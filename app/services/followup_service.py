import json
import logging
from datetime import datetime, timedelta, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.campaign import Campaign
from app.models.client import Client
from app.models.follow_up_rule import FollowUpRule
from app.models.lead import Lead
from app.services.dm_sender_service import dm_sender_service

logger = logging.getLogger(__name__)

FOLLOW_UP_PROMPT = """Eres un copywriter experto en follow-up DMs de Instagram para {client_business_type}.

## Contexto:
Este es el follow-up #{step_number} para un lead que no respondio al DM original.

## DM original enviado:
{original_dm}

## Informacion del lead:
- Nombre: {full_name}
- Username: {username}
- Bio: {bio}
- Categoria: {category}
- Research: {research_data}

## Servicio que ofrecemos:
{client_service_description}

{custom_instructions}

## Reglas para el follow-up:
1. SOLO texto plano, sin formateo
2. Maximo 2-3 oraciones (mas corto que el DM original)
3. NO repitas lo mismo que el DM original — usa un angulo diferente
4. Tono casual y natural, como si recordaras algo
5. Nunca uses palabras que suenen a IA: "journey", "game-changer", "impressive", "amplify"
6. NO seas agresivo ni insistente
7. Si es follow-up #2+, se aun mas breve y directo
8. Evita: emojis, exclamaciones excesivas, ALL CAPS

## Output:
Responde SOLO en JSON valido, sin markdown ni backticks:
{{
  "follow_up_message": "<texto del follow-up>"
}}"""


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from API response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


class FollowUpService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def _call_claude(self, prompt: str, max_tokens: int = 1024) -> str:
        """Make a Claude API call and return the text response."""
        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    def generate_follow_up(
        self, lead: Lead, rule: FollowUpRule, client_config: dict
    ) -> str | None:
        """Generate a personalized follow-up DM using Claude.

        Returns the follow-up message text, or None on failure.
        """
        username = lead.ig_username
        try:
            custom_instructions = ""
            if rule.template_prompt:
                custom_instructions = f"## Instrucciones adicionales del cliente:\n{rule.template_prompt}"

            prompt = FOLLOW_UP_PROMPT.format(
                full_name=lead.ig_full_name or "",
                username=username,
                bio=lead.ig_bio_clean or lead.ig_bio or "",
                category=lead.lead_category or "",
                research_data=lead.research_data or "No research available",
                original_dm=lead.dm_message or "No original DM available",
                step_number=rule.step_number,
                client_business_type=client_config.get("business_type", "B2B automation"),
                client_service_description=client_config.get(
                    "service_description", "B2B lead generation and automation services"
                ),
                custom_instructions=custom_instructions,
            )
            raw = self._call_claude(prompt, max_tokens=1024)
            result = json.loads(_strip_code_fences(raw))
            message = result.get("follow_up_message")
            if message:
                logger.info(f"Generated follow-up #{rule.step_number} for @{username}")
            return message
        except Exception as e:
            logger.error(
                f"Follow-up generation failed for @{username} (step {rule.step_number}): "
                f"{type(e).__name__}: {e}"
            )
            return None

    async def get_leads_due_for_followup(
        self, campaign_id: str, db: AsyncSession
    ) -> list[Lead]:
        """Get leads that are due for a follow-up message.

        Criteria:
        - status = 'sent'
        - conversation_status != 'replied'
        - next_follow_up_at <= now()
        - follow_up_count < max_attempts (checked per-rule later)
        """
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Lead).where(
                Lead.campaign_id == campaign_id,
                Lead.status == "sent",
                Lead.conversation_status != "replied",
                Lead.next_follow_up_at.isnot(None),
                Lead.next_follow_up_at <= now,
            ).order_by(Lead.score.desc())
        )
        return list(result.scalars().all())

    async def get_active_rules(
        self, campaign_id: str, db: AsyncSession
    ) -> list[FollowUpRule]:
        """Get active follow-up rules for a campaign, ordered by step_number."""
        result = await db.execute(
            select(FollowUpRule).where(
                FollowUpRule.campaign_id == campaign_id,
                FollowUpRule.is_active.is_(True),
            ).order_by(FollowUpRule.step_number)
        )
        return list(result.scalars().all())

    async def schedule_next_follow_up(
        self, lead: Lead, rules: list[FollowUpRule], db: AsyncSession
    ) -> None:
        """Calculate and set next_follow_up_at based on the next rule's delay_days.

        If no more rules apply, clears next_follow_up_at.
        """
        next_step = lead.follow_up_count + 1
        next_rule = None
        for rule in rules:
            if rule.step_number == next_step and rule.is_active:
                next_rule = rule
                break

        if next_rule is None or lead.follow_up_count >= next_rule.max_attempts:
            # No more follow-ups scheduled
            lead.next_follow_up_at = None
            return

        # Calculate from last action timestamp
        reference_time = lead.last_follow_up_at or lead.sent_at or datetime.now(timezone.utc)
        lead.next_follow_up_at = reference_time + timedelta(days=next_rule.delay_days)

    async def process_follow_ups(
        self, campaign_id: str, db: AsyncSession
    ) -> dict:
        """Full follow-up processing flow for a campaign.

        1. Find leads due for follow-up
        2. Get active rules
        3. Generate follow-up message via Claude
        4. Send via dm_sender
        5. Update lead fields

        Returns dict with sent_count, failed_count, skipped_count.
        """
        rules = await self.get_active_rules(campaign_id, db)
        if not rules:
            logger.info(f"No active follow-up rules for campaign {campaign_id}")
            return {"sent_count": 0, "failed_count": 0, "skipped_count": 0}

        rules_by_step = {r.step_number: r for r in rules}

        leads = await self.get_leads_due_for_followup(campaign_id, db)
        if not leads:
            logger.info(f"No leads due for follow-up in campaign {campaign_id}")
            return {"sent_count": 0, "failed_count": 0, "skipped_count": 0}

        logger.info(f"Processing follow-ups for {len(leads)} leads in campaign {campaign_id}")

        # Get client config
        campaign_result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = campaign_result.scalar_one_or_none()
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found")
            return {"sent_count": 0, "failed_count": 0, "skipped_count": 0}

        client_result = await db.execute(
            select(Client).where(Client.id == campaign.client_id)
        )
        client = client_result.scalar_one_or_none()
        client_config = {
            "business_type": client.business_type if client else "B2B automation",
            "service_description": (client.settings or {}).get(
                "service_description",
                "B2B lead generation and automation services",
            ) if client else "B2B lead generation and automation services",
        }

        # Login to Instagram
        logged_in = dm_sender_service.login()
        if not logged_in:
            logger.error("Instagram login failed — cannot send follow-ups")
            return {"sent_count": 0, "failed_count": 0, "skipped_count": 0, "error": "Instagram login failed"}

        sent_count = 0
        failed_count = 0
        skipped_count = 0

        for lead in leads:
            next_step = lead.follow_up_count + 1
            rule = rules_by_step.get(next_step)

            if rule is None:
                # No rule for this step — clear schedule
                lead.next_follow_up_at = None
                skipped_count += 1
                continue

            if lead.follow_up_count >= rule.max_attempts:
                lead.next_follow_up_at = None
                skipped_count += 1
                continue

            # Generate follow-up message
            follow_up_msg = self.generate_follow_up(lead, rule, client_config)
            if not follow_up_msg:
                logger.warning(f"Could not generate follow-up for @{lead.ig_username}, skipping")
                skipped_count += 1
                continue

            # Send follow-up DM
            send_result = dm_sender_service.send_dm(lead.ig_username, follow_up_msg)

            now = datetime.now(timezone.utc)

            if send_result["success"]:
                lead.follow_up_count += 1
                lead.last_follow_up_at = now
                sent_count += 1
                logger.info(
                    f"Follow-up #{next_step} sent to @{lead.ig_username} "
                    f"[{sent_count}/{len(leads)}]"
                )

                # Schedule next follow-up if there are more rules
                await self.schedule_next_follow_up(lead, rules, db)
            else:
                failed_count += 1
                logger.warning(
                    f"Follow-up #{next_step} failed for @{lead.ig_username}: "
                    f"{send_result.get('error', 'Unknown error')}"
                )

                # If challenge/block, stop processing this campaign
                if send_result.get("is_challenge") or send_result.get("is_block"):
                    logger.warning("Account challenge/block detected — stopping follow-up processing")
                    await db.commit()
                    return {
                        "sent_count": sent_count,
                        "failed_count": failed_count,
                        "skipped_count": skipped_count,
                        "paused": True,
                        "reason": "Account challenge/block",
                    }

            await db.commit()

        dm_sender_service.save_sessions()

        logger.info(
            f"Follow-up processing complete for campaign {campaign_id}: "
            f"{sent_count} sent, {failed_count} failed, {skipped_count} skipped"
        )

        return {
            "sent_count": sent_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
        }


followup_service = FollowUpService()

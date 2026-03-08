import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead
from app.utils.text_cleanup import clean_bio

logger = logging.getLogger(__name__)

# Max parallel API calls (respect rate limits)
MAX_PARALLEL_SCORING = 10

SCORING_PROMPT = """Eres un asistente de calificación de leads para una agencia de automatización B2B.

Evalúa este perfil de Instagram y asigna un score de 0 a 100.

## Datos del lead:
- Username: {username}
- Nombre: {full_name}
- Bio: {bio}
- Website: {website}
- Categoría IG: {category}
- Followers: {follower_count}
- Following: {following_count}
- Perfil privado: {is_private}

## Criterios de scoring:
- Es un negocio o emprendedor (0-25 puntos)
- Tiene entre 200 y 1M followers (0-15 puntos)
- Su bio menciona servicios, productos o negocio (0-20 puntos)
- Podría beneficiarse de lead generation B2B (0-25 puntos)
- Tiene website (0-10 puntos)
- Perfil público (0-5 puntos, 0 si es privado)

## Output:
Responde SOLO en JSON válido, sin markdown ni backticks:
{{
    "score": <número 0-100>,
    "reason": "<explicación de 1-2 oraciones>",
    "category": "<una de: coach, ecommerce, saas, agency, creator, local_business, other>",
    "bio_clean": "<bio limpia sin emojis ni line breaks>"
}}"""


class ScoringService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def score_lead(self, lead_data: dict) -> dict:
        """Score a single lead using Claude API. Returns dict with score, reason, category."""
        prompt = SCORING_PROMPT.format(
            username=lead_data.get("ig_username", ""),
            full_name=lead_data.get("ig_full_name", ""),
            bio=lead_data.get("ig_bio", ""),
            website=lead_data.get("ig_website", ""),
            category=lead_data.get("ig_category", ""),
            follower_count=lead_data.get("ig_follower_count", 0),
            following_count=lead_data.get("ig_following_count", 0),
            is_private=lead_data.get("ig_is_private", False),
        )

        message = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()
        # Strip markdown code fences if present
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1] if "\n" in response_text else response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3].strip()
        return json.loads(response_text)

    def _score_lead_safe(self, lead_data: dict) -> tuple[str, dict | None]:
        """Thread-safe scoring wrapper. Returns (username, result_or_None)."""
        username = lead_data.get("ig_username", "unknown")
        try:
            result = self.score_lead(lead_data)
            logger.info(f"Scored lead {username}: {result.get('score', 0)}")
            return (username, result)
        except Exception:
            logger.exception(f"Error scoring lead {username}")
            return (username, None)

    async def score_leads_batch(
        self, lead_ids: list[str], db: AsyncSession
    ) -> list[str]:
        """Score a batch of leads in parallel. Returns list of lead_ids that meet the threshold."""
        result = await db.execute(
            select(Lead).where(Lead.id.in_(lead_ids), Lead.status == "scraped")
        )
        leads = result.scalars().all()

        if not leads:
            return []

        # Prepare lead data for parallel scoring
        lead_data_map: dict[str, tuple] = {}  # username -> (lead, lead_data, cleaned_bio)
        for lead in leads:
            cleaned_bio = clean_bio(lead.ig_bio)
            lead_data = {
                "ig_username": lead.ig_username,
                "ig_full_name": lead.ig_full_name,
                "ig_bio": cleaned_bio,
                "ig_website": lead.ig_website,
                "ig_category": lead.ig_category,
                "ig_follower_count": lead.ig_follower_count,
                "ig_following_count": lead.ig_following_count,
                "ig_is_private": lead.ig_is_private,
            }
            lead_data_map[lead.ig_username] = (lead, lead_data, cleaned_bio)

        # Score in parallel using ThreadPoolExecutor
        logger.info(f"Scoring {len(leads)} leads in parallel (max {MAX_PARALLEL_SCORING} concurrent)")
        scored_ids = []

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SCORING) as executor:
            futures = {
                executor.submit(self._score_lead_safe, data[1]): username
                for username, data in lead_data_map.items()
            }
            for future in as_completed(futures):
                username = futures[future]
                _, score_result = future.result()
                if score_result is None:
                    continue

                lead, _, cleaned_bio = lead_data_map[username]
                lead.score = score_result.get("score", 0)
                lead.score_reason = score_result.get("reason", "")
                lead.lead_category = score_result.get("category", "other")
                lead.ig_bio_clean = score_result.get("bio_clean") or cleaned_bio
                lead.status = "scored"
                lead.scored_at = datetime.now(timezone.utc)
                scored_ids.append(str(lead.id))

        await db.flush()
        logger.info(f"Parallel scoring complete: {len(scored_ids)}/{len(leads)} leads scored")
        return scored_ids


scoring_service = ScoringService()

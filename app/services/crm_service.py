"""CRM service — Kanban pipeline with dynamic scoring.

Provides:
- get_pipeline_board: all leads organized by CRM stage
- move_lead: move a lead to a different stage
- get_lead_detail: full lead info with score history, notes, conversation
- add_note: add a manual note to a lead
- auto_classify_stage: automatic stage transitions based on events
- update_conversation_score: dynamic scoring via Claude when replies arrive
- get_board_stats: metrics per stage
"""

import json
import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

import anthropic
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.campaign import Campaign
from app.models.crm import LeadNote, ScoreHistory
from app.models.lead import Lead
from app.schemas.enums import CrmStage

logger = logging.getLogger(__name__)

# CRM stages in display order
CRM_STAGES = [
    CrmStage.NEW,
    CrmStage.CONTACTED,
    CrmStage.REPLIED,
    CrmStage.INTERESTED,
    CrmStage.CALL_SCHEDULED,
    CrmStage.CLOSED_WON,
    CrmStage.CLOSED_LOST,
]

# Spanish labels for display
STAGE_LABELS = {
    "new": "Nuevo",
    "contacted": "Contactado",
    "replied": "Respondió",
    "interested": "Interesado",
    "call_scheduled": "Llamada Agendada",
    "closed_won": "Cerrado (Ganado)",
    "closed_lost": "Cerrado (Perdido)",
}

# Keywords that indicate interest (Spanish + English)
INTEREST_KEYWORDS = [
    "precio", "costo", "cuánto", "cuanto", "agendar", "llamada",
    "reunión", "reunion", "demo", "price", "cost", "how much",
    "schedule", "call", "meeting", "interested", "interesado",
]

# Keywords that indicate lost (Spanish + English)
LOST_KEYWORDS = [
    "no gracias", "no me interesa", "no estoy interesado",
    "no thanks", "not interested", "no necesito",
]


class CrmService:
    """CRM pipeline: Kanban board, stage management, dynamic scoring."""

    def __init__(self):
        self._anthropic_client: anthropic.Anthropic | None = None

    def _get_anthropic_client(self) -> anthropic.Anthropic:
        if self._anthropic_client is None:
            self._anthropic_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._anthropic_client

    # ------------------------------------------------------------------ #
    # 1. Get pipeline board
    # ------------------------------------------------------------------ #
    async def get_pipeline_board(
        self,
        db: AsyncSession,
        *,
        campaign_id: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> dict:
        """Return all leads organized by CRM stage.

        Returns: {"stages": {stage: [leads]}, "stage_labels": {...}}
        """
        query = select(Lead).where(Lead.dm_message.isnot(None))

        if campaign_id:
            query = query.where(Lead.campaign_id == campaign_id)
        if client_id:
            query = query.where(Lead.client_id == client_id)

        query = query.order_by(desc(Lead.score))
        result = await db.execute(query)
        leads = result.scalars().all()

        stages = {stage.value: [] for stage in CRM_STAGES}

        for lead in leads:
            stage = lead.crm_stage if lead.crm_stage in stages else "new"
            stages[stage].append(self._lead_to_card(lead))

        return {
            "stages": stages,
            "stage_labels": STAGE_LABELS,
        }

    def _lead_to_card(self, lead: Lead) -> dict:
        """Convert Lead to a CRM card dict."""
        has_reply = lead.reply_text is not None
        last_msg = lead.reply_text if has_reply else lead.dm_message
        last_msg_at = lead.replied_at if has_reply else lead.sent_at

        return {
            "lead_id": str(lead.id),
            "campaign_id": str(lead.campaign_id),
            "ig_username": lead.ig_username,
            "ig_full_name": lead.ig_full_name,
            "ig_profile_pic_url": lead.ig_profile_pic_url,
            "score": lead.score,
            "crm_stage": lead.crm_stage,
            "reply_classification": lead.reply_classification,
            "conversation_status": lead.conversation_status,
            "last_message_preview": (last_msg[:80] + "...") if last_msg and len(last_msg) > 80 else last_msg,
            "last_message_at": last_msg_at.isoformat() if last_msg_at else None,
            "has_reply": has_reply,
            "follow_up_count": lead.follow_up_count,
            "lead_category": lead.lead_category,
        }

    # ------------------------------------------------------------------ #
    # 2. Move lead
    # ------------------------------------------------------------------ #
    async def move_lead(
        self,
        lead_id: str,
        new_stage: str,
        db: AsyncSession,
        user_id: Optional[str] = None,
    ) -> dict:
        """Move a lead to a new CRM stage. Returns updated lead card."""
        lead = await db.get(Lead, lead_id)
        if not lead:
            return {"error": "Lead not found"}

        valid_stages = {s.value for s in CRM_STAGES}
        if new_stage not in valid_stages:
            return {"error": f"Invalid stage: {new_stage}"}

        old_stage = lead.crm_stage
        lead.crm_stage = new_stage
        await db.commit()

        logger.info(f"CRM: @{lead.ig_username} moved from {old_stage} to {new_stage}")
        return {"success": True, "old_stage": old_stage, "new_stage": new_stage}

    # ------------------------------------------------------------------ #
    # 3. Get lead detail
    # ------------------------------------------------------------------ #
    async def get_lead_detail(
        self, lead_id: str, db: AsyncSession,
    ) -> dict | None:
        """Full lead detail: info, score history, notes, conversation."""
        lead = await db.get(Lead, lead_id)
        if not lead:
            return None

        # Get score history
        hist_result = await db.execute(
            select(ScoreHistory)
            .where(ScoreHistory.lead_id == lead_id)
            .order_by(desc(ScoreHistory.created_at))
            .limit(20)
        )
        score_history = [
            {
                "old_score": h.old_score,
                "new_score": h.new_score,
                "delta": h.delta,
                "reason": h.reason,
                "created_at": h.created_at.isoformat(),
            }
            for h in hist_result.scalars().all()
        ]

        # Get notes
        notes_result = await db.execute(
            select(LeadNote)
            .where(LeadNote.lead_id == lead_id)
            .order_by(desc(LeadNote.created_at))
            .limit(50)
        )
        notes = [
            {
                "id": str(n.id),
                "content": n.content,
                "user_id": str(n.user_id) if n.user_id else None,
                "created_at": n.created_at.isoformat(),
            }
            for n in notes_result.scalars().all()
        ]

        # Get conversation messages if available
        from app.models.conversation_message import ConversationMessage
        msgs_result = await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.lead_id == lead_id)
            .order_by(ConversationMessage.sent_at.asc())
        )
        messages = [
            {
                "direction": m.direction,
                "message_type": m.message_type,
                "content": m.content,
                "sent_at": m.sent_at.isoformat(),
            }
            for m in msgs_result.scalars().all()
        ]

        # If no conversation_messages, reconstruct from lead fields
        if not messages:
            if lead.dm_message and lead.sent_at:
                messages.append({
                    "direction": "outbound", "message_type": "dm",
                    "content": lead.dm_message, "sent_at": lead.sent_at.isoformat(),
                })
            if lead.reply_text and lead.replied_at:
                messages.append({
                    "direction": "inbound", "message_type": "reply",
                    "content": lead.reply_text, "sent_at": lead.replied_at.isoformat(),
                })

        return {
            "lead": {
                "id": str(lead.id),
                "campaign_id": str(lead.campaign_id),
                "client_id": str(lead.client_id),
                "ig_username": lead.ig_username,
                "ig_full_name": lead.ig_full_name,
                "ig_bio": lead.ig_bio,
                "ig_profile_pic_url": lead.ig_profile_pic_url,
                "ig_follower_count": lead.ig_follower_count,
                "ig_following_count": lead.ig_following_count,
                "score": lead.score,
                "score_reason": lead.score_reason,
                "lead_category": lead.lead_category,
                "research_summary": lead.research_summary,
                "crm_stage": lead.crm_stage,
                "reply_classification": lead.reply_classification,
                "conversation_status": lead.conversation_status,
                "comment_message": lead.comment_message,
                "comment_sent_at": lead.comment_sent_at.isoformat() if lead.comment_sent_at else None,
                "sent_at": lead.sent_at.isoformat() if lead.sent_at else None,
                "replied_at": lead.replied_at.isoformat() if lead.replied_at else None,
            },
            "score_history": score_history,
            "notes": notes,
            "messages": messages,
        }

    # ------------------------------------------------------------------ #
    # 4. Add note
    # ------------------------------------------------------------------ #
    async def add_note(
        self,
        lead_id: str,
        content: str,
        db: AsyncSession,
        user_id: Optional[str] = None,
    ) -> dict | None:
        """Add a manual note to a lead."""
        lead = await db.get(Lead, lead_id)
        if not lead:
            return None

        note = LeadNote(
            id=_uuid.uuid4(),
            lead_id=lead.id,
            user_id=user_id if user_id else None,
            content=content,
        )
        db.add(note)
        await db.commit()

        logger.info(f"CRM: Note added to @{lead.ig_username}")
        return {
            "id": str(note.id),
            "content": note.content,
            "created_at": note.created_at.isoformat() if note.created_at else datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #
    # 5. Auto-classify stage
    # ------------------------------------------------------------------ #
    async def auto_classify_stage(
        self, lead_id: str, db: AsyncSession, event: str = "unknown",
    ) -> str | None:
        """Automatically transition a lead's CRM stage based on events.

        Events: "dm_sent", "reply_received", "reply_positive", "reply_negative"
        Returns the new stage, or None if no change.
        """
        lead = await db.get(Lead, lead_id)
        if not lead:
            return None

        old_stage = lead.crm_stage

        if event == "dm_sent":
            if old_stage == "new":
                lead.crm_stage = CrmStage.CONTACTED
        elif event == "reply_received":
            if old_stage in ("new", "contacted"):
                lead.crm_stage = CrmStage.REPLIED
            # Check reply text for interest/lost keywords
            if lead.reply_text:
                reply_lower = lead.reply_text.lower()
                if any(kw in reply_lower for kw in INTEREST_KEYWORDS):
                    lead.crm_stage = CrmStage.INTERESTED
                elif any(kw in reply_lower for kw in LOST_KEYWORDS):
                    lead.crm_stage = CrmStage.CLOSED_LOST
        elif event == "reply_positive":
            if old_stage not in ("call_scheduled", "closed_won"):
                lead.crm_stage = CrmStage.INTERESTED
        elif event == "reply_negative":
            if old_stage not in ("call_scheduled", "closed_won", "closed_lost"):
                lead.crm_stage = CrmStage.CLOSED_LOST

        if lead.crm_stage != old_stage:
            await db.commit()
            logger.info(f"CRM auto-classify: @{lead.ig_username} {old_stage} -> {lead.crm_stage} (event={event})")
            return lead.crm_stage
        return None

    # ------------------------------------------------------------------ #
    # 6. Dynamic scoring
    # ------------------------------------------------------------------ #
    async def update_conversation_score(
        self, lead_id: str, db: AsyncSession,
    ) -> dict | None:
        """Evaluate purchase intent from latest reply and adjust score.

        Claude evaluates the reply in context and returns a delta (-20 to +20).
        The score change is recorded in score_history.
        """
        lead = await db.get(Lead, lead_id)
        if not lead or not lead.reply_text:
            return None

        if lead.score is None:
            return None

        reply_text = lead.reply_text

        prompt = (
            "You are evaluating purchase intent from an Instagram DM reply. "
            "Based on the reply text, assign a score delta between -20 and +20.\n\n"
            "Guidelines:\n"
            "- Strong buying intent (asks price, wants to schedule call, asks how to buy): +10 to +20\n"
            "- Mild interest (tell me more, interesting, curious): +5 to +10\n"
            "- Neutral (ok, thanks, I'll think about it): 0 to +5\n"
            "- Mild disinterest (not right now, maybe later, busy): -5 to -10\n"
            "- Clear rejection (not interested, no thanks, stop messaging): -15 to -20\n"
            "- Spam or irrelevant (gibberish, bot-like): -10\n\n"
            f"Reply text: \"{reply_text}\"\n\n"
            "Respond with ONLY a JSON object: {\"delta\": <number>, \"reason\": \"<short reason>\"}\n"
            "No markdown, no explanation."
        )

        try:
            client = self._get_anthropic_client()
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = response.content[0].text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
                raw_text = raw_text.rsplit("```", 1)[0].strip()

            result = json.loads(raw_text)
            delta = max(-20, min(20, int(result.get("delta", 0))))
            reason = result.get("reason", "AI evaluation")

            old_score = lead.score
            new_score = max(0, min(100, old_score + delta))

            # Record history
            history = ScoreHistory(
                id=_uuid.uuid4(),
                lead_id=lead.id,
                old_score=old_score,
                new_score=new_score,
                delta=delta,
                reason=reason,
            )
            db.add(history)

            # Update lead score
            lead.score = new_score
            await db.commit()

            logger.info(
                f"CRM dynamic score: @{lead.ig_username} "
                f"{old_score} -> {new_score} ({'+' if delta > 0 else ''}{delta}) reason={reason}"
            )

            return {
                "old_score": old_score,
                "new_score": new_score,
                "delta": delta,
                "reason": reason,
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse scoring response for lead {lead_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Dynamic scoring failed for lead {lead_id}: {type(e).__name__}: {e}")
            return None

    # ------------------------------------------------------------------ #
    # 7. Board stats
    # ------------------------------------------------------------------ #
    async def get_board_stats(
        self,
        db: AsyncSession,
        *,
        campaign_id: Optional[str] = None,
    ) -> dict:
        """Metrics per stage: count, avg score."""
        query = select(
            Lead.crm_stage,
            func.count().label("count"),
            func.avg(Lead.score).label("avg_score"),
        ).where(
            Lead.dm_message.isnot(None),
        ).group_by(Lead.crm_stage)

        if campaign_id:
            query = query.where(Lead.campaign_id == campaign_id)

        result = await db.execute(query)
        rows = result.all()

        stages = {}
        total_leads = 0
        total_replied = 0
        total_interested = 0
        total_closed_won = 0

        for row in rows:
            stage = row.crm_stage or "new"
            count = row.count
            stages[stage] = {
                "count": count,
                "avg_score": round(float(row.avg_score), 1) if row.avg_score else 0,
                "label": STAGE_LABELS.get(stage, stage),
            }
            total_leads += count
            if stage in ("replied", "interested", "call_scheduled", "closed_won"):
                total_replied += count
            if stage in ("interested", "call_scheduled", "closed_won"):
                total_interested += count
            if stage == "closed_won":
                total_closed_won += count

        response_rate = (total_replied / total_leads * 100) if total_leads > 0 else 0
        interest_rate = (total_interested / total_leads * 100) if total_leads > 0 else 0

        return {
            "stages": stages,
            "total_leads": total_leads,
            "response_rate": round(response_rate, 1),
            "interest_rate": round(interest_rate, 1),
            "closed_won": total_closed_won,
        }

    # ------------------------------------------------------------------ #
    # 8. Get score history
    # ------------------------------------------------------------------ #
    async def get_score_history(
        self, lead_id: str, db: AsyncSession,
    ) -> list[dict]:
        """Return score change timeline for a lead."""
        result = await db.execute(
            select(ScoreHistory)
            .where(ScoreHistory.lead_id == lead_id)
            .order_by(desc(ScoreHistory.created_at))
            .limit(50)
        )
        return [
            {
                "old_score": h.old_score,
                "new_score": h.new_score,
                "delta": h.delta,
                "reason": h.reason,
                "created_at": h.created_at.isoformat(),
            }
            for h in result.scalars().all()
        ]


crm_service = CrmService()

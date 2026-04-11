"""Unibox service — unified inbox with AI-assisted reply suggestions.

Provides:
- get_all_conversations: paginated conversation list with filters
- get_conversation_thread: full message history for a lead
- send_reply: send a reply via instagrapi
- generate_reply_suggestions: Claude-powered reply suggestions (Close/Nurture/Qualify)
- auto_suggest_on_new_reply: pre-generate suggestions when inbox detects a new reply
- mark_as_read / mark_as_starred: conversation state management
- get_stats: unread counts, classification breakdown, avg response time
"""

import json
import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

import anthropic
from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.campaign import Campaign
from app.models.client import Client
from app.models.conversation_message import ConversationMessage
from app.models.lead import Lead
from app.models.reply_suggestion import ReplySuggestion

logger = logging.getLogger(__name__)


class UniboxService:
    """Unified inbox: conversations, threads, replies, and AI suggestions."""

    def __init__(self):
        self._anthropic_client: anthropic.Anthropic | None = None

    def _get_anthropic_client(self) -> anthropic.Anthropic:
        if self._anthropic_client is None:
            self._anthropic_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._anthropic_client

    # ------------------------------------------------------------------ #
    # 1. List conversations
    # ------------------------------------------------------------------ #
    async def get_all_conversations(
        self,
        db: AsyncSession,
        *,
        campaign_id: Optional[str] = None,
        client_id: Optional[str] = None,
        classification: Optional[str] = None,
        conversation_status: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "recent",  # recent | score
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Return paginated list of conversations (leads that have been sent a DM).

        Returns: {"conversations": [...], "total": int}
        """
        query = select(Lead).where(
            Lead.status.in_(["sent", "delivered", "failed"]),
            Lead.dm_message.isnot(None),
        )

        if campaign_id:
            query = query.where(Lead.campaign_id == campaign_id)
        if client_id:
            query = query.where(Lead.client_id == client_id)
        if classification:
            query = query.where(Lead.reply_classification == classification)
        if conversation_status:
            query = query.where(Lead.conversation_status == conversation_status)
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Lead.ig_username.ilike(search_pattern),
                    Lead.ig_full_name.ilike(search_pattern),
                    Lead.reply_text.ilike(search_pattern),
                )
            )

        # Count total before pagination
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # Sort
        if sort_by == "score":
            query = query.order_by(desc(Lead.score), desc(Lead.replied_at))
        else:  # recent
            query = query.order_by(
                # Leads with replies first, ordered by reply time
                case(
                    (Lead.replied_at.isnot(None), Lead.replied_at),
                    else_=Lead.sent_at,
                ).desc()
            )

        query = query.limit(limit).offset(offset)
        result = await db.execute(query)
        leads = result.scalars().all()

        conversations = []
        for lead in leads:
            conversations.append(self._lead_to_conversation(lead))

        return {"conversations": conversations, "total": total}

    def _lead_to_conversation(self, lead: Lead) -> dict:
        """Convert a Lead ORM object to a conversation summary dict."""
        has_reply = lead.reply_text is not None
        last_message = lead.reply_text if has_reply else lead.dm_message
        last_message_at = lead.replied_at if has_reply else lead.sent_at

        return {
            "lead_id": str(lead.id),
            "campaign_id": str(lead.campaign_id),
            "client_id": str(lead.client_id),
            "ig_username": lead.ig_username,
            "ig_full_name": lead.ig_full_name,
            "ig_profile_pic_url": lead.ig_profile_pic_url,
            "score": lead.score,
            "reply_classification": lead.reply_classification,
            "conversation_status": lead.conversation_status,
            "crm_stage": lead.crm_stage,
            "has_reply": has_reply,
            "last_message_preview": (last_message[:100] + "...") if last_message and len(last_message) > 100 else last_message,
            "last_message_at": last_message_at.isoformat() if last_message_at else None,
            "replied_at": lead.replied_at.isoformat() if lead.replied_at else None,
            "sent_at": lead.sent_at.isoformat() if lead.sent_at else None,
            "follow_up_count": lead.follow_up_count,
        }

    # ------------------------------------------------------------------ #
    # 2. Get conversation thread
    # ------------------------------------------------------------------ #
    async def get_conversation_thread(
        self, lead_id: str, db: AsyncSession,
    ) -> dict | None:
        """Return full conversation thread for a lead, including lead info.

        Reconstructs thread from:
        1. conversation_messages table (full history if available)
        2. Fallback: lead.dm_message + lead.reply_text (legacy data)
        """
        lead = await db.get(Lead, lead_id)
        if not lead:
            return None

        # Get stored conversation messages
        result = await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.lead_id == lead_id)
            .order_by(ConversationMessage.sent_at.asc())
        )
        stored_messages = result.scalars().all()

        if stored_messages:
            messages = [
                {
                    "id": str(msg.id),
                    "direction": msg.direction,
                    "message_type": msg.message_type,
                    "content": msg.content,
                    "ig_account_used": msg.ig_account_used,
                    "variant_used": msg.variant_used,
                    "sent_at": msg.sent_at.isoformat(),
                }
                for msg in stored_messages
            ]
        else:
            # Reconstruct from lead fields (legacy data before unibox)
            messages = []
            if lead.dm_message and lead.sent_at:
                messages.append({
                    "id": None,
                    "direction": "outbound",
                    "message_type": "dm",
                    "content": lead.dm_message,
                    "ig_account_used": None,
                    "variant_used": lead.dm_variant_used,
                    "sent_at": lead.sent_at.isoformat(),
                })
            if lead.reply_text and lead.replied_at:
                messages.append({
                    "id": None,
                    "direction": "inbound",
                    "message_type": "reply",
                    "content": lead.reply_text,
                    "ig_account_used": None,
                    "variant_used": None,
                    "sent_at": lead.replied_at.isoformat(),
                })

        # Get latest suggestions
        sugg_result = await db.execute(
            select(ReplySuggestion)
            .where(ReplySuggestion.lead_id == lead_id)
            .order_by(ReplySuggestion.generated_at.desc())
            .limit(1)
        )
        suggestion = sugg_result.scalar_one_or_none()

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
                "reply_classification": lead.reply_classification,
                "conversation_status": lead.conversation_status,
                "crm_stage": lead.crm_stage,
                "comment_message": lead.comment_message,
                "comment_sent_at": lead.comment_sent_at.isoformat() if lead.comment_sent_at else None,
            },
            "messages": messages,
            "suggestions": suggestion.suggestions if suggestion else None,
            "suggestions_generated_at": suggestion.generated_at.isoformat() if suggestion else None,
        }

    # ------------------------------------------------------------------ #
    # 3. Send reply
    # ------------------------------------------------------------------ #
    async def send_reply(
        self,
        lead_id: str,
        message: str,
        db: AsyncSession,
    ) -> dict:
        """Send a manual reply to a lead via instagrapi.

        Uses the dm_sender_service for anti-detection and account rotation.
        Returns: {"success": bool, "error": str | None}
        """
        lead = await db.get(Lead, lead_id)
        if not lead:
            return {"success": False, "error": "Lead not found"}

        from app.services.dm_sender_service import dm_sender_service

        # Ensure we're logged in
        logged_in = dm_sender_service.login()
        if not logged_in:
            return {"success": False, "error": "Instagram login failed"}

        # Send via dm_sender_service (uses round-robin account rotation)
        result = dm_sender_service.send_dm(lead.ig_username, message)

        if result.get("success"):
            # Determine which account sent it
            account_used = None
            for acct in dm_sender_service._accounts:
                if acct._logged_in:
                    account_used = acct.username
                    break

            # Store in conversation_messages
            conv_msg = ConversationMessage(
                id=_uuid.uuid4(),
                lead_id=lead.id,
                campaign_id=lead.campaign_id,
                client_id=lead.client_id,
                direction="outbound",
                message_type="manual_reply",
                content=message,
                ig_account_used=account_used,
                sent_at=datetime.now(timezone.utc),
            )
            db.add(conv_msg)

            # Update lead conversation status
            lead.conversation_status = "engaged"

            await db.commit()

            # Save IG sessions
            dm_sender_service.save_sessions()

            logger.info(f"Manual reply sent to @{lead.ig_username} via Unibox")
            return {"success": True, "error": None}
        else:
            error = result.get("error", "Unknown send error")
            logger.error(f"Failed to send reply to @{lead.ig_username}: {error}")
            return {"success": False, "error": error}

    # ------------------------------------------------------------------ #
    # 4. Generate reply suggestions
    # ------------------------------------------------------------------ #
    async def generate_reply_suggestions(
        self, lead_id: str, db: AsyncSession,
    ) -> dict | None:
        """Generate 3 AI reply suggestions for a conversation.

        Intents:
        1. Close — schedule a call or close the sale
        2. Nurture — answer their question, keep the conversation going
        3. Qualify — ask questions to understand if they're a good fit

        Returns the suggestions dict or None if generation fails.
        """
        lead = await db.get(Lead, lead_id)
        if not lead:
            return None

        # Build conversation context
        thread = await self.get_conversation_thread(lead_id, db)
        if not thread:
            return None

        # Get campaign info for context
        campaign = await db.get(Campaign, str(lead.campaign_id))
        campaign_name = campaign.name if campaign else "Unknown"
        campaign_settings = campaign.settings if campaign else {}

        # Get client info for custom prompts
        client = await db.get(Client, str(lead.client_id))
        client_name = client.name if client else "Unknown"
        client_settings = client.settings if client else {}
        dm_prompt = client_settings.get("dm_prompt", "")

        # Build conversation transcript
        transcript_lines = []
        for msg in thread["messages"]:
            sender = "Tú" if msg["direction"] == "outbound" else f"@{lead.ig_username}"
            transcript_lines.append(f"{sender}: {msg['content']}")
        transcript = "\n".join(transcript_lines)

        # Build lead context
        lead_info = thread["lead"]
        lead_context_parts = []
        if lead_info.get("ig_bio"):
            lead_context_parts.append(f"Bio: {lead_info['ig_bio']}")
        if lead_info.get("ig_follower_count"):
            lead_context_parts.append(f"Followers: {lead_info['ig_follower_count']}")
        if lead_info.get("lead_category"):
            lead_context_parts.append(f"Category: {lead_info['lead_category']}")
        if lead_info.get("score"):
            lead_context_parts.append(f"Score: {lead_info['score']}/100")
        if lead_info.get("research_summary"):
            lead_context_parts.append(f"Research: {lead_info['research_summary'][:500]}")
        lead_context = "\n".join(lead_context_parts) if lead_context_parts else "No additional info"

        prompt = (
            "You are an expert Instagram DM sales assistant. "
            "Based on the conversation below, generate 3 reply suggestions with different intents.\n\n"
            f"**Campaign:** {campaign_name}\n"
            f"**Client/Business:** {client_name}\n"
        )
        if dm_prompt:
            prompt += f"**Business context:** {dm_prompt[:500]}\n"

        prompt += (
            f"\n**Lead info:**\n{lead_context}\n\n"
            f"**Conversation so far:**\n{transcript}\n\n"
            "Generate exactly 3 reply suggestions as a JSON array. Each suggestion must have:\n"
            '- "intent": one of "close", "nurture", "qualify"\n'
            '- "label": short label in Spanish (e.g., "Agendar llamada", "Responder pregunta", "Calificar interés")\n'
            '- "message": the actual DM reply text (in the same language as the conversation, natural and conversational)\n\n'
            "Intent descriptions:\n"
            "1. **close**: Try to schedule a call or close the sale directly\n"
            "2. **nurture**: Answer their question/concern and keep the conversation flowing\n"
            "3. **qualify**: Ask strategic questions to understand if they're a good fit\n\n"
            "Rules:\n"
            "- Keep messages short (2-4 sentences max, this is Instagram DM)\n"
            "- Match the tone and language of the conversation\n"
            "- Be natural, not salesy\n"
            "- Reference specific things from their profile/bio/conversation when possible\n\n"
            "Return ONLY the JSON array, no markdown, no explanation."
        )

        try:
            client = self._get_anthropic_client()
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = response.content[0].text.strip()
            # Handle potential markdown code block wrapping
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
                raw_text = raw_text.rsplit("```", 1)[0].strip()

            suggestions = json.loads(raw_text)

            if not isinstance(suggestions, list) or len(suggestions) < 1:
                logger.warning(f"Invalid suggestions format for lead {lead_id}")
                return None

            # Store in DB
            sugg = ReplySuggestion(
                id=_uuid.uuid4(),
                lead_id=lead.id,
                suggestions=suggestions,
                generated_at=datetime.now(timezone.utc),
            )
            db.add(sugg)
            await db.commit()

            logger.info(f"Generated {len(suggestions)} reply suggestions for @{lead.ig_username}")
            return {
                "suggestions": suggestions,
                "generated_at": sugg.generated_at.isoformat(),
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse suggestions JSON for lead {lead_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to generate suggestions for lead {lead_id}: {type(e).__name__}: {e}")
            return None

    # ------------------------------------------------------------------ #
    # 5. Auto-suggest on new reply (called from inbox_tasks)
    # ------------------------------------------------------------------ #
    async def auto_suggest_on_new_reply(
        self, lead_id: str, db: AsyncSession,
    ) -> bool:
        """Pre-generate reply suggestions when a new reply is detected.

        Called automatically by inbox_tasks.py after classifying a reply.
        Returns True if suggestions were generated successfully.
        """
        lead = await db.get(Lead, lead_id)
        if not lead:
            return False

        # Only generate suggestions for actionable replies
        skip_classifications = {"spam", "not_interested"}
        if lead.reply_classification in skip_classifications:
            logger.info(
                f"Skipping auto-suggest for @{lead.ig_username} "
                f"(classification: {lead.reply_classification})"
            )
            return False

        # Also store the inbound reply in conversation_messages for thread tracking
        existing = await db.execute(
            select(ConversationMessage).where(
                ConversationMessage.lead_id == lead_id,
                ConversationMessage.direction == "inbound",
                ConversationMessage.content == lead.reply_text,
            )
        )
        if not existing.scalar_one_or_none() and lead.reply_text:
            conv_msg = ConversationMessage(
                id=_uuid.uuid4(),
                lead_id=lead.id,
                campaign_id=lead.campaign_id,
                client_id=lead.client_id,
                direction="inbound",
                message_type="reply",
                content=lead.reply_text,
                sent_at=lead.replied_at or datetime.now(timezone.utc),
            )
            db.add(conv_msg)

        # Also backfill the original outbound DM if not already stored
        existing_out = await db.execute(
            select(ConversationMessage).where(
                ConversationMessage.lead_id == lead_id,
                ConversationMessage.direction == "outbound",
                ConversationMessage.message_type == "dm",
            )
        )
        if not existing_out.scalar_one_or_none() and lead.dm_message:
            conv_msg_out = ConversationMessage(
                id=_uuid.uuid4(),
                lead_id=lead.id,
                campaign_id=lead.campaign_id,
                client_id=lead.client_id,
                direction="outbound",
                message_type="dm",
                content=lead.dm_message,
                variant_used=lead.dm_variant_used,
                sent_at=lead.sent_at or datetime.now(timezone.utc),
            )
            db.add(conv_msg_out)

        await db.commit()

        # Generate suggestions
        result = await self.generate_reply_suggestions(lead_id, db)
        return result is not None

    # ------------------------------------------------------------------ #
    # 6. Get pre-generated suggestions
    # ------------------------------------------------------------------ #
    async def get_suggestions(
        self, lead_id: str, db: AsyncSession,
    ) -> dict | None:
        """Get the latest pre-generated suggestions for a lead."""
        result = await db.execute(
            select(ReplySuggestion)
            .where(ReplySuggestion.lead_id == lead_id)
            .order_by(ReplySuggestion.generated_at.desc())
            .limit(1)
        )
        sugg = result.scalar_one_or_none()
        if not sugg:
            return None

        return {
            "suggestions": sugg.suggestions,
            "generated_at": sugg.generated_at.isoformat(),
            "was_used": sugg.was_used,
        }

    # ------------------------------------------------------------------ #
    # 7. Mark suggestion as used
    # ------------------------------------------------------------------ #
    async def mark_suggestion_used(
        self, lead_id: str, db: AsyncSession,
    ) -> None:
        """Mark the latest suggestion as used (for analytics)."""
        result = await db.execute(
            select(ReplySuggestion)
            .where(ReplySuggestion.lead_id == lead_id)
            .order_by(ReplySuggestion.generated_at.desc())
            .limit(1)
        )
        sugg = result.scalar_one_or_none()
        if sugg:
            sugg.was_used = True
            await db.commit()

    # ------------------------------------------------------------------ #
    # 8. Stats
    # ------------------------------------------------------------------ #
    async def get_stats(self, db: AsyncSession) -> dict:
        """Unread/unreplied counts and classification breakdown."""
        # Total conversations with replies waiting for our response
        unreplied = await db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.reply_text.isnot(None),
                Lead.conversation_status.in_(["replied", "pending", "awaiting_reply"]),
            )
        )
        unreplied_count = unreplied.scalar() or 0

        # Classification breakdown
        classif_result = await db.execute(
            select(
                Lead.reply_classification,
                func.count().label("count"),
            ).where(
                Lead.reply_text.isnot(None),
            ).group_by(Lead.reply_classification)
        )
        classifications = {
            row.reply_classification or "unknown": row.count
            for row in classif_result.all()
        }

        # Total conversations (leads with DMs sent)
        total = await db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.status.in_(["sent", "delivered", "failed"]),
                Lead.dm_message.isnot(None),
            )
        )
        total_count = total.scalar() or 0

        # Total with replies
        replied = await db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.reply_text.isnot(None),
            )
        )
        replied_count = replied.scalar() or 0

        return {
            "total_conversations": total_count,
            "total_replied": replied_count,
            "unreplied": unreplied_count,
            "classifications": classifications,
        }


unibox_service = UniboxService()

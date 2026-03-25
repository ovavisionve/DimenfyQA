import logging
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead
from app.schemas.enums import ConversationStatus, ReplyClassification
from app.services.dm_sender_service import DMSenderService, IGAccount
from app.services.webhook_service import webhook_service
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)

# Valid classification values for validation
VALID_CLASSIFICATIONS = {c.value for c in ReplyClassification}


class InboxService:
    """Monitor Instagram inbox for replies to sent DMs and classify them."""

    def __init__(self, dm_sender_service: DMSenderService | None = None):
        self._dm_sender = dm_sender_service
        self._anthropic_client: anthropic.Anthropic | None = None

    def _get_anthropic_client(self) -> anthropic.Anthropic:
        if self._anthropic_client is None:
            self._anthropic_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._anthropic_client

    def _get_dm_sender(self) -> DMSenderService:
        if self._dm_sender is None:
            from app.services.dm_sender_service import dm_sender_service
            self._dm_sender = dm_sender_service
        return self._dm_sender

    def check_inbox(self, ig_account: IGAccount) -> list[dict]:
        """Get recent DM threads from Instagram via instagrapi.

        Returns a list of dicts with keys:
            - thread_id: str
            - username: str (the other participant)
            - messages: list of {text, timestamp, is_me}
        """
        if not ig_account._logged_in:
            logger.warning(f"Cannot check inbox — @{ig_account.username} not logged in")
            return []

        try:
            threads = ig_account._client.direct_threads(amount=20)
        except Exception as e:
            logger.error(f"[@{ig_account.username}] Failed to fetch DM threads: {type(e).__name__}: {e}")
            return []

        result = []
        for thread in threads:
            # Get the other user in the conversation (skip group threads)
            other_users = [u for u in thread.users if u.username != ig_account.username]
            if not other_users:
                continue
            other_username = other_users[0].username

            messages = []
            for msg in (thread.messages or []):
                if msg.text:
                    is_me = str(msg.user_id) == str(ig_account._client.user_id)
                    messages.append({
                        "text": msg.text,
                        "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                        "is_me": is_me,
                    })

            result.append({
                "thread_id": str(thread.id),
                "username": other_username,
                "messages": messages,
            })

        logger.info(f"[@{ig_account.username}] Fetched {len(result)} DM threads")
        return result

    async def match_replies_to_leads(
        self,
        threads: list[dict],
        campaign_id: str,
        db: AsyncSession,
    ) -> list[dict]:
        """Match incoming messages to sent leads by username.

        Returns list of dicts: {lead, reply_text, thread_id}
        for leads that have a new reply (not already recorded).
        """
        # Get all sent leads for this campaign
        result = await db.execute(
            select(Lead).where(
                Lead.campaign_id == campaign_id,
                Lead.status == "sent",
            )
        )
        sent_leads = {lead.ig_username.lower(): lead for lead in result.scalars().all()}

        if not sent_leads:
            logger.info(f"No sent leads found for campaign {campaign_id}")
            return []

        matches = []
        for thread in threads:
            username = thread["username"].lower()
            if username not in sent_leads:
                continue

            lead = sent_leads[username]

            # Find the most recent message from the lead (not from us)
            incoming_messages = [m for m in thread["messages"] if not m["is_me"]]
            if not incoming_messages:
                continue

            # Use the most recent incoming message
            latest_reply = incoming_messages[0]
            reply_text = latest_reply["text"]

            # Skip if we already recorded this exact reply
            if lead.reply_text == reply_text:
                continue

            matches.append({
                "lead": lead,
                "reply_text": reply_text,
                "thread_id": thread["thread_id"],
            })

        logger.info(f"Matched {len(matches)} new replies for campaign {campaign_id}")
        return matches

    def classify_reply(self, reply_text: str) -> str:
        """Use Claude API to classify a reply into a category.

        Returns one of: positive, negative, question, not_interested, out_of_office, spam
        """
        if not reply_text or not reply_text.strip():
            return ReplyClassification.SPAM

        try:
            client = self._get_anthropic_client()
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=50,
                messages=[{
                    "role": "user",
                    "content": (
                        "Classify this Instagram DM reply into exactly one category. "
                        "Reply with ONLY the category name, nothing else.\n\n"
                        "Categories:\n"
                        "- positive (interested, wants to learn more, agrees to meeting/call)\n"
                        "- negative (rude rejection, hostile, angry)\n"
                        "- question (asking for more info, pricing, details)\n"
                        "- not_interested (polite decline, not relevant, no thanks)\n"
                        "- out_of_office (away, busy, will respond later)\n"
                        "- spam (irrelevant, gibberish, bot-like)\n\n"
                        f"Reply message: \"{reply_text}\"\n\n"
                        "Category:"
                    ),
                }],
            )
            classification = response.content[0].text.strip().lower().replace(" ", "_")

            # Validate the classification
            if classification not in VALID_CLASSIFICATIONS:
                logger.warning(f"Unexpected classification '{classification}', defaulting to 'question'")
                return ReplyClassification.QUESTION

            return classification

        except Exception as e:
            logger.error(f"Reply classification failed: {type(e).__name__}: {e}")
            # Default to question so the lead gets attention
            return ReplyClassification.QUESTION

    async def process_campaign_inbox(
        self,
        campaign_id: str,
        db: AsyncSession,
    ) -> dict:
        """Full inbox processing flow: check inbox -> match -> classify -> update leads.

        Returns dict with:
            - checked: bool
            - new_replies: int
            - classifications: dict of {classification: count}
            - errors: list of error strings
        """
        result = {
            "checked": False,
            "new_replies": 0,
            "classifications": {},
            "errors": [],
        }

        # Login to Instagram
        sender = self._get_dm_sender()
        logged_in = sender.login()
        if not logged_in:
            result["errors"].append("Instagram login failed — check credentials")
            return result

        # Check inbox from all logged-in accounts
        all_threads = []
        for account in sender._accounts:
            if account._logged_in and not account.is_blocked:
                threads = self.check_inbox(account)
                all_threads.extend(threads)

        result["checked"] = True

        if not all_threads:
            logger.info(f"No DM threads found for campaign {campaign_id}")
            return result

        # Match replies to sent leads
        matches = await self.match_replies_to_leads(all_threads, campaign_id, db)

        if not matches:
            logger.info(f"No new replies matched for campaign {campaign_id}")
            return result

        # Classify and update each matched lead
        for match in matches:
            lead: Lead = match["lead"]
            reply_text = match["reply_text"]

            try:
                classification = self.classify_reply(reply_text)

                lead.reply_text = reply_text
                lead.reply_classification = classification
                lead.replied_at = datetime.now(timezone.utc)
                lead.conversation_status = ConversationStatus.REPLIED

                # Track classification counts
                result["classifications"][classification] = (
                    result["classifications"].get(classification, 0) + 1
                )
                result["new_replies"] += 1

                logger.info(
                    f"Reply from @{lead.ig_username}: "
                    f"classification={classification}, text={reply_text[:80]}"
                )

                # Trigger webhook for reply received
                try:
                    await webhook_service.trigger_event(
                        client_id=str(lead.client_id),
                        event_type="reply.received",
                        payload={
                            "lead_id": str(lead.id),
                            "ig_username": lead.ig_username,
                            "campaign_id": str(lead.campaign_id),
                            "reply_text": reply_text[:500],
                            "classification": classification,
                        },
                        db=db,
                    )
                except Exception:
                    pass

                # Send in-app + Slack notification
                try:
                    await notification_service.on_reply_received(
                        db=db,
                        lead_username=lead.ig_username,
                        classification=classification,
                        campaign_id=str(lead.campaign_id),
                    )
                except Exception:
                    pass

            except Exception as e:
                error_msg = f"Error processing reply from @{lead.ig_username}: {e}"
                logger.error(error_msg)
                result["errors"].append(error_msg)

        await db.commit()

        # Save Instagram sessions
        sender.save_sessions()

        logger.info(
            f"Inbox check complete for campaign {campaign_id}: "
            f"{result['new_replies']} new replies"
        )
        return result


inbox_service = InboxService()

import asyncio
import json
import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead

logger = logging.getLogger(__name__)

# Max send attempts before giving up on a lead
MAX_SEND_ATTEMPTS = 3


class DMSenderService:
    """Send Instagram DMs via instagrapi with rate limiting and session persistence."""

    def __init__(self):
        self._client = None
        self._logged_in = False
        self._session_path = Path(settings.IG_SESSION_DIR)
        self._session_path.mkdir(parents=True, exist_ok=True)

    def _get_session_file(self) -> Path:
        return self._session_path / f"{settings.IG_USERNAME}_session.json"

    def _ensure_client(self):
        """Lazily import and create instagrapi Client."""
        if self._client is None:
            from instagrapi import Client
            self._client = Client()
            if settings.PROXY_URL:
                self._client.set_proxy(settings.PROXY_URL)

    def login(self) -> bool:
        """Login to Instagram, restoring session if available."""
        if self._logged_in:
            return True

        if not settings.IG_USERNAME or not settings.IG_PASSWORD:
            logger.error("IG_USERNAME or IG_PASSWORD not configured")
            return False

        self._ensure_client()
        session_file = self._get_session_file()

        # Try to restore saved session first
        if session_file.exists():
            try:
                self._client.load_settings(session_file)
                self._client.login(settings.IG_USERNAME, settings.IG_PASSWORD)
                self._client.get_timeline_feed()  # Validate session
                self._logged_in = True
                logger.info(f"Restored Instagram session for @{settings.IG_USERNAME}")
                return True
            except Exception as e:
                logger.warning(f"Session restore failed ({type(e).__name__}), doing fresh login")
                session_file.unlink(missing_ok=True)

        # Fresh login
        try:
            self._client.login(settings.IG_USERNAME, settings.IG_PASSWORD)
            self._client.dump_settings(session_file)
            self._logged_in = True
            logger.info(f"Fresh login successful for @{settings.IG_USERNAME}")
            return True
        except Exception as e:
            logger.error(f"Instagram login failed: {type(e).__name__}: {e}")
            return False

    def send_dm(self, username: str, message: str) -> dict:
        """Send a DM to a single user. Returns dict with status info."""
        if not self._logged_in:
            return {"success": False, "error": "Not logged in"}

        try:
            user_id = self._client.user_id_from_username(username)
            result = self._client.direct_send(message, [int(user_id)])
            logger.info(f"DM sent to @{username}")
            return {"success": True, "thread_id": str(result.id) if result else None}
        except Exception as e:
            error_type = type(e).__name__
            error_msg = f"{error_type}: {e}"
            logger.error(f"Failed to send DM to @{username}: {error_msg}")

            # Detect challenge/block scenarios
            is_challenge = "challenge" in str(e).lower() or "checkpoint" in str(e).lower()
            is_block = "block" in str(e).lower() or "feedback_required" in str(e).lower()

            return {
                "success": False,
                "error": error_msg[:500],
                "is_challenge": is_challenge,
                "is_block": is_block,
            }

    def save_session(self):
        """Persist session to disk."""
        if self._client and self._logged_in:
            try:
                self._client.dump_settings(self._get_session_file())
            except Exception as e:
                logger.warning(f"Failed to save session: {e}")

    async def get_daily_send_count(self, db: AsyncSession) -> int:
        """Count DMs sent today for rate limiting."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.status == "sent",
                Lead.sent_at >= today_start,
            )
        )
        return result.scalar() or 0

    async def get_next_leads_to_send(
        self, campaign_id: str, db: AsyncSession, limit: int = 10
    ) -> list[Lead]:
        """Get next batch of leads ready to send, ordered by score DESC."""
        result = await db.execute(
            select(Lead).where(
                Lead.campaign_id == campaign_id,
                Lead.status.in_(["dm_ready", "retry"]),
                Lead.send_attempts < MAX_SEND_ATTEMPTS,
            ).order_by(Lead.score.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def send_campaign_dms(
        self,
        campaign_id: str,
        db: AsyncSession,
        progress_callback=None,
    ) -> dict:
        """Send DMs for a campaign with rate limiting and random delays.

        Returns dict with sent_count, failed_count, paused (bool), reason.
        """
        daily_count = await self.get_daily_send_count(db)
        daily_limit = settings.DAILY_DM_LIMIT

        if daily_count >= daily_limit:
            logger.warning(f"Daily DM limit reached ({daily_count}/{daily_limit})")
            return {
                "sent_count": 0,
                "failed_count": 0,
                "paused": True,
                "reason": f"Daily limit reached ({daily_count}/{daily_limit})",
            }

        remaining_today = daily_limit - daily_count
        leads = await self.get_next_leads_to_send(campaign_id, db, limit=remaining_today)

        if not leads:
            logger.info(f"No leads ready to send for campaign {campaign_id}")
            return {"sent_count": 0, "failed_count": 0, "paused": False, "reason": "No leads to send"}

        logger.info(f"Sending DMs to {len(leads)} leads (daily: {daily_count}/{daily_limit})")

        sent_count = 0
        failed_count = 0

        for i, lead in enumerate(leads):
            # Pick DM variant (A by default, B if A already failed)
            if lead.dm_variant_used == "A" and lead.dm_variant_b:
                message = lead.dm_variant_b
                variant = "B"
            else:
                message = lead.dm_message
                variant = "A"

            if not message:
                logger.warning(f"No DM message for @{lead.ig_username}, skipping")
                lead.status = "failed"
                lead.send_error = "No DM message available"
                failed_count += 1
                continue

            # Mark as sending
            lead.status = "sending"
            lead.dm_variant_used = variant
            await db.commit()

            # Send the DM
            result = self.send_dm(lead.ig_username, message)

            if result["success"]:
                lead.status = "sent"
                lead.sent_at = datetime.now(timezone.utc)
                lead.delivery_status = "sent"
                lead.send_error = None
                sent_count += 1
                logger.info(f"Sent DM ({variant}) to @{lead.ig_username} [{sent_count}/{len(leads)}]")
            else:
                lead.send_attempts += 1
                lead.send_error = result.get("error", "Unknown error")

                # Challenge or block → pause the whole campaign
                if result.get("is_challenge") or result.get("is_block"):
                    lead.status = "retry"
                    lead.delivery_status = "challenge" if result.get("is_challenge") else "blocked"
                    await db.commit()
                    reason = "Instagram challenge detected" if result.get("is_challenge") else "Account blocked"
                    logger.warning(f"Pausing campaign: {reason}")
                    return {
                        "sent_count": sent_count,
                        "failed_count": failed_count,
                        "paused": True,
                        "reason": reason,
                    }

                if lead.send_attempts >= MAX_SEND_ATTEMPTS:
                    lead.status = "failed"
                    lead.delivery_status = "max_attempts"
                    failed_count += 1
                else:
                    lead.status = "retry"
                    lead.delivery_status = "retry"

            await db.commit()

            if progress_callback:
                try:
                    progress_callback(i + 1, len(leads), lead.ig_username, result["success"])
                except Exception:
                    pass

            # Random delay between sends (skip after last one)
            if i < len(leads) - 1:
                delay = random.uniform(settings.DM_DELAY_MIN, settings.DM_DELAY_MAX)
                logger.debug(f"Waiting {delay:.1f}s before next DM")
                await asyncio.sleep(delay)

        self.save_session()

        return {
            "sent_count": sent_count,
            "failed_count": failed_count,
            "paused": False,
            "reason": "Batch complete",
        }


dm_sender_service = DMSenderService()

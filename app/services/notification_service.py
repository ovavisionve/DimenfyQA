"""Notification service — in-app + Slack notifications.

Creates in-app notifications (stored in DB, shown in dashboard dropdown)
and optionally forwards them to Slack via incoming webhook.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import Notification

logger = logging.getLogger(__name__)


# Maps internal levels to Slack emoji
_SLACK_EMOJI = {
    "success": ":white_check_mark:",
    "info": ":information_source:",
    "warning": ":warning:",
    "error": ":x:",
}


class NotificationService:
    """Dual-channel notification: DB (dashboard) + Slack webhook."""

    # ------------------------------------------------------------------ #
    # Core: create in-app notification
    # ------------------------------------------------------------------ #
    async def notify(
        self,
        db: AsyncSession,
        title: str,
        message: str,
        level: str = "info",
        link: Optional[str] = None,
        slack: bool = True,
    ) -> Notification:
        """Create an in-app notification and optionally send to Slack.

        Args:
            db: async DB session
            title: short title (shown in dropdown)
            message: longer detail text
            level: info | warning | error | success
            link: optional dashboard link (e.g. /campaigns/{id})
            slack: whether to also send to Slack (default True)
        """
        notif = Notification(
            title=title,
            message=message,
            level=level,
            link=link,
        )
        db.add(notif)
        await db.flush()
        await db.refresh(notif)

        if slack and settings.SLACK_WEBHOOK_URL:
            await self._send_slack(title, message, level, link)

        return notif

    # ------------------------------------------------------------------ #
    # Pipeline events — convenience methods
    # ------------------------------------------------------------------ #
    async def on_campaign_started(self, db: AsyncSession, campaign_name: str, campaign_id: str) -> None:
        await self.notify(
            db, title="Campaign Started",
            message=f"Pipeline started for *{campaign_name}*",
            level="info",
            link=f"/campaigns/{campaign_id}",
        )

    async def on_campaign_completed(self, db: AsyncSession, campaign_name: str, campaign_id: str, stats: dict) -> None:
        leads = stats.get("total_leads", "?")
        sent = stats.get("sent", "?")
        await self.notify(
            db, title="Campaign Completed",
            message=f"*{campaign_name}* finished — {leads} leads, {sent} DMs sent",
            level="success",
            link=f"/campaigns/{campaign_id}",
        )

    async def on_campaign_failed(self, db: AsyncSession, campaign_name: str, campaign_id: str, error: str) -> None:
        await self.notify(
            db, title="Campaign Failed",
            message=f"*{campaign_name}* failed: {error}",
            level="error",
            link=f"/campaigns/{campaign_id}",
        )

    async def on_reply_received(
        self, db: AsyncSession, lead_username: str, classification: str, campaign_id: str,
    ) -> None:
        await self.notify(
            db, title="New Reply",
            message=f"@{lead_username} replied ({classification})",
            level="success" if classification == "positive" else "info",
            link=f"/campaigns/{campaign_id}",
        )

    async def on_account_blocked(self, db: AsyncSession, ig_username: str, reason: str) -> None:
        await self.notify(
            db, title="Account Blocked",
            message=f"@{ig_username} blocked: {reason}",
            level="error",
        )

    async def on_daily_summary(
        self, db: AsyncSession, dms_sent: int, replies: int, new_leads: int,
    ) -> None:
        await self.notify(
            db, title="Daily Summary",
            message=f"Today: {dms_sent} DMs sent, {replies} replies, {new_leads} new leads",
            level="info",
        )

    # ------------------------------------------------------------------ #
    # Slack integration
    # ------------------------------------------------------------------ #
    async def _send_slack(
        self, title: str, message: str, level: str, link: Optional[str] = None,
    ) -> None:
        """Send a message to Slack via incoming webhook."""
        url = settings.SLACK_WEBHOOK_URL
        if not url:
            return

        emoji = _SLACK_EMOJI.get(level, ":bell:")
        text = f"{emoji} *{title}*\n{message}"
        if link:
            text += f"\n<{link}|View in dashboard>"

        payload = {"text": text}

        # Add channel override if configured
        if settings.SLACK_CHANNEL:
            payload["channel"] = settings.SLACK_CHANNEL

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if not resp.is_success:
                    logger.warning(f"Slack webhook returned {resp.status_code}: {resp.text[:200]}")
        except httpx.TimeoutException:
            logger.warning("Slack webhook timed out")
        except Exception as e:
            logger.error(f"Slack webhook failed: {type(e).__name__}: {e}")


notification_service = NotificationService()

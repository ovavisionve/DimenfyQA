"""WhatsApp notification service via Twilio API.

Sends WhatsApp messages for campaign events, reply alerts, and account health.
Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and WHATSAPP_ENABLED=true.
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "+14155238886")
WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"


class WhatsAppNotificationService:
    """Sends WhatsApp notifications via the Twilio Messages API."""

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
        enabled: Optional[bool] = None,
    ):
        self.account_sid = account_sid or TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or TWILIO_AUTH_TOKEN
        self.from_number = from_number or TWILIO_WHATSAPP_FROM
        self.enabled = enabled if enabled is not None else WHATSAPP_ENABLED

    def _is_configured(self) -> bool:
        """Check if WhatsApp notifications are enabled and credentials exist."""
        if not self.enabled:
            return False
        if not self.account_sid or not self.auth_token:
            logger.warning("WhatsApp enabled but missing Twilio credentials")
            return False
        return True

    async def send_message(self, to: str, body: str) -> bool:
        """Send a WhatsApp message via Twilio API.

        Args:
            to: Recipient phone number (E.164 format, e.g. "+5491155551234").
            body: Message text.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._is_configured():
            return False

        url = (
            f"https://api.twilio.com/2010-04-01/Accounts"
            f"/{self.account_sid}/Messages.json"
        )

        data = {
            "From": f"whatsapp:{self.from_number}",
            "To": f"whatsapp:{to}",
            "Body": body,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    data=data,
                    auth=(self.account_sid, self.auth_token),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=15.0,
                )

            if response.status_code in (200, 201):
                logger.info("WhatsApp message sent to %s", to)
                return True

            logger.error(
                "Twilio API error %s: %s", response.status_code, response.text
            )
            return False

        except httpx.HTTPError as exc:
            logger.error("WhatsApp send failed: %s", exc)
            return False
        except Exception as exc:
            logger.error("Unexpected error sending WhatsApp: %s", exc)
            return False

    async def send_campaign_completed(
        self, to: str, campaign_name: str, stats: dict
    ) -> bool:
        """Notify that a campaign has finished sending.

        Args:
            to: Recipient phone number.
            campaign_name: Name of the completed campaign.
            stats: Dict with campaign statistics (e.g. sent, failed, skipped).
        """
        sent = stats.get("sent", 0)
        failed = stats.get("failed", 0)
        total = stats.get("total", sent + failed)

        body = (
            f"Campaign completed: {campaign_name}\n"
            f"Sent: {sent}/{total}"
        )
        if failed:
            body += f" | Failed: {failed}"

        return await self.send_message(to, body)

    async def send_reply_received(
        self, to: str, lead_username: str, reply_text: str
    ) -> bool:
        """Notify that a lead has replied to a DM.

        Args:
            to: Recipient phone number.
            lead_username: Instagram username of the lead.
            reply_text: The reply message text.
        """
        preview = reply_text[:200] if reply_text else "(empty)"
        body = f"New reply from @{lead_username}:\n{preview}"
        return await self.send_message(to, body)

    async def send_account_blocked(
        self, to: str, account_username: str
    ) -> bool:
        """Notify that an Instagram account has been blocked.

        Args:
            to: Recipient phone number.
            account_username: The blocked Instagram account username.
        """
        body = (
            f"ALERT: Instagram account @{account_username} has been blocked. "
            f"The account is now in cooldown."
        )
        return await self.send_message(to, body)

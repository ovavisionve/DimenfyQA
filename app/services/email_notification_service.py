"""Email notification service — sends transactional emails via SendGrid or Resend.

Reads configuration from environment variables:
- EMAIL_API_KEY: API key for the email provider
- EMAIL_FROM: sender address (default: noreply@igdmengine.com)
- EMAIL_PROVIDER: "sendgrid" or "resend" (default: resend)
- EMAIL_ENABLED: "true" to enable, anything else disables (default: false)

If EMAIL_ENABLED is not "true" or EMAIL_API_KEY is missing, all methods
return False silently without raising errors.
"""

import os
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
RESEND_URL = "https://api.resend.com/emails"


class EmailNotificationService:
    """Sends transactional email notifications via HTTP (SendGrid or Resend)."""

    def __init__(self) -> None:
        self.api_key: str = os.getenv("EMAIL_API_KEY", "")
        self.from_email: str = os.getenv("EMAIL_FROM", "noreply@igdmengine.com")
        self.provider: str = os.getenv("EMAIL_PROVIDER", "resend").lower()
        self.enabled: bool = os.getenv("EMAIL_ENABLED", "false").lower() == "true"

    # ------------------------------------------------------------------ #
    # Core send method
    # ------------------------------------------------------------------ #

    async def send_email(self, to: str, subject: str, html_body: str) -> bool:
        """Send an email via the configured provider.

        Returns True on success, False on failure or if disabled.
        """
        if not self.enabled or not self.api_key:
            return False

        try:
            if self.provider == "sendgrid":
                return await self._send_via_sendgrid(to, subject, html_body)
            else:
                return await self._send_via_resend(to, subject, html_body)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Email API returned error status %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return False
        except httpx.RequestError as exc:
            logger.error("Email request failed: %s", exc)
            return False
        except Exception as exc:
            logger.error("Unexpected error sending email: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Provider-specific implementations
    # ------------------------------------------------------------------ #

    async def _send_via_sendgrid(
        self, to: str, subject: str, html_body: str
    ) -> bool:
        payload: dict[str, Any] = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": self.from_email},
            "subject": subject,
            "content": [{"type": "text/html", "value": html_body}],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(SENDGRID_URL, json=payload, headers=headers)
            resp.raise_for_status()
        logger.info("Email sent via SendGrid to %s — subject: %s", to, subject)
        return True

    async def _send_via_resend(
        self, to: str, subject: str, html_body: str
    ) -> bool:
        payload: dict[str, Any] = {
            "from": self.from_email,
            "to": [to],
            "subject": subject,
            "html": html_body,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(RESEND_URL, json=payload, headers=headers)
            resp.raise_for_status()
        logger.info("Email sent via Resend to %s — subject: %s", to, subject)
        return True

    # ------------------------------------------------------------------ #
    # Convenience methods for common notification types
    # ------------------------------------------------------------------ #

    async def send_campaign_completed(
        self, to: str, campaign_name: str, stats: dict
    ) -> bool:
        """Notify that a campaign has finished sending all DMs."""
        total = stats.get("total", 0)
        sent = stats.get("sent", 0)
        failed = stats.get("failed", 0)

        subject = f"Campaign Completed: {campaign_name}"
        html_body = (
            f"<h2>Campaign Completed</h2>"
            f"<p>The campaign <strong>{campaign_name}</strong> has finished.</p>"
            f"<table style='border-collapse:collapse;'>"
            f"<tr><td style='padding:4px 12px;'>Total leads</td>"
            f"<td style='padding:4px 12px;'><strong>{total}</strong></td></tr>"
            f"<tr><td style='padding:4px 12px;'>Sent</td>"
            f"<td style='padding:4px 12px;'><strong>{sent}</strong></td></tr>"
            f"<tr><td style='padding:4px 12px;'>Failed</td>"
            f"<td style='padding:4px 12px;'><strong>{failed}</strong></td></tr>"
            f"</table>"
        )
        return await self.send_email(to, subject, html_body)

    async def send_reply_received(
        self,
        to: str,
        lead_username: str,
        reply_text: str,
        campaign_name: str,
    ) -> bool:
        """Notify that a lead has replied to a DM."""
        subject = f"New Reply from @{lead_username}"
        html_body = (
            f"<h2>New Reply Received</h2>"
            f"<p><strong>@{lead_username}</strong> replied in campaign "
            f"<em>{campaign_name}</em>:</p>"
            f"<blockquote style='border-left:3px solid #f59e0b;padding:8px 12px;"
            f"background:#fffbeb;'>{reply_text}</blockquote>"
        )
        return await self.send_email(to, subject, html_body)

    async def send_account_blocked(self, to: str, account_username: str) -> bool:
        """Notify that an Instagram account has been blocked."""
        subject = f"Account Blocked: @{account_username}"
        html_body = (
            f"<h2 style='color:#dc2626;'>Account Blocked</h2>"
            f"<p>The Instagram account <strong>@{account_username}</strong> "
            f"has been blocked by Instagram.</p>"
            f"<p>The account has been placed in cooldown. No DMs will be sent "
            f"from this account until the cooldown period expires.</p>"
        )
        return await self.send_email(to, subject, html_body)

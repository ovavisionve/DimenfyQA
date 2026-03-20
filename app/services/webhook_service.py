import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import Webhook
from app.schemas.webhook import WebhookCreate, WebhookUpdate

logger = logging.getLogger(__name__)

# Auto-disable webhook after this many consecutive failures
MAX_FAILURE_COUNT = 10


class WebhookService:
    VALID_EVENTS = [
        "lead.scraped",
        "lead.scored",
        "lead.researched",
        "dm.generated",
        "dm.sent",
        "dm.failed",
        "reply.received",
        "campaign.completed",
        "campaign.failed",
    ]

    async def create_webhook(
        self, client_id: str, data: WebhookCreate, db: AsyncSession
    ) -> Webhook:
        """Create a new webhook for a client."""
        # Validate events
        for event in data.events:
            if event not in self.VALID_EVENTS:
                raise ValueError(f"Invalid event type: {event}. Valid events: {self.VALID_EVENTS}")

        webhook = Webhook(
            client_id=client_id,
            url=data.url,
            secret=data.secret,
            events=",".join(data.events),
            is_active=True,
        )
        db.add(webhook)
        await db.flush()
        await db.refresh(webhook)
        return webhook

    async def list_webhooks(self, client_id: str, db: AsyncSession) -> list[Webhook]:
        """List all webhooks for a client."""
        result = await db.execute(
            select(Webhook).where(Webhook.client_id == client_id)
        )
        return list(result.scalars().all())

    async def update_webhook(
        self, webhook_id: str, data: WebhookUpdate, db: AsyncSession
    ) -> Webhook:
        """Update a webhook."""
        result = await db.execute(
            select(Webhook).where(Webhook.id == webhook_id)
        )
        webhook = result.scalar_one_or_none()
        if not webhook:
            raise ValueError("Webhook not found")

        if data.url is not None:
            webhook.url = data.url
        if data.events is not None:
            for event in data.events:
                if event not in self.VALID_EVENTS:
                    raise ValueError(f"Invalid event type: {event}")
            webhook.events = ",".join(data.events)
        if data.is_active is not None:
            webhook.is_active = data.is_active
            # Reset failure count when re-enabling
            if data.is_active:
                webhook.failure_count = 0

        await db.flush()
        await db.refresh(webhook)
        return webhook

    async def delete_webhook(self, webhook_id: str, db: AsyncSession) -> None:
        """Delete a webhook."""
        result = await db.execute(
            select(Webhook).where(Webhook.id == webhook_id)
        )
        webhook = result.scalar_one_or_none()
        if not webhook:
            raise ValueError("Webhook not found")

        await db.delete(webhook)
        await db.flush()

    async def test_webhook(self, webhook_id: str, db: AsyncSession) -> dict:
        """Send a test event to verify the webhook works."""
        result = await db.execute(
            select(Webhook).where(Webhook.id == webhook_id)
        )
        webhook = result.scalar_one_or_none()
        if not webhook:
            raise ValueError("Webhook not found")

        test_payload = {
            "event": "webhook.test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "message": "This is a test event from IG DM Engine",
                "webhook_id": str(webhook.id),
            },
        }

        return await self._send_webhook(webhook, "webhook.test", test_payload, db)

    async def trigger_event(
        self, client_id: str, event_type: str, payload: dict, db: AsyncSession
    ) -> None:
        """Find all active webhooks for client subscribed to this event, send POST to each."""
        if event_type not in self.VALID_EVENTS:
            logger.warning(f"Unknown webhook event type: {event_type}")
            return

        # Query active webhooks for this client
        result = await db.execute(
            select(Webhook).where(
                Webhook.client_id == client_id,
                Webhook.is_active == True,  # noqa: E712
            )
        )
        webhooks = result.scalars().all()

        for webhook in webhooks:
            # Check if webhook is subscribed to this event type
            subscribed_events = webhook.events.split(",") if webhook.events else []
            if event_type not in subscribed_events:
                continue

            event_body = {
                "event": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": payload,
            }

            try:
                await self._send_webhook(webhook, event_type, event_body, db)
            except Exception as e:
                logger.error(f"Webhook trigger failed for {webhook.id}: {type(e).__name__}: {e}")

    async def _send_webhook(
        self, webhook: Webhook, event_type: str, body: dict, db: AsyncSession
    ) -> dict:
        """Send a POST request to a webhook URL."""
        headers = {"Content-Type": "application/json"}

        # Add HMAC signature if secret is configured
        body_bytes = json.dumps(body).encode("utf-8")
        if webhook.secret:
            signature = hmac.new(
                webhook.secret.encode("utf-8"),
                body_bytes,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = signature

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook.url,
                    content=body_bytes,
                    headers=headers,
                )

            webhook.last_triggered_at = datetime.now(timezone.utc)
            webhook.last_status_code = response.status_code

            if response.is_success:
                webhook.failure_count = 0
                logger.info(
                    f"Webhook {webhook.id} triggered ({event_type}): "
                    f"status={response.status_code}"
                )
            else:
                webhook.failure_count += 1
                logger.warning(
                    f"Webhook {webhook.id} returned {response.status_code} "
                    f"(failure #{webhook.failure_count})"
                )

            # Auto-disable after too many failures
            if webhook.failure_count > MAX_FAILURE_COUNT:
                webhook.is_active = False
                logger.warning(
                    f"Webhook {webhook.id} auto-disabled after "
                    f"{webhook.failure_count} consecutive failures"
                )

            await db.flush()

            return {
                "success": response.is_success,
                "status_code": response.status_code,
                "response_body": response.text[:500],
            }

        except httpx.TimeoutException:
            webhook.last_triggered_at = datetime.now(timezone.utc)
            webhook.failure_count += 1

            if webhook.failure_count > MAX_FAILURE_COUNT:
                webhook.is_active = False
                logger.warning(f"Webhook {webhook.id} auto-disabled after timeout failures")

            await db.flush()

            logger.warning(f"Webhook {webhook.id} timed out ({event_type})")
            return {"success": False, "status_code": None, "error": "Timeout"}

        except Exception as e:
            webhook.last_triggered_at = datetime.now(timezone.utc)
            webhook.failure_count += 1

            if webhook.failure_count > MAX_FAILURE_COUNT:
                webhook.is_active = False

            await db.flush()

            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"Webhook {webhook.id} failed ({event_type}): {error_msg}")
            return {"success": False, "status_code": None, "error": error_msg}


webhook_service = WebhookService()

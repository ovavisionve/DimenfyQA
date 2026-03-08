import asyncio
import logging

import anthropic
import httpx

from app.tasks.celery_app import celery_app
from app.database import create_worker_session

logger = logging.getLogger(__name__)

# Exceptions that should trigger automatic retry (transient errors)
RETRIABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.HTTPStatusError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)

# Default retry settings for all pipeline tasks
RETRY_KWARGS = {
    "autoretry_for": RETRIABLE_EXCEPTIONS,
    "max_retries": 3,
    "retry_backoff": True,
    "retry_backoff_max": 300,
    "retry_jitter": True,
}


def _run_async(coro):
    """Run async code in synchronous Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _set_campaign_failed(campaign_id: str, error_msg: str):
    """Mark a campaign as failed with an error message in stats."""
    async with create_worker_session()() as db:
        from sqlalchemy import select
        from app.models.campaign import Campaign

        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if campaign:
            campaign.status = "failed"
            stats = campaign.stats or {}
            stats["error"] = error_msg[:500]
            campaign.stats = stats
            await db.commit()
            logger.error(f"Campaign {campaign_id} marked as failed: {error_msg}")


async def _get_campaign_id_from_leads(lead_ids: list[str]) -> str | None:
    """Look up campaign_id from lead_ids."""
    if not lead_ids:
        return None
    async with create_worker_session()() as db:
        from sqlalchemy import select
        from app.models.lead import Lead

        result = await db.execute(
            select(Lead.campaign_id).where(Lead.id == lead_ids[0])
        )
        return str(result.scalar_one_or_none()) if result.scalar_one_or_none else None


def fail_campaign(campaign_id: str, error_msg: str):
    """Sync wrapper to mark campaign as failed."""
    _run_async(_set_campaign_failed(campaign_id, error_msg))


async def _update_progress(campaign_id: str, progress: dict):
    """Update campaign.stats with progress info for the frontend."""
    async with create_worker_session()() as db:
        from sqlalchemy import select
        from app.models.campaign import Campaign

        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if campaign:
            stats = dict(campaign.stats or {})
            stats["progress"] = progress
            campaign.stats = stats
            await db.commit()


async def update_progress(campaign_id: str, phase: str, message: str,
                          current: int = 0, total: int = 0, detail: str = ""):
    """Async function to update campaign progress. Must be awaited from async task context."""
    progress = {
        "phase": phase,
        "message": message,
        "current": current,
        "total": total,
        "detail": detail,
    }
    await _update_progress(campaign_id, progress)


def sync_update_progress(campaign_id: str, phase: str, message: str,
                         current: int = 0, total: int = 0, detail: str = ""):
    """Sync version for use in ThreadPoolExecutor callbacks (runs in separate thread)."""
    progress = {
        "phase": phase,
        "message": message,
        "current": current,
        "total": total,
        "detail": detail,
    }
    _run_async(_update_progress(campaign_id, progress))

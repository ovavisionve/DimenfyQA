import logging

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, fail_campaign, RETRY_KWARGS
from app.database import async_session
from app.services.copywriting_service import copywriting_service

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="write_dms", **RETRY_KWARGS)
def write_dms_task(self, lead_ids: list[str]) -> list[str]:
    """Generate DMs for leads with score >= threshold. Returns dm-ready lead_ids."""
    logger.info(f"Writing DMs for {len(lead_ids)} candidates (attempt {self.request.retries + 1}/{self.max_retries + 1})")

    async def _write():
        async with async_session() as db:
            from sqlalchemy import select
            from app.models.lead import Lead
            from app.models.campaign import Campaign

            campaign_id = None

            # Update campaign status to "writing"
            if lead_ids:
                result = await db.execute(
                    select(Lead.campaign_id).where(Lead.id == lead_ids[0])
                )
                campaign_id = result.scalar_one_or_none()
                if campaign_id:
                    campaign_result = await db.execute(
                        select(Campaign).where(Campaign.id == str(campaign_id))
                    )
                    campaign = campaign_result.scalar_one_or_none()
                    if campaign:
                        campaign.status = "writing"
                        await db.flush()

            dm_ready_ids = await copywriting_service.write_dms_batch(lead_ids, db)

            # Update campaign to "ready"
            if campaign_id:
                campaign_result = await db.execute(
                    select(Campaign).where(Campaign.id == str(campaign_id))
                )
                campaign = campaign_result.scalar_one_or_none()
                if campaign:
                    campaign.status = "ready"

            await db.commit()
            logger.info(f"Generated DMs for {len(dm_ready_ids)} leads")
            return dm_ready_ids

    try:
        return _run_async(_write())
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            try:
                async def _get_campaign():
                    async with async_session() as db:
                        from sqlalchemy import select
                        from app.models.lead import Lead
                        result = await db.execute(
                            select(Lead.campaign_id).where(Lead.id == lead_ids[0])
                        )
                        return str(result.scalar_one_or_none())
                campaign_id = _run_async(_get_campaign()) if lead_ids else None
                if campaign_id:
                    fail_campaign(campaign_id, f"DM generation failed after {self.max_retries + 1} attempts: {exc}")
            except Exception:
                logger.exception("Could not mark campaign as failed")
        raise

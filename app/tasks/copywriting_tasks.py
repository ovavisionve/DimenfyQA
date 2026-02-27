import asyncio
import logging

from app.tasks.celery_app import celery_app
from app.database import async_session
from app.services.copywriting_service import copywriting_service

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="write_dms")
def write_dms_task(self, lead_ids: list[str]) -> list[str]:
    """Generate DMs for leads with score >= threshold. Returns dm-ready lead_ids."""
    logger.info(f"Writing DMs for leads from {len(lead_ids)} candidates")

    async def _write():
        async with async_session() as db:
            # Update campaign status
            if lead_ids:
                from sqlalchemy import select
                from app.models.lead import Lead
                from app.models.campaign import Campaign

                result = await db.execute(
                    select(Lead.campaign_id).where(Lead.id == lead_ids[0])
                )
                campaign_id = result.scalar_one_or_none()
                if campaign_id:
                    campaign_result = await db.execute(
                        select(Campaign).where(Campaign.id == campaign_id)
                    )
                    campaign = campaign_result.scalar_one_or_none()
                    if campaign:
                        campaign.status = "writing"
                        await db.flush()

            dm_ready_ids = await copywriting_service.write_dms_batch(lead_ids, db)

            # Update campaign to ready
            if lead_ids:
                result = await db.execute(
                    select(Lead.campaign_id).where(Lead.id == lead_ids[0])
                )
                campaign_id = result.scalar_one_or_none()
                if campaign_id:
                    campaign_result = await db.execute(
                        select(Campaign).where(Campaign.id == campaign_id)
                    )
                    campaign = campaign_result.scalar_one_or_none()
                    if campaign:
                        campaign.status = "ready"

            await db.commit()
            logger.info(f"Generated DMs for {len(dm_ready_ids)} leads")
            return dm_ready_ids

    return _run_async(_write())

import asyncio
import logging

from app.tasks.celery_app import celery_app
from app.database import async_session
from app.services.scoring_service import scoring_service

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="score_leads")
def score_leads_task(self, lead_ids: list[str]) -> list[str]:
    """Score a batch of leads. Returns all lead_ids (scored and unscored)."""
    logger.info(f"Scoring {len(lead_ids)} leads")

    async def _score():
        async with async_session() as db:
            # Update campaign status
            if lead_ids:
                from sqlalchemy import select
                from app.models.lead import Lead
                result = await db.execute(
                    select(Lead.campaign_id).where(Lead.id == lead_ids[0])
                )
                campaign_id = result.scalar_one_or_none()
                if campaign_id:
                    from app.models.campaign import Campaign
                    campaign_result = await db.execute(
                        select(Campaign).where(Campaign.id == campaign_id)
                    )
                    campaign = campaign_result.scalar_one_or_none()
                    if campaign:
                        campaign.status = "scoring"
                        await db.flush()

            scored_ids = await scoring_service.score_leads_batch(lead_ids, db)
            await db.commit()
            logger.info(f"Scored {len(scored_ids)} leads")
            return scored_ids

    return _run_async(_score())

import logging

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, fail_campaign, RETRY_KWARGS
from app.database import async_session
from app.services.scoring_service import scoring_service

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="score_leads", **RETRY_KWARGS)
def score_leads_task(self, lead_ids: list[str]) -> list[str]:
    """Score a batch of leads. Returns all lead_ids (scored and unscored)."""
    logger.info(f"Scoring {len(lead_ids)} leads (attempt {self.request.retries + 1}/{self.max_retries + 1})")

    async def _score():
        async with async_session() as db:
            campaign_id = None

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
                        select(Campaign).where(Campaign.id == str(campaign_id))
                    )
                    campaign = campaign_result.scalar_one_or_none()
                    if campaign:
                        campaign.status = "scoring"
                        await db.flush()

            scored_ids = await scoring_service.score_leads_batch(lead_ids, db)
            await db.commit()
            logger.info(f"Scored {len(scored_ids)} leads")
            # Return ALL lead_ids so next step can filter by score
            return lead_ids

    try:
        return _run_async(_score())
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            # Try to find campaign_id from leads to mark it failed
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
                    fail_campaign(campaign_id, f"Scoring failed after {self.max_retries + 1} attempts: {exc}")
            except Exception:
                logger.exception("Could not mark campaign as failed")
        raise

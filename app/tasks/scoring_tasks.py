import logging

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, fail_campaign, update_progress, RETRY_KWARGS
from app.database import create_worker_session
from app.services.scoring_service import scoring_service

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="score_leads", **RETRY_KWARGS)
def score_leads_task(self, lead_ids: list[str]) -> list[str]:
    """Score a batch of leads. Returns all lead_ids (scored and unscored)."""
    logger.info(f"Scoring {len(lead_ids)} leads (attempt {self.request.retries + 1}/{self.max_retries + 1})")

    async def _score():
        async with create_worker_session()() as db:
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

            cid = str(campaign_id) if campaign_id else None
            if cid:
                update_progress(cid, "scoring",
                                f"Scoring {len(lead_ids)} leads with Claude AI...",
                                current=0, total=len(lead_ids),
                                detail="Preparing leads for parallel scoring")

            scored_ids = await scoring_service.score_leads_batch(
                lead_ids, db, progress_callback=lambda cur, tot, uname:
                    update_progress(cid, "scoring",
                                    f"Scoring lead {cur}/{tot}: @{uname}",
                                    current=cur, total=tot,
                                    detail=f"Using 10 parallel threads") if cid else None
            )
            await db.commit()
            logger.info(f"Scored {len(scored_ids)} leads")

            if cid:
                update_progress(cid, "scoring",
                                f"Scoring complete! {len(scored_ids)}/{len(lead_ids)} leads scored.",
                                current=len(scored_ids), total=len(lead_ids),
                                detail="Moving to research phase...")

            return lead_ids

    try:
        return _run_async(_score())
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            try:
                async def _get_campaign():
                    async with create_worker_session()() as db:
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

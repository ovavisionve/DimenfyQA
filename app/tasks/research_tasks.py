import logging

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, fail_campaign, update_progress, RETRY_KWARGS
from app.database import create_worker_session
from app.services.research_service import research_service

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="research_leads", **RETRY_KWARGS)
def research_leads_task(self, lead_ids: list[str]) -> list[str]:
    """Research leads with score >= threshold. Returns all lead_ids."""
    logger.info(f"Researching from {len(lead_ids)} scored leads (attempt {self.request.retries + 1}/{self.max_retries + 1})")

    async def _research():
        async with create_worker_session()() as db:
            # Update campaign status to "researching"
            campaign_id = None
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
                        campaign.status = "researching"
                        await db.flush()

            cid = str(campaign_id) if campaign_id else None
            if cid:
                update_progress(cid, "researching",
                                f"Starting research on qualified leads...",
                                current=0, total=len(lead_ids),
                                detail="Filtering leads by score threshold")

            researched_ids = await research_service.research_leads_batch(
                lead_ids, db, progress_callback=lambda cur, tot, uname:
                    update_progress(cid, "researching",
                                    f"Researching lead {cur}/{tot}: @{uname}",
                                    current=cur, total=tot,
                                    detail=f"Using 8 parallel requests") if cid else None
            )
            await db.commit()
            logger.info(f"Researched {len(researched_ids)} leads")

            if cid:
                update_progress(cid, "researching",
                                f"Research complete! {len(researched_ids)} leads researched.",
                                current=len(researched_ids), total=len(researched_ids),
                                detail="Moving to DM copywriting phase...")

            # Return all lead_ids so the next step can filter
            return lead_ids

    try:
        return _run_async(_research())
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
                    fail_campaign(campaign_id, f"Research failed after {self.max_retries + 1} attempts: {exc}")
            except Exception:
                logger.exception("Could not mark campaign as failed")
        raise

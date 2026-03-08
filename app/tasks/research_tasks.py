import logging

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, fail_campaign, RETRY_KWARGS
from app.database import create_worker_session
from app.services.research_service import research_service

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="research_leads", **RETRY_KWARGS)
def research_leads_task(self, lead_ids: list[str]) -> list[str]:
    """Research leads with score >= threshold. Returns all lead_ids."""
    logger.info(f"Researching from {len(lead_ids)} scored leads (attempt {self.request.retries + 1}/{self.max_retries + 1})")

    async def _research():
        async with create_worker_session()() as db:
            researched_ids = await research_service.research_leads_batch(lead_ids, db)
            await db.commit()
            logger.info(f"Researched {len(researched_ids)} leads")
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

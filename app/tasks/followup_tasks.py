import logging

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, RETRY_KWARGS
from app.database import create_worker_session
from app.services.followup_service import followup_service

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="process_follow_ups", **RETRY_KWARGS)
def process_follow_ups_task(self, campaign_id: str) -> dict:
    """Process follow-ups for a specific campaign."""
    logger.info(
        f"Starting follow-up processing for campaign {campaign_id} "
        f"(attempt {self.request.retries + 1}/{self.max_retries + 1})"
    )

    async def _process():
        async with create_worker_session()() as db:
            result = await followup_service.process_follow_ups(campaign_id, db)
            return result

    try:
        return _run_async(_process())
    except Exception as exc:
        logger.exception(f"Follow-up processing failed for campaign {campaign_id}: {exc}")
        raise


@celery_app.task(bind=True, name="check_all_follow_ups")
def check_all_follow_ups_task(self) -> dict:
    """Celery beat task: check ALL active campaigns for due follow-ups.

    This task is designed to run periodically (e.g., every hour via Celery beat).
    It finds all campaigns that have active follow-up rules and dispatches
    individual process_follow_ups_task for each.
    """
    logger.info("Checking all campaigns for due follow-ups")

    async def _check():
        from sqlalchemy import select, distinct
        from app.models.follow_up_rule import FollowUpRule
        from app.models.campaign import Campaign

        async with create_worker_session()() as db:
            # Find campaigns that have active follow-up rules and are in a sendable state
            result = await db.execute(
                select(distinct(FollowUpRule.campaign_id)).where(
                    FollowUpRule.is_active.is_(True),
                ).join(
                    Campaign, Campaign.id == FollowUpRule.campaign_id
                ).where(
                    Campaign.status.in_(["completed", "sending", "ready", "paused"]),
                )
            )
            campaign_ids = [str(cid) for cid in result.scalars().all()]

        return campaign_ids

    try:
        campaign_ids = _run_async(_check())
        dispatched = 0

        for cid in campaign_ids:
            process_follow_ups_task.delay(cid)
            dispatched += 1

        logger.info(f"Dispatched follow-up processing for {dispatched} campaigns")
        return {"campaigns_checked": len(campaign_ids), "dispatched": dispatched}

    except Exception as exc:
        logger.exception(f"Failed to check campaigns for follow-ups: {exc}")
        raise

import logging

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, update_progress, RETRY_KWARGS
from app.database import create_worker_session

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="check_inbox", **RETRY_KWARGS)
def check_inbox_task(self, campaign_id: str) -> dict:
    """Check Instagram inbox for replies to sent DMs in a campaign.

    Returns dict with new_replies count and classifications.
    """
    logger.info(
        f"Starting inbox check for campaign {campaign_id} "
        f"(attempt {self.request.retries + 1}/{self.max_retries + 1})"
    )

    async def _check():
        async with create_worker_session()() as db:
            from app.services.inbox_service import inbox_service

            await update_progress(
                campaign_id, "inbox_check",
                "Checking Instagram inbox for replies...",
                current=0, total=0,
                detail="Logging in and fetching DM threads",
            )

            result = await inbox_service.process_campaign_inbox(campaign_id, db)

            if result["errors"]:
                detail = "; ".join(result["errors"][:3])
            else:
                detail = "No errors"

            await update_progress(
                campaign_id, "inbox_check",
                f"Inbox check complete: {result['new_replies']} new replies",
                current=result["new_replies"], total=result["new_replies"],
                detail=detail,
            )

            logger.info(
                f"Inbox check done for campaign {campaign_id}: "
                f"{result['new_replies']} new replies, "
                f"classifications={result['classifications']}"
            )

            return result

    try:
        return _run_async(_check())
    except Exception as exc:
        logger.exception(f"Inbox check failed for campaign {campaign_id}: {exc}")
        raise

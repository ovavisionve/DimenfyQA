import logging

from celery import chain

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async
from app.tasks.scraping_tasks import scrape_leads_task
from app.tasks.scoring_tasks import score_leads_task
from app.tasks.research_tasks import research_leads_task
from app.tasks.copywriting_tasks import write_dms_task
from app.tasks.comment_tasks import fetch_posts_and_generate_comments_task
from app.database import create_worker_session

logger = logging.getLogger(__name__)

# Maps campaign status → phase that should resume
RESUME_PHASES = {
    "scraping": "scrape",
    "scoring": "score",
    "researching": "research",
    "writing": "write",
    "writing_dms": "write",
    "sending": "send",
}


def run_campaign_pipeline(campaign_id: str) -> str:
    """
    Run the pipeline for a campaign (stops at DM generation, sending is manual):
    1. Scrape leads
    2. Score each lead (parallel within task)
    3. Research leads with score >= 60 (parallel within task)
    4. Write DMs for leads with score >= 70 (parallel within task)
    → STOPS here. Campaign status becomes "ready".
    → User reviews DMs and clicks "Send DMs" button to start sending.

    Each task receives the lead_ids from the previous step.
    """
    pipeline = chain(
        scrape_leads_task.s(campaign_id),
        score_leads_task.s(),
        research_leads_task.s(),
        write_dms_task.s(),
        fetch_posts_and_generate_comments_task.s(),
    )
    result = pipeline.apply_async()
    task_id = result.id

    # Store task_id on campaign for recovery
    _save_task_id(campaign_id, task_id)

    logger.info(f"Started pipeline for campaign {campaign_id}, task_id={task_id}")
    return task_id


def _save_task_id(campaign_id: str, task_id: str):
    """Save celery_task_id on campaign for idempotency and recovery."""
    async def _save():
        async with create_worker_session()() as db:
            from sqlalchemy import select
            from app.models.campaign import Campaign

            result = await db.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            campaign = result.scalar_one_or_none()
            if campaign:
                campaign.celery_task_id = task_id
                await db.commit()

    try:
        _run_async(_save())
    except Exception as e:
        logger.warning(f"Failed to save task_id on campaign {campaign_id}: {e}")


def resume_campaign(campaign_id: str, from_phase: str) -> str | None:
    """Resume a campaign from a specific phase.

    Used by startup recovery to continue interrupted campaigns.
    Returns the new task_id, or None if phase is unknown.
    """
    # Build partial pipeline based on where we left off
    if from_phase == "scrape":
        pipeline = chain(
            scrape_leads_task.s(campaign_id),
            score_leads_task.s(),
            research_leads_task.s(),
            write_dms_task.s(),
            fetch_posts_and_generate_comments_task.s(),
        )
    elif from_phase == "score":
        # Re-score: get lead_ids from DB
        lead_ids = _get_campaign_lead_ids(campaign_id)
        pipeline = chain(
            score_leads_task.s(lead_ids),
            research_leads_task.s(),
            write_dms_task.s(),
            fetch_posts_and_generate_comments_task.s(),
        )
    elif from_phase == "research":
        lead_ids = _get_campaign_lead_ids(campaign_id)
        pipeline = chain(
            research_leads_task.s(lead_ids),
            write_dms_task.s(),
            fetch_posts_and_generate_comments_task.s(),
        )
    elif from_phase == "write":
        lead_ids = _get_campaign_lead_ids(campaign_id)
        pipeline = chain(
            write_dms_task.s(lead_ids),
            fetch_posts_and_generate_comments_task.s(),
        )
    else:
        logger.warning(f"Unknown phase '{from_phase}' for campaign {campaign_id}")
        return None

    result = pipeline.apply_async()
    _save_task_id(campaign_id, result.id)
    logger.info(f"Resumed campaign {campaign_id} from phase={from_phase}, task_id={result.id}")
    return result.id


def _get_campaign_lead_ids(campaign_id: str) -> list[str]:
    """Get all lead IDs for a campaign."""
    async def _get():
        async with create_worker_session()() as db:
            from sqlalchemy import select
            from app.models.lead import Lead

            result = await db.execute(
                select(Lead.id).where(Lead.campaign_id == campaign_id)
            )
            return [str(lid) for lid in result.scalars().all()]

    return _run_async(_get())


async def recover_interrupted_campaigns():
    """Check for campaigns stuck in active phases and resume them.

    Called on FastAPI startup to handle Docker/server restarts.
    """
    from sqlalchemy import select
    from app.database import async_session
    from app.models.campaign import Campaign

    active_statuses = list(RESUME_PHASES.keys())

    async with async_session() as db:
        result = await db.execute(
            select(Campaign).where(Campaign.status.in_(active_statuses))
        )
        stuck_campaigns = result.scalars().all()

        if not stuck_campaigns:
            logger.info("No interrupted campaigns found on startup")
            return

        logger.warning(f"Found {len(stuck_campaigns)} interrupted campaign(s) — resuming")

        for campaign in stuck_campaigns:
            phase = RESUME_PHASES.get(campaign.status)
            if not phase:
                continue

            # Check if the Celery task is still running
            if campaign.celery_task_id:
                task_result = celery_app.AsyncResult(campaign.celery_task_id)
                if task_result.state in ("PENDING", "STARTED", "RETRY"):
                    logger.info(
                        f"Campaign {campaign.id} ({campaign.name}) task still active "
                        f"(state={task_result.state}), skipping recovery"
                    )
                    continue

            logger.info(
                f"Resuming campaign {campaign.id} ({campaign.name}) "
                f"from status={campaign.status} → phase={phase}"
            )

            try:
                resume_campaign(str(campaign.id), phase)
            except Exception as e:
                logger.error(f"Failed to resume campaign {campaign.id}: {e}")
                campaign.status = "failed"
                stats = dict(campaign.stats or {})
                stats["error"] = f"Recovery failed: {e}"
                campaign.stats = stats

        await db.commit()

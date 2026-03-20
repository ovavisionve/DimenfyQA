import logging

from celery import chain

from app.tasks.scraping_tasks import scrape_leads_task
from app.tasks.scoring_tasks import score_leads_task
from app.tasks.research_tasks import research_leads_task
from app.tasks.copywriting_tasks import write_dms_task
from app.tasks.sending_tasks import send_dms_task

logger = logging.getLogger(__name__)


def run_campaign_pipeline(campaign_id: str):
    """
    Run the full pipeline for a campaign:
    1. Scrape leads
    2. Score each lead (parallel within task)
    3. Research leads with score >= 60 (parallel within task)
    4. Write DMs for leads with score >= 70 (parallel within task)
    5. Send DMs via Instagram (rate-limited, with delays)

    Each task receives the lead_ids from the previous step.
    """
    pipeline = chain(
        scrape_leads_task.s(campaign_id),
        score_leads_task.s(),
        research_leads_task.s(),
        write_dms_task.s(),
        send_dms_task.s(),
    )
    result = pipeline.apply_async()
    logger.info(f"Started pipeline for campaign {campaign_id}, task_id={result.id}")
    return result.id

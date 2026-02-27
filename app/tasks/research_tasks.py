import asyncio
import logging

from app.tasks.celery_app import celery_app
from app.database import async_session
from app.services.research_service import research_service

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="research_leads")
def research_leads_task(self, lead_ids: list[str]) -> list[str]:
    """Research leads with score >= threshold. Returns all lead_ids."""
    logger.info(f"Researching from {len(lead_ids)} scored leads")

    async def _research():
        async with async_session() as db:
            researched_ids = await research_service.research_leads_batch(lead_ids, db)
            await db.commit()
            logger.info(f"Researched {len(researched_ids)} leads")
            # Return all lead_ids so the next step can filter
            return lead_ids

    return _run_async(_research())

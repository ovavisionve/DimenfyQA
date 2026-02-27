import asyncio
import logging

from app.tasks.celery_app import celery_app
from app.database import async_session
from app.services.apify_service import apify_service
from app.models.campaign import Campaign

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Helper to run async code in sync Celery tasks."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="scrape_leads")
def scrape_leads_task(self, campaign_id: str) -> list[str]:
    """Scrape leads for a campaign. Returns list of lead_ids."""
    logger.info(f"Starting scrape for campaign {campaign_id}")

    async def _scrape():
        async with async_session() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            campaign = result.scalar_one_or_none()
            if not campaign:
                raise ValueError(f"Campaign {campaign_id} not found")

            campaign.status = "scraping"
            await db.flush()

            # Start scrape job
            scrape_job = await apify_service.start_scrape(
                campaign.source_type,
                campaign.source_value,
                campaign_id,
                db,
            )

            # Poll until complete
            import time
            max_attempts = 60
            for _ in range(max_attempts):
                status_data = await apify_service.poll_scrape_status(
                    scrape_job.apify_run_id
                )
                if status_data["status"] == "SUCCEEDED":
                    scrape_job.apify_dataset_id = status_data["defaultDatasetId"]
                    scrape_job.status = "completed"
                    break
                elif status_data["status"] in ("FAILED", "ABORTED", "TIMED-OUT"):
                    scrape_job.status = "failed"
                    scrape_job.error_message = f"Apify run {status_data['status']}"
                    await db.commit()
                    raise RuntimeError(f"Apify run failed: {status_data['status']}")
                time.sleep(5)  # noqa: ASYNC251 — sync sleep in sync context within event loop

            # Get results
            raw_profiles = await apify_service.get_scrape_results(
                scrape_job.apify_dataset_id
            )

            # Get detailed profiles if needed (followers/comments give partial data)
            if campaign.source_type in ("followers", "comments"):
                usernames = [p.get("username", "") for p in raw_profiles if p.get("username")]
                if usernames:
                    # Batch in chunks of 50
                    detailed_profiles = []
                    for i in range(0, len(usernames), 50):
                        chunk = usernames[i:i + 50]
                        profiles = await apify_service.scrape_profiles_sync(chunk)
                        detailed_profiles.extend(profiles)
                    raw_profiles = detailed_profiles

            # Save leads with dedup
            saved = await apify_service.save_leads(
                raw_profiles, campaign_id, str(campaign.client_id), db
            )
            scrape_job.items_found = saved
            await db.commit()

            # Return lead IDs for next pipeline step
            from app.models.lead import Lead
            lead_result = await db.execute(
                select(Lead.id).where(
                    Lead.campaign_id == campaign_id,
                    Lead.status == "scraped",
                )
            )
            lead_ids = [str(row[0]) for row in lead_result.fetchall()]
            logger.info(f"Scraped {saved} leads for campaign {campaign_id}")
            return lead_ids

    return _run_async(_scrape())

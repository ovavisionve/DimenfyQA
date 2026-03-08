import logging
import time

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, fail_campaign, update_progress, RETRY_KWARGS
from app.database import create_worker_session
from app.services.apify_service import apify_service
from app.models.campaign import Campaign

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="scrape_leads", **RETRY_KWARGS)
def scrape_leads_task(self, campaign_id: str) -> list[str]:
    """Scrape leads for a campaign. Returns list of lead_ids."""
    logger.info(f"Starting scrape for campaign {campaign_id} (attempt {self.request.retries + 1}/{self.max_retries + 1})")

    async def _scrape():
        async with create_worker_session()() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            campaign = result.scalar_one_or_none()
            if not campaign:
                raise ValueError(f"Campaign {campaign_id} not found")

            campaign.status = "scraping"
            await db.flush()

            # Start scrape job (use max_leads from campaign settings if set)
            max_leads = (campaign.settings or {}).get("max_leads", 0)

            await update_progress(campaign_id, "scraping",
                            f"Starting Apify scraper for @{campaign.source_value[:50]}...",
                            detail=f"Source: {campaign.source_type}, target: {max_leads or 'all'} leads")

            scrape_job = await apify_service.start_scrape(
                campaign.source_type,
                campaign.source_value,
                campaign_id,
                db,
                max_leads=max_leads,
            )

            # Poll until complete
            max_attempts = 60
            for attempt in range(max_attempts):
                status_data = await apify_service.poll_scrape_status(
                    scrape_job.apify_run_id
                )
                run_status = status_data["status"]
                stats = status_data.get("stats", {})
                items_count = stats.get("itemsCount", 0) if isinstance(stats, dict) else 0
                logger.info(f"Poll {attempt+1}: status={run_status}, stats={stats}")

                await update_progress(campaign_id, "scraping",
                                f"Apify running... ({run_status})",
                                current=attempt + 1, total=max_attempts,
                                detail=f"Poll {attempt+1}/{max_attempts} | Items found: {items_count}")

                if run_status == "SUCCEEDED":
                    scrape_job.apify_dataset_id = status_data["defaultDatasetId"]
                    scrape_job.status = "completed"
                    logger.info(f"Run succeeded. Dataset: {status_data['defaultDatasetId']}, usage: {status_data.get('usageTotalUsd')}")
                    break
                elif status_data["status"] in ("FAILED", "ABORTED", "TIMED-OUT"):
                    scrape_job.status = "failed"
                    scrape_job.error_message = f"Apify run {status_data['status']}"
                    await db.commit()
                    raise RuntimeError(f"Apify run failed: {status_data['status']}")
                time.sleep(5)
            else:
                scrape_job.status = "failed"
                scrape_job.error_message = "Polling timeout"
                await db.commit()
                raise RuntimeError("Apify run polling timed out after 5 minutes")

            # Get results
            await update_progress(campaign_id, "scraping",
                            "Downloading profiles from Apify...",
                            detail="Fetching dataset results")

            raw_profiles = await apify_service.get_scrape_results(
                scrape_job.apify_dataset_id
            )
            logger.info(f"Raw profiles from Apify: {len(raw_profiles)} items for source_type={campaign.source_type}")

            # Get detailed profiles if needed (followers/comments give partial data)
            if campaign.source_type in ("followers", "comments"):
                usernames = [p.get("username", "") for p in raw_profiles if p.get("username")]
                if usernames:
                    total_chunks = (len(usernames) + 49) // 50
                    detailed_profiles = []
                    for i in range(0, len(usernames), 50):
                        chunk_num = i // 50 + 1
                        chunk = usernames[i:i + 50]

                        await update_progress(campaign_id, "scraping",
                                        f"Fetching detailed profiles ({chunk_num}/{total_chunks})...",
                                        current=chunk_num, total=total_chunks,
                                        detail=f"Batch {chunk_num}: {len(chunk)} profiles")

                        profiles = await apify_service.scrape_profiles_sync(chunk)
                        detailed_profiles.extend(profiles)
                    raw_profiles = detailed_profiles

            # Save leads with dedup
            await update_progress(campaign_id, "scraping",
                            f"Saving {len(raw_profiles)} profiles to database...",
                            detail="Deduplicating and storing leads")

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

            await update_progress(campaign_id, "scraping",
                            f"Scraping complete! {saved} leads saved.",
                            current=saved, total=saved,
                            detail="Moving to scoring phase...")

            return lead_ids

    try:
        return _run_async(_scrape())
    except ValueError as exc:
        fail_campaign(campaign_id, str(exc))
        raise
    except RuntimeError as exc:
        fail_campaign(campaign_id, str(exc))
        raise
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            fail_campaign(campaign_id, f"Scraping failed after {self.max_retries + 1} attempts: {exc}")
        raise

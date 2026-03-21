import logging
import time

from datetime import datetime, timezone

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
            await db.commit()

            # Start scrape job (use max_leads from campaign settings if set)
            max_leads = (campaign.settings or {}).get("max_leads", 0)

            await update_progress(campaign_id, "scraping",
                            f"Starting Apify scraper for @{campaign.source_value[:50]}...",
                            detail=f"Source: {campaign.source_type}, target: {max_leads or 'all'} leads")

            # For comments: use multi-actor strategy to maximize results
            if campaign.source_type == "comments":
                from app.models.scrape_job import ScrapeJob as SJ
                scrape_job = SJ(
                    campaign_id=campaign_id,
                    apify_run_id="multi-actor",
                    actor_type="comments",
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
                db.add(scrape_job)
                await db.flush()

                async def _multi_progress(msg):
                    await update_progress(campaign_id, "scraping", msg,
                                    detail="Running multiple scrapers in parallel for more results")

                await update_progress(campaign_id, "scraping",
                                "Running 3 comment scrapers in parallel for maximum results...",
                                detail="Each scraper fetches comments independently")

                raw_profiles = await apify_service.scrape_comments_multi_actor(
                    campaign.source_value,
                    max_leads=max_leads,
                    progress_callback=_multi_progress,
                )
                scrape_job.status = "completed"
                scrape_job.items_found = len(raw_profiles)
                await db.commit()
                logger.info(f"Multi-actor scrape returned {len(raw_profiles)} unique comments")
            else:
                # Non-comment sources: use single actor as before
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
                # Extract unique usernames from raw data (comments/followers)
                usernames = []
                for p in raw_profiles:
                    uname = (
                        p.get("username")
                        or p.get("ownerUsername")
                        or p.get("owner", {}).get("username", "")
                        or ""
                    )
                    if uname and uname not in usernames:
                        usernames.append(uname)
                    # Extract usernames from comment replies
                    for reply in (p.get("replies") or []):
                        reply_uname = (
                            reply.get("ownerUsername")
                            or reply.get("username")
                            or reply.get("owner", {}).get("username", "")
                            or ""
                        )
                        if reply_uname and reply_uname not in usernames:
                            usernames.append(reply_uname)
                logger.info(f"Extracted {len(usernames)} unique usernames (including replies) from {len(raw_profiles)} comments")
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

            # Auto-analyze campaign content if URLs/text are configured
            content_urls = (campaign.settings or {}).get("content_urls", [])
            content_text = (campaign.settings or {}).get("content_text", "")
            existing_analysis = (campaign.settings or {}).get("content_analysis")

            if (content_urls or content_text) and not existing_analysis:
                try:
                    from app.services.content_analysis_service import content_analysis_service
                    await update_progress(campaign_id, "scraping",
                                    "Analyzing campaign content with Gemini AI...",
                                    detail="Multimodal analysis of video/image/webpage content")
                    await content_analysis_service.analyze_campaign_content(
                        campaign_id, db,
                        content_urls=content_urls,
                        content_text=content_text,
                    )
                    await db.commit()
                    logger.info(f"Content analysis completed for campaign {campaign_id}")
                except Exception as e:
                    logger.warning(f"Content analysis failed (non-blocking): {e}")

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

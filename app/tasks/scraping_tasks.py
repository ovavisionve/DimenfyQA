import json
import logging
import time

from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, fail_campaign, update_progress, RETRY_KWARGS
from app.database import create_worker_session
from app.services.apify_service import apify_service
from app.models.campaign import Campaign

logger = logging.getLogger(__name__)

# Pre-filter thresholds for quality leads
MIN_FOLLOWERS = 200       # Minimum followers to be considered valuable
MAX_FOLLOWERS = 5_000_000 # Filter out celebrity/spam accounts
OVERSCRAPE_MULTIPLIER = 3 # Scrape 3x the target to compensate for filtering
MAX_SCRAPE_ROUNDS = 5     # Maximum scraping rounds before giving up


def _pre_filter_profiles(profiles: list[dict]) -> tuple[list[dict], list[dict]]:
    """Apply hard pre-filters to profiles. Returns (passed, rejected)."""
    passed = []
    rejected = []

    for p in profiles:
        username = p.get("username") or p.get("ownerUsername") or ""
        if not username:
            rejected.append(p)
            continue

        # ZERO tolerance for private accounts
        if p.get("isPrivate", False):
            logger.info(f"[PreFilter] REJECTED private: @{username}")
            rejected.append(p)
            continue

        followers = p.get("followersCount") or 0
        bio = (p.get("biography") or "").strip()
        has_profile_pic = bool(p.get("profilePicUrl") or p.get("profilePicUrlHD"))

        # Must have minimum followers
        if followers < MIN_FOLLOWERS:
            logger.debug(f"[PreFilter] REJECTED low followers ({followers}): @{username}")
            rejected.append(p)
            continue

        # Must have a bio
        if not bio:
            logger.debug(f"[PreFilter] REJECTED no bio: @{username}")
            rejected.append(p)
            continue

        # Filter mega accounts (unlikely to read DMs)
        if followers > MAX_FOLLOWERS:
            logger.debug(f"[PreFilter] REJECTED too many followers ({followers}): @{username}")
            rejected.append(p)
            continue

        passed.append(p)

    return passed, rejected


async def _claude_pre_evaluate(profiles: list[dict], content_context: str = "") -> list[dict]:
    """Use Claude to quickly evaluate which profiles are worth keeping.

    Does a fast batch evaluation — cheaper than full scoring because we only
    send minimal data and ask for a simple yes/no + reason.
    Returns only the profiles Claude deems worth pursuing.
    """
    import anthropic
    from app.config import settings

    if not profiles:
        return []

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Build minimal profile data for Claude
    profiles_for_claude = []
    for p in profiles:
        profiles_for_claude.append({
            "username": p.get("username") or p.get("ownerUsername") or "",
            "full_name": p.get("fullName") or "",
            "bio": (p.get("biography") or "")[:200],
            "followers": p.get("followersCount") or 0,
            "following": p.get("followsCount") or 0,
            "category": p.get("businessCategoryName") or "",
            "has_website": bool(p.get("externalUrl")),
            "posts_count": p.get("postsCount") or 0,
        })

    prompt = f"""Eres un filtro de calidad de leads para una agencia B2B de automatización.

Evalúa rápidamente cada perfil y decide si vale la pena contactar por DM.

## Criterios para APROBAR (keep=true):
- Es un negocio, emprendedor, coach, agencia, o creador de contenido profesional
- Su bio sugiere que vende productos/servicios o tiene un negocio
- Tiene una audiencia relevante (no es cuenta personal random)
- Podría beneficiarse de automatización, marketing digital, o generación de leads

## Criterios para RECHAZAR (keep=false):
- Cuenta personal sin indicios de negocio
- Fan account, meme account, cuenta de noticias
- Bot o cuenta spam
- Bio vacía o genérica sin contexto de negocio
- Solo emojis o frases personales en bio

{content_context}

## Perfiles a evaluar:
{json.dumps(profiles_for_claude, ensure_ascii=False)}

## Output:
Responde SOLO un JSON array. Por cada perfil:
[
  {{"username": "<username>", "keep": true/false, "reason": "<1 oración>"}}
]

IMPORTANTE: Devuelve EXACTAMENTE {len(profiles_for_claude)} resultados."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        # Clean markdown if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        evaluations = json.loads(text)

        # Build set of approved usernames
        approved = set()
        for ev in evaluations:
            if ev.get("keep", False):
                approved.add(ev["username"])

        logger.info(f"[Claude PreFilter] {len(approved)}/{len(profiles_for_claude)} profiles approved")

        # Return only approved profiles (original full profile data)
        result = []
        for p in profiles:
            uname = p.get("username") or p.get("ownerUsername") or ""
            if uname in approved:
                result.append(p)

        return result

    except Exception as e:
        logger.warning(f"[Claude PreFilter] Failed (non-blocking, keeping all): {e}")
        return profiles  # On failure, keep all profiles


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
            campaign.last_phase = "scrape"
            await db.commit()

            # Extract all campaign data upfront to avoid lazy-load after long Apify wait
            campaign_settings = dict(campaign.settings or {})
            campaign_source_type = campaign.source_type
            campaign_source_value = campaign.source_value
            campaign_client_id = str(campaign.client_id)

            # Target number of quality leads
            max_leads = campaign_settings.get("max_leads", 0)

            # Get content context for Claude pre-evaluation
            content_context = ""
            content_analysis = campaign_settings.get("content_analysis")
            if content_analysis:
                content_context = f"## Contexto del negocio del cliente:\n{json.dumps(content_analysis, ensure_ascii=False)[:500]}"

            await update_progress(campaign_id, "scraping",
                            f"Starting smart scraper for @{campaign_source_value[:50]}...",
                            detail=f"Source: {campaign_source_type}, target: {max_leads or 'all'} quality leads")

            if campaign_source_type == "comments":
                quality_profiles = await _scrape_comments_with_quality_filter(
                    campaign_id=campaign_id,
                    source_value=campaign_source_value,
                    target_leads=max_leads,
                    content_context=content_context,
                )
            else:
                # Non-comment sources: use original flow
                quality_profiles = await _scrape_other_source(
                    campaign=campaign,
                    campaign_id=campaign_id,
                    max_leads=max_leads,
                    db=db,
                )

            # Bio keyword filter — only keep profiles whose bio contains at least one keyword
            bio_keywords = campaign_settings.get("bio_keywords", [])
            if bio_keywords:
                before_count = len(quality_profiles)
                kw_lower = [kw.lower().strip() for kw in bio_keywords if kw.strip()]
                quality_profiles = [
                    p for p in quality_profiles
                    if any(
                        kw in (p.get("biography") or "").lower()
                        for kw in kw_lower
                    )
                ]
                filtered_out = before_count - len(quality_profiles)
                logger.info(
                    f"Bio keyword filter: {len(quality_profiles)} kept, {filtered_out} removed "
                    f"(keywords: {kw_lower})"
                )
                await update_progress(campaign_id, "scraping",
                                f"Bio filter: {len(quality_profiles)} of {before_count} profiles matched keywords.",
                                detail=f"Keywords: {', '.join(bio_keywords)}")

        # === FRESH DB SESSION ===
        # After the long Apify scraping (10-20 min), the original DB connection
        # is dead (Supabase/PgBouncer drops idle connections). Instead of trying
        # to reuse it and catching errors, we proactively create a fresh session.
        logger.info(f"[SmartScrape] Creating fresh DB session for saving {len(quality_profiles)} profiles")
        async with create_worker_session()() as db2:
            from app.models.lead import Lead

            # Save leads with dedup
            await update_progress(campaign_id, "scraping",
                            f"Saving {len(quality_profiles)} quality profiles to database...",
                            detail="Deduplicating and storing leads")

            saved = await apify_service.save_leads(
                quality_profiles, campaign_id, campaign_client_id, db2
            )
            await db2.commit()

            # Return lead IDs for next pipeline step
            lead_result = await db2.execute(
                select(Lead.id).where(
                    Lead.campaign_id == campaign_id,
                    Lead.status == "scraped",
                )
            )
            lead_ids = [str(row[0]) for row in lead_result.fetchall()]
            logger.info(f"Scraped {saved} quality leads for campaign {campaign_id}")

            await update_progress(campaign_id, "scraping",
                            f"Scraping complete! {saved} quality leads saved.",
                            current=saved, total=saved,
                            detail="Moving to scoring phase...")

            # Auto-analyze campaign content if URLs/text are configured
            content_urls = campaign_settings.get("content_urls", [])
            content_text = campaign_settings.get("content_text", "")
            existing_analysis = campaign_settings.get("content_analysis")

            if (content_urls or content_text) and not existing_analysis:
                try:
                    from app.services.content_analysis_service import content_analysis_service
                    await update_progress(campaign_id, "scraping",
                                    "Analyzing campaign content with Gemini AI...",
                                    detail="Multimodal analysis of video/image/webpage content")
                    await content_analysis_service.analyze_campaign_content(
                        campaign_id, db2,
                        content_urls=content_urls,
                        content_text=content_text,
                    )
                    await db2.commit()
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


async def _scrape_comments_with_quality_filter(
    campaign_id: str,
    source_value: str,
    target_leads: int,
    content_context: str,
) -> list[dict]:
    """Scrape comments with over-scraping loop + pre-filters + Claude evaluation.

    Keeps scraping in increasing batches until we reach the target number
    of quality leads, or exhaust all available comments.

    NOTE: This function creates its own DB session for the scrape_job record
    because the calling session will be dead after the long Apify wait.
    """
    from app.models.scrape_job import ScrapeJob as SJ

    # Use a short-lived session just to create the scrape_job record
    async with create_worker_session()() as init_db:
        scrape_job = SJ(
            campaign_id=campaign_id,
            apify_run_id="smart-scrape",
            actor_type="comments",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        init_db.add(scrape_job)
        await init_db.commit()
        scrape_job_id = scrape_job.id

    all_quality_profiles = []
    seen_usernames = set()
    scrape_limit = max(target_leads * OVERSCRAPE_MULTIPLIER, 100) if target_leads > 0 else 200

    for round_num in range(1, MAX_SCRAPE_ROUNDS + 1):
        await update_progress(campaign_id, "scraping",
            f"Round {round_num}: Scraping {scrape_limit} comments...",
            detail=f"Target: {target_leads} quality leads | Found so far: {len(all_quality_profiles)}")

        # 1. Scrape comments
        async def _progress(msg):
            await update_progress(campaign_id, "scraping", msg,
                detail=f"Round {round_num}/{MAX_SCRAPE_ROUNDS} | Quality leads so far: {len(all_quality_profiles)}")

        raw_comments = await apify_service.scrape_comments_multi_actor(
            source_value,
            max_leads=scrape_limit,
            progress_callback=_progress,
        )

        # 2. Extract new usernames (skip already processed)
        new_usernames = []
        for p in raw_comments:
            uname = (
                p.get("username")
                or p.get("ownerUsername")
                or p.get("owner", {}).get("username", "")
                or (p.get("user") or {}).get("username", "")
                or ""
            )
            if uname and uname not in seen_usernames:
                seen_usernames.add(uname)
                new_usernames.append(uname)
            for reply in (p.get("replies") or []):
                reply_uname = (
                    reply.get("ownerUsername")
                    or reply.get("username")
                    or reply.get("owner", {}).get("username", "")
                    or (reply.get("user") or {}).get("username", "")
                    or ""
                )
                if reply_uname and reply_uname not in seen_usernames:
                    seen_usernames.add(reply_uname)
                    new_usernames.append(reply_uname)

        if not new_usernames:
            logger.info(f"[SmartScrape] Round {round_num}: No new usernames found. Stopping.")
            await update_progress(campaign_id, "scraping",
                f"No more new commenters found after {len(seen_usernames)} total.",
                detail=f"Quality leads collected: {len(all_quality_profiles)}")
            break

        logger.info(f"[SmartScrape] Round {round_num}: {len(new_usernames)} new usernames to process")

        # 3. Fetch detailed profiles
        await update_progress(campaign_id, "scraping",
            f"Round {round_num}: Fetching {len(new_usernames)} profiles...",
            detail=f"Getting full profile data for quality filtering")

        detailed_profiles = []
        for i in range(0, len(new_usernames), 50):
            chunk = new_usernames[i:i + 50]
            chunk_num = i // 50 + 1
            total_chunks = (len(new_usernames) + 49) // 50
            await update_progress(campaign_id, "scraping",
                f"Round {round_num}: Profiles batch {chunk_num}/{total_chunks}...",
                detail=f"Fetching {len(chunk)} profiles")
            profiles = await apify_service.scrape_profiles_sync(chunk)
            detailed_profiles.extend(profiles)

        logger.info(f"[SmartScrape] Round {round_num}: Got {len(detailed_profiles)} detailed profiles")

        # 4. Hard pre-filters (free, instant)
        passed, rejected = _pre_filter_profiles(detailed_profiles)
        logger.info(f"[SmartScrape] Round {round_num}: Pre-filter: {len(passed)} passed, {len(rejected)} rejected")

        await update_progress(campaign_id, "scraping",
            f"Round {round_num}: {len(passed)} passed pre-filters (of {len(detailed_profiles)})",
            detail=f"Rejected: {len(rejected)} (private, low followers, no bio)")

        # 5. Claude pre-evaluation (smart filter)
        if passed:
            await update_progress(campaign_id, "scraping",
                f"Round {round_num}: Claude AI evaluating {len(passed)} profiles...",
                detail="Filtering for business potential with AI")

            # Process in batches of 20 for Claude
            claude_approved = []
            for i in range(0, len(passed), 20):
                batch = passed[i:i + 20]
                approved = await _claude_pre_evaluate(batch, content_context)
                claude_approved.extend(approved)

            logger.info(f"[SmartScrape] Round {round_num}: Claude approved {len(claude_approved)}/{len(passed)} profiles")
            all_quality_profiles.extend(claude_approved)

        await update_progress(campaign_id, "scraping",
            f"Round {round_num} complete: {len(all_quality_profiles)} quality leads total",
            detail=f"Target: {target_leads}")

        # 6. Check if we've reached the target
        if target_leads > 0 and len(all_quality_profiles) >= target_leads:
            all_quality_profiles = all_quality_profiles[:target_leads]
            logger.info(f"[SmartScrape] Target reached! {len(all_quality_profiles)} quality leads.")
            break

        # 7. If not enough, increase scrape limit for next round
        if round_num < MAX_SCRAPE_ROUNDS:
            remaining = target_leads - len(all_quality_profiles) if target_leads > 0 else 100
            # Increase limit: scrape more comments next round
            scrape_limit = min(scrape_limit + remaining * OVERSCRAPE_MULTIPLIER, 2000)
            logger.info(f"[SmartScrape] Need {remaining} more leads. Next round will scrape {scrape_limit} comments.")

    # Use a fresh DB session to update scrape_job — the original connection
    # is dead after the long Apify wait (Supabase drops idle connections).
    async with create_worker_session()() as final_db:
        from sqlalchemy import update as sa_update
        from app.models.scrape_job import ScrapeJob as SJ2
        await final_db.execute(
            sa_update(SJ2).where(SJ2.id == scrape_job_id).values(
                status="completed", items_found=len(all_quality_profiles)
            )
        )
        await final_db.commit()

    logger.info(f"[SmartScrape] Final: {len(all_quality_profiles)} quality leads from {len(seen_usernames)} total usernames")
    return all_quality_profiles


async def _scrape_other_source(campaign, campaign_id: str, max_leads: int, db) -> list[dict]:
    """Original scraping flow for non-comment sources (followers, profiles)."""
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

    # Get detailed profiles if needed
    if campaign.source_type in ("followers", "hashtag"):
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
        logger.info(f"Extracted {len(usernames)} unique usernames from {len(raw_profiles)} items")
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

    return raw_profiles

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead
from app.models.scrape_job import ScrapeJob

logger = logging.getLogger(__name__)

APIFY_BASE_URL = "https://api.apify.com/v2"

# Apify actors
# instagram-scraper: the MAIN official actor — handles posts, comments, profiles, etc.
#   $2.30/1K results. Use resultsType to control what to scrape.
# instagram-profile-scraper: dedicated profile scraper ($2.60/1K results)
ACTORS = {
    "followers": "apify~instagram-profile-scraper",  # fallback to profile scraper
    "comments": "apify~instagram-scraper",            # main scraper with resultsType=comments
    "profiles": "apify~instagram-profile-scraper",    # dedicated profile scraper
}


def _extract_shortcode(url: str) -> str:
    """Extract Instagram shortcode from a post/reel URL."""
    # Matches /p/SHORTCODE/, /reel/SHORTCODE/, /reels/SHORTCODE/
    match = re.search(r"/(p|reel|reels)/([A-Za-z0-9_-]+)", url)
    if match:
        return match.group(2)
    # If it's already a shortcode (no slashes), return as-is
    if "/" not in url:
        return url
    return url


class ApifyService:
    def __init__(self):
        self._token: Optional[str] = None

    @property
    def token(self) -> str:
        if not self._token:
            self._token = settings.APIFY_API_TOKEN
            if not self._token:
                logger.error("APIFY_API_TOKEN is empty — check .env file")
                raise ValueError("APIFY_API_TOKEN is not configured")
            logger.info("Apify token loaded: %s...%s", self._token[:10], self._token[-4:])
        return self._token

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def start_scrape(
        self, source_type: str, source_value: str, campaign_id: str, db: AsyncSession,
        max_leads: int = 0,
    ) -> ScrapeJob:
        actor_id = ACTORS.get(source_type)
        if not actor_id:
            raise ValueError(f"Unknown source type: {source_type}")

        input_data = self._build_input(source_type, source_value, max_leads=max_leads)
        logger.info(f"Apify input for {source_type}: {input_data}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{APIFY_BASE_URL}/acts/{actor_id}/runs",
                headers=self.headers,
                json=input_data,
                timeout=30,
            )
            response.raise_for_status()
            run_data = response.json()["data"]
            logger.info(f"Apify run started: id={run_data['id']}, status={run_data.get('status')}")

        scrape_job = ScrapeJob(
            campaign_id=campaign_id,
            apify_run_id=run_data["id"],
            actor_type=source_type,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(scrape_job)
        await db.flush()
        return scrape_job

    async def poll_scrape_status(self, run_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{APIFY_BASE_URL}/actor-runs/{run_id}",
                headers=self.headers,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()["data"]

    async def get_scrape_results(self, dataset_id: str) -> list[dict]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{APIFY_BASE_URL}/datasets/{dataset_id}/items",
                headers=self.headers,
                params={"format": "json"},
                timeout=60,
            )
            response.raise_for_status()
            results = response.json()
            logger.info(f"Dataset {dataset_id} returned {len(results)} items")
            if results:
                logger.info(f"First item keys: {list(results[0].keys())[:15]}")
                logger.info(f"First item sample: username={results[0].get('username')}, fullName={results[0].get('fullName')}")
                # Log error messages from Apify actors
                if len(results) == 1 and "message" in results[0] and "username" not in results[0]:
                    logger.error(f"Apify actor returned error: {results[0].get('message', 'unknown error')}")
            return results

    async def scrape_comments_multi_actor(
        self, source_value: str, max_leads: int = 0,
        progress_callback=None,
    ) -> list[dict]:
        """Scrape comments from an Instagram post using the main instagram-scraper actor.

        Uses apify/instagram-scraper with resultsType="comments" which properly
        respects the resultsLimit parameter on paid plans.
        """
        actor_id = ACTORS["comments"]  # apify~instagram-scraper
        input_data = {
            "directUrls": [source_value],
            "resultsType": "comments",
        }
        if max_leads > 0:
            input_data["resultsLimit"] = max_leads

        logger.info(f"[Comments] Starting apify/instagram-scraper with input: {input_data}")
        if progress_callback:
            target = max_leads if max_leads > 0 else "all"
            await progress_callback(f"Scraping up to {target} comments from post...")

        try:
            # Start the run
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{APIFY_BASE_URL}/acts/{actor_id}/runs",
                    headers=self.headers,
                    json=input_data,
                    timeout=30,
                )
                response.raise_for_status()
                run_data = response.json()["data"]
                run_id = run_data["id"]
                logger.info(f"[Comments] Run started: {run_id}")

            # Poll until complete (up to 15 min for large scrapes)
            poll_interval = 5
            max_poll_attempts = 180  # 15 minutes
            for attempt in range(max_poll_attempts):
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{APIFY_BASE_URL}/actor-runs/{run_id}",
                        headers=self.headers,
                        timeout=30,
                    )
                    response.raise_for_status()
                    status_data = response.json()["data"]

                run_status = status_data["status"]
                stats = status_data.get("stats", {})
                items_count = stats.get("itemsCount", 0) if isinstance(stats, dict) else 0

                # Log progress periodically
                if attempt > 0 and attempt % 12 == 0:
                    elapsed_min = (attempt * poll_interval) / 60
                    logger.info(f"[Comments] Still running after {elapsed_min:.0f}min, {items_count} items so far...")
                    if progress_callback:
                        await progress_callback(
                            f"Scraping comments... {items_count} found ({elapsed_min:.0f}min elapsed)"
                        )

                if run_status == "SUCCEEDED":
                    dataset_id = status_data["defaultDatasetId"]
                    usage_usd = status_data.get("usageTotalUsd", "?")
                    logger.info(f"[Comments] Succeeded. Dataset: {dataset_id}, cost: ${usage_usd}")

                    # Fetch results with pagination
                    all_items = []
                    offset = 0
                    page_size = 1000
                    while True:
                        async with httpx.AsyncClient() as client:
                            response = await client.get(
                                f"{APIFY_BASE_URL}/datasets/{dataset_id}/items",
                                headers=self.headers,
                                params={"format": "json", "offset": offset, "limit": page_size},
                                timeout=120,
                            )
                            response.raise_for_status()
                            page = response.json()
                        all_items.extend(page)
                        if len(page) < page_size:
                            break
                        offset += page_size

                    logger.info(f"[Comments] Total items fetched: {len(all_items)}")
                    if all_items:
                        logger.info(f"[Comments] First item keys: {list(all_items[0].keys())[:10]}")
                    if progress_callback:
                        await progress_callback(f"Scraping complete: {len(all_items)} comments found (cost: ${usage_usd})")

                    # Deduplicate by username
                    return self._deduplicate_comments(all_items)

                elif run_status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    logger.error(f"[Comments] Run failed: {run_status}")
                    if progress_callback:
                        await progress_callback(f"Comment scraping failed: {run_status}")
                    return []

                await asyncio.sleep(poll_interval)

            logger.warning(f"[Comments] Timed out after 15min of polling")
            return []

        except Exception as e:
            logger.error(f"[Comments] Error: {e}")
            if progress_callback:
                await progress_callback(f"Comment scraping error: {e}")
            return []

    def _deduplicate_comments(self, comments: list[dict]) -> list[dict]:
        """Deduplicate comments by username."""
        unique_comments = []
        seen_usernames = set()

        for comment in comments:
            uname = (
                comment.get("ownerUsername")
                or comment.get("username")
                or comment.get("owner", {}).get("username", "")
                or ""
            )
            if uname and uname not in seen_usernames:
                seen_usernames.add(uname)
                unique_comments.append(comment)

        logger.info(f"[Comments] Deduplicated: {len(comments)} raw → {len(unique_comments)} unique usernames")
        return unique_comments

    async def scrape_profiles_sync(self, usernames: list[str]) -> list[dict]:
        """Use synchronous Apify endpoint for profile scraping."""
        actor_id = ACTORS["profiles"]
        input_data = {"usernames": usernames}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{APIFY_BASE_URL}/acts/{actor_id}/run-sync-get-dataset-items",
                headers=self.headers,
                json=input_data,
                timeout=300,
            )
            response.raise_for_status()
            return response.json()

    async def save_leads(
        self,
        profiles: list[dict],
        campaign_id: str,
        client_id: str,
        db: AsyncSession,
    ) -> int:
        """Save scraped profiles as leads with deduplication."""
        saved = 0
        logger.info(f"Processing {len(profiles)} profiles for saving")
        if profiles:
            logger.info(f"Sample profile keys: {list(profiles[0].keys())[:15]}")
        for profile in profiles:
            username = profile.get("username") or profile.get("ownerUsername") or ""
            if not username:
                logger.warning(f"Skipping profile with no username: {list(profile.keys())[:10]}")
                continue
            if profile.get("isPrivate", False):
                logger.info(f"Skipping private profile: {username}")
                continue

            # Handle externalUrl - can be string, dict, or list
            website = ""
            raw_url = profile.get("externalUrl")
            if isinstance(raw_url, str) and raw_url:
                website = raw_url
            elif isinstance(raw_url, dict):
                website = raw_url.get("url", "") or raw_url.get("lynx_url", "") or ""
            if not website:
                ext_urls = profile.get("externalUrls") or []
                if isinstance(ext_urls, list):
                    for eu in ext_urls:
                        if isinstance(eu, str) and eu:
                            website = eu
                            break
                        elif isinstance(eu, dict):
                            website = eu.get("url", "") or eu.get("lynx_url", "") or ""
                            if website:
                                break

            # Handle profile pic - try multiple field names
            profile_pic = (
                profile.get("profilePicUrl")
                or profile.get("profilePicUrlHD")
                or ""
            )

            # Capture latest posts/reels from the profile scraper
            latest_posts = profile.get("latestPosts") or []
            # Keep only useful fields per post to save DB space
            posts_data = []
            for post in latest_posts[:12]:  # max 12 posts
                posts_data.append({
                    "shortCode": post.get("shortCode", ""),
                    "caption": (post.get("caption") or "")[:500],
                    "likesCount": post.get("likesCount", 0),
                    "commentsCount": post.get("commentsCount", 0),
                    "timestamp": post.get("timestamp", ""),
                    "type": post.get("type", post.get("__typename", "post")),
                    "url": post.get("url", ""),
                    "displayUrl": post.get("displayUrl", ""),
                    "videoViewCount": post.get("videoViewCount"),
                    "isVideo": post.get("isVideo", False),
                })

            stmt = pg_insert(Lead).values(
                campaign_id=campaign_id,
                client_id=client_id,
                ig_username=username,
                ig_full_name=profile.get("fullName"),
                ig_bio=profile.get("biography"),
                ig_website=website,
                ig_category=profile.get("businessCategoryName"),
                ig_follower_count=profile.get("followersCount"),
                ig_following_count=profile.get("followsCount"),
                ig_is_private=profile.get("isPrivate", False),
                ig_profile_pic_url=profile_pic,
                ig_posts=posts_data if posts_data else None,
                status="scraped",
                scraped_at=datetime.now(timezone.utc),
            ).on_conflict_do_nothing(
                constraint="uq_leads_client_username"
            )
            result = await db.execute(stmt)
            if result.rowcount > 0:
                saved += 1

        await db.flush()
        return saved

    def _build_input(self, source_type: str, source_value: str, max_leads: int = 0) -> dict:
        if source_type == "followers":
            # "followers" now uses the profile scraper as fallback (free tier).
            # Treat source_value as comma-separated usernames to scrape profiles for.
            usernames = [u.strip() for u in source_value.split(",") if u.strip()]
            if not usernames:
                usernames = [source_value]
            return {"usernames": usernames}
        elif source_type == "comments":
            # apify~instagram-scraper with resultsType=comments
            data: dict = {
                "directUrls": [source_value],
                "resultsType": "comments",
                "searchLimit": 1,
            }
            if max_leads > 0:
                data["resultsLimit"] = max_leads
            return data
        elif source_type == "profiles":
            usernames = [u.strip() for u in source_value.split(",") if u.strip()]
            return {"usernames": usernames}
        else:
            raise ValueError(f"Unknown source type: {source_type}")


apify_service = ApifyService()

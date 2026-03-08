import logging
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

ACTORS = {
    "followers": "louisdeconinck~instagram-following-scraper",
    "comments": "apidojo~instagram-comments-scraper",
    "profiles": "danek~instagram-profiles-scraper-ppr",
}


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
        self, source_type: str, source_value: str, campaign_id: str, db: AsyncSession
    ) -> ScrapeJob:
        actor_id = ACTORS.get(source_type)
        if not actor_id:
            raise ValueError(f"Unknown source type: {source_type}")

        input_data = self._build_input(source_type, source_value)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{APIFY_BASE_URL}/acts/{actor_id}/runs",
                headers=self.headers,
                json=input_data,
                timeout=30,
            )
            response.raise_for_status()
            run_data = response.json()["data"]

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
            return response.json()

    async def scrape_profiles_sync(self, usernames: list[str]) -> list[dict]:
        """Use synchronous Apify endpoint for profile scraping."""
        actor_id = ACTORS["profiles"]
        input_data = {"usernames": usernames}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{APIFY_BASE_URL}/acts/{actor_id}/run-sync-get-dataset-items",
                headers=self.headers,
                json=input_data,
                timeout=120,
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
            username = profile.get("username", "")
            if not username:
                logger.warning(f"Skipping profile with no username: {list(profile.keys())[:10]}")
                continue
            if profile.get("isPrivate", False):
                logger.info(f"Skipping private profile: {username}")
                continue

            stmt = pg_insert(Lead).values(
                campaign_id=campaign_id,
                client_id=client_id,
                ig_username=profile.get("username", ""),
                ig_full_name=profile.get("fullName"),
                ig_bio=profile.get("biography"),
                ig_website=profile.get("externalUrl"),
                ig_category=profile.get("businessCategoryName"),
                ig_follower_count=profile.get("followersCount"),
                ig_following_count=profile.get("followsCount"),
                ig_is_private=profile.get("isPrivate", False),
                ig_profile_pic_url=profile.get("profilePicUrl"),
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

    def _build_input(self, source_type: str, source_value: str) -> dict:
        if source_type == "followers":
            return {"usernames": [source_value]}
        elif source_type == "comments":
            return {"directUrls": [source_value]}
        elif source_type == "profiles":
            # Support comma-separated usernames
            usernames = [u.strip() for u in source_value.split(",") if u.strip()]
            return {"usernames": usernames}
        else:
            raise ValueError(f"Unknown source type: {source_type}")


apify_service = ApifyService()

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign
from app.models.scrape_job import ScrapeJob
from app.services.apify_service import apify_service

router = APIRouter()


class ScrapeFollowersRequest(BaseModel):
    campaign_id: uuid.UUID
    username: str


class ScrapeCommentsRequest(BaseModel):
    campaign_id: uuid.UUID
    post_url: str


@router.post("/followers")
async def scrape_followers(
    data: ScrapeFollowersRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Campaign).where(Campaign.id == data.campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    scrape_job = await apify_service.start_scrape(
        "followers", data.username, str(data.campaign_id), db
    )
    await db.commit()
    return {
        "job_id": str(scrape_job.id),
        "status": scrape_job.status,
        "apify_run_id": scrape_job.apify_run_id,
    }


@router.post("/comments")
async def scrape_comments(
    data: ScrapeCommentsRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Campaign).where(Campaign.id == data.campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    scrape_job = await apify_service.start_scrape(
        "comments", data.post_url, str(data.campaign_id), db
    )
    await db.commit()
    return {
        "job_id": str(scrape_job.id),
        "status": scrape_job.status,
        "apify_run_id": scrape_job.apify_run_id,
    }


@router.get("/jobs")
async def list_scrape_jobs(
    campaign_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ScrapeJob)
    if campaign_id:
        query = query.where(ScrapeJob.campaign_id == campaign_id)
    query = query.order_by(ScrapeJob.created_at.desc())
    result = await db.execute(query)
    jobs = result.scalars().all()
    return [
        {
            "id": str(j.id),
            "campaign_id": str(j.campaign_id),
            "apify_run_id": j.apify_run_id,
            "actor_type": j.actor_type,
            "status": j.status,
            "items_found": j.items_found,
            "error_message": j.error_message,
            "started_at": j.started_at,
            "completed_at": j.completed_at,
        }
        for j in jobs
    ]


@router.get("/jobs/{job_id}")
async def get_scrape_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    return {
        "id": str(job.id),
        "campaign_id": str(job.campaign_id),
        "apify_run_id": job.apify_run_id,
        "apify_dataset_id": job.apify_dataset_id,
        "actor_type": job.actor_type,
        "status": job.status,
        "items_found": job.items_found,
        "error_message": job.error_message,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }

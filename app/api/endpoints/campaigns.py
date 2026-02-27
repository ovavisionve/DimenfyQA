import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign
from app.models.lead import Lead
from app.schemas.campaign import CampaignCreate, CampaignRead, CampaignStats, CampaignUpdate
from app.tasks.pipeline import run_campaign_pipeline

router = APIRouter()


@router.post("/", response_model=CampaignRead, status_code=201)
async def create_campaign(data: CampaignCreate, db: AsyncSession = Depends(get_db)):
    campaign = Campaign(
        client_id=data.client_id,
        name=data.name,
        source_type=data.source_type,
        source_value=data.source_value,
        settings=data.settings,
    )
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.get("/", response_model=list[CampaignRead])
async def list_campaigns(
    client_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Campaign)
    if client_id:
        query = query.where(Campaign.client_id == client_id)
    query = query.order_by(Campaign.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{campaign_id}", response_model=CampaignRead)
async def get_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.post("/{campaign_id}/start")
async def start_campaign_pipeline(
    campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status not in ("pending", "ready"):
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is currently '{campaign.status}', cannot start",
        )

    task_id = run_campaign_pipeline(str(campaign_id))
    return {"message": "Pipeline started", "task_id": task_id, "campaign_id": str(campaign_id)}


@router.get("/{campaign_id}/stats", response_model=CampaignStats)
async def get_campaign_stats(
    campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Count leads by status
    total = await db.execute(
        select(func.count()).where(Lead.campaign_id == campaign_id)
    )
    scored = await db.execute(
        select(func.count()).where(
            Lead.campaign_id == campaign_id, Lead.score.isnot(None)
        )
    )
    researched = await db.execute(
        select(func.count()).where(
            Lead.campaign_id == campaign_id, Lead.research_data.isnot(None)
        )
    )
    dm_ready = await db.execute(
        select(func.count()).where(
            Lead.campaign_id == campaign_id, Lead.dm_message.isnot(None)
        )
    )
    avg_score = await db.execute(
        select(func.avg(Lead.score)).where(
            Lead.campaign_id == campaign_id, Lead.score.isnot(None)
        )
    )

    return CampaignStats(
        campaign_id=campaign_id,
        total_leads=total.scalar() or 0,
        scored_leads=scored.scalar() or 0,
        researched_leads=researched.scalar() or 0,
        dm_ready_leads=dm_ready.scalar() or 0,
        avg_score=avg_score.scalar(),
        status=campaign.status,
    )

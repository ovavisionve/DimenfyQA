import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.database import get_db
from app.models.lead import Lead
from app.schemas.lead import LeadDMReady, LeadDetail, LeadRead, LeadScored

router = APIRouter()


@router.get("/", response_model=list[LeadRead])
async def list_leads(
    campaign_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    status: str | None = None,
    min_score: int | None = None,
    category: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Lead).options(
        defer(Lead.research_data),
        defer(Lead.ig_posts),
        defer(Lead.ig_post_analysis),
    )

    if campaign_id:
        query = query.where(Lead.campaign_id == campaign_id)
    if client_id:
        query = query.where(Lead.client_id == client_id)
    if status:
        query = query.where(Lead.status == status)
    if min_score is not None:
        query = query.where(Lead.score >= min_score)
    if category:
        query = query.where(Lead.lead_category == category)

    query = query.order_by(Lead.score.desc().nullslast()).offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/scored", response_model=list[LeadScored])
async def list_scored_leads(
    campaign_id: uuid.UUID | None = None,
    min_score: int = Query(default=0),
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    query = select(Lead).where(Lead.score.isnot(None), Lead.score >= min_score)
    if campaign_id:
        query = query.where(Lead.campaign_id == campaign_id)
    query = query.order_by(Lead.score.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/dm-ready", response_model=list[LeadDMReady])
async def list_dm_ready_leads(
    campaign_id: uuid.UUID | None = None,
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    query = select(Lead).where(Lead.status == "dm_ready", Lead.dm_message.isnot(None))
    if campaign_id:
        query = query.where(Lead.campaign_id == campaign_id)
    query = query.order_by(Lead.score.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead

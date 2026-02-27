import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.message import Message
from app.schemas.message import MessageRead

router = APIRouter()


@router.get("/", response_model=list[MessageRead])
async def list_messages(
    campaign_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Message)

    if campaign_id:
        query = query.where(Message.campaign_id == campaign_id)
    if client_id:
        query = query.where(Message.client_id == client_id)
    if lead_id:
        query = query.where(Message.lead_id == lead_id)

    query = query.order_by(Message.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

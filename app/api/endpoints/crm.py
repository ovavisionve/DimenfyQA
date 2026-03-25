"""CRM API endpoints — Kanban pipeline with dynamic scoring."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.crm_service import crm_service

router = APIRouter()


# ------------------------------------------------------------------ #
# Request schemas
# ------------------------------------------------------------------ #
class MoveLeadRequest(BaseModel):
    stage: str


class NoteRequest(BaseModel):
    content: str
    user_id: Optional[str] = None


# ------------------------------------------------------------------ #
# Endpoints
# ------------------------------------------------------------------ #

@router.get("/board")
async def get_board(
    campaign_id: Optional[str] = None,
    client_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get the full CRM Kanban board."""
    return await crm_service.get_pipeline_board(db, campaign_id=campaign_id, client_id=client_id)


@router.get("/board/stats")
async def get_board_stats(
    campaign_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get metrics per stage: count, avg score, response/interest rates."""
    return await crm_service.get_board_stats(db, campaign_id=campaign_id)


@router.patch("/leads/{lead_id}/stage")
async def move_lead(lead_id: str, data: MoveLeadRequest, db: AsyncSession = Depends(get_db)):
    """Move a lead to a different CRM stage."""
    result = await crm_service.move_lead(lead_id, data.stage, db)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/leads/{lead_id}")
async def get_lead_detail(lead_id: str, db: AsyncSession = Depends(get_db)):
    """Get full lead detail with score history, notes, conversation."""
    result = await crm_service.get_lead_detail(lead_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result


@router.post("/leads/{lead_id}/notes")
async def add_note(lead_id: str, data: NoteRequest, db: AsyncSession = Depends(get_db)):
    """Add a note to a lead."""
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="Note content cannot be empty")
    result = await crm_service.add_note(lead_id, data.content.strip(), db, user_id=data.user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result


@router.get("/leads/{lead_id}/score-history")
async def get_score_history(lead_id: str, db: AsyncSession = Depends(get_db)):
    """Get score change timeline for a lead."""
    return await crm_service.get_score_history(lead_id, db)

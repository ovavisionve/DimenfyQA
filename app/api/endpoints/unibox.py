"""Unibox API endpoints — unified inbox with AI-assisted replies."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.unibox_service import unibox_service

router = APIRouter()


# ------------------------------------------------------------------ #
# Request/Response schemas
# ------------------------------------------------------------------ #
class ReplyRequest(BaseModel):
    message: str


class ConversationUpdate(BaseModel):
    conversation_status: Optional[str] = None
    reply_classification: Optional[str] = None


# ------------------------------------------------------------------ #
# Endpoints
# ------------------------------------------------------------------ #

@router.get("/conversations")
async def list_conversations(
    campaign_id: Optional[str] = None,
    client_id: Optional[str] = None,
    classification: Optional[str] = None,
    conversation_status: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "recent",
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all conversations with filters and pagination."""
    return await unibox_service.get_all_conversations(
        db,
        campaign_id=campaign_id,
        client_id=client_id,
        classification=classification,
        conversation_status=conversation_status,
        search=search,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{lead_id}/thread")
async def get_thread(lead_id: str, db: AsyncSession = Depends(get_db)):
    """Get full conversation thread for a lead."""
    result = await unibox_service.get_conversation_thread(lead_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result


@router.post("/conversations/{lead_id}/reply")
async def send_reply(lead_id: str, data: ReplyRequest, db: AsyncSession = Depends(get_db)):
    """Send a manual reply to a lead via Instagram DM."""
    if not data.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    result = await unibox_service.send_reply(lead_id, data.message.strip(), db)

    if not result["success"]:
        raise HTTPException(status_code=502, detail=result["error"])

    # Mark suggestion as used if one existed
    await unibox_service.mark_suggestion_used(lead_id, db)

    return result


@router.get("/conversations/{lead_id}/suggestions")
async def get_suggestions(lead_id: str, db: AsyncSession = Depends(get_db)):
    """Get pre-generated AI reply suggestions for a lead."""
    result = await unibox_service.get_suggestions(lead_id, db)
    if not result:
        return {"suggestions": None, "generated_at": None}
    return result


@router.post("/conversations/{lead_id}/suggest")
async def generate_suggestions(lead_id: str, db: AsyncSession = Depends(get_db)):
    """Force (re)generate AI reply suggestions for a lead."""
    result = await unibox_service.generate_reply_suggestions(lead_id, db)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to generate suggestions")
    return result


@router.patch("/conversations/{lead_id}")
async def update_conversation(
    lead_id: str, data: ConversationUpdate, db: AsyncSession = Depends(get_db),
):
    """Update conversation state (status, classification)."""
    from app.models.lead import Lead

    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if data.conversation_status is not None:
        lead.conversation_status = data.conversation_status
    if data.reply_classification is not None:
        lead.reply_classification = data.reply_classification

    await db.commit()
    return {"updated": True}


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Unibox stats: unreplied count, classification breakdown."""
    return await unibox_service.get_stats(db)

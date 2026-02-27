import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.export_service import export_service

router = APIRouter()


@router.get("/{campaign_id}/csv")
async def export_csv(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    csv_content = await export_service.export_csv(str(campaign_id), db)
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_leads.csv"},
    )


@router.get("/{campaign_id}/json")
async def export_json(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    data = await export_service.export_json(str(campaign_id), db)
    return data

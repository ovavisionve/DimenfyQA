import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign
from app.services.export_service import export_service

router = APIRouter()


async def _validate_campaign(campaign_id: uuid.UUID, db: AsyncSession) -> None:
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campaign not found")


@router.get("/{campaign_id}/csv")
async def export_csv(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _validate_campaign(campaign_id, db)
    csv_content = await export_service.export_csv(str(campaign_id), db)
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_leads.csv"},
    )


@router.get("/{campaign_id}/json")
async def export_json(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _validate_campaign(campaign_id, db)
    data = await export_service.export_json(str(campaign_id), db)
    return data


@router.get("/{campaign_id}/excel")
async def export_excel(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _validate_campaign(campaign_id, db)
    excel_bytes = await export_service.export_excel(str(campaign_id), db)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_leads.xlsx"},
    )

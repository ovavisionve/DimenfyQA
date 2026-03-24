import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign
from app.services.content_analysis_service import content_analysis_service

router = APIRouter()


class ContentAnalysisRequest(BaseModel):
    content_urls: list[str] | None = None
    content_text: str | None = None


class CampaignContentRequest(BaseModel):
    campaign_id: uuid.UUID
    content_urls: list[str] | None = None
    content_text: str | None = None


@router.post("/analyze")
async def analyze_content(data: ContentAnalysisRequest):
    """
    Analyze content (video, image, webpage, text) using Gemini multimodal.
    Standalone endpoint — does not save to any campaign.
    """
    if not data.content_urls and not data.content_text:
        raise HTTPException(status_code=400, detail="Provide at least one content_url or content_text")

    result = await content_analysis_service.analyze_content(
        content_urls=data.content_urls,
        content_text=data.content_text,
    )

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    return result


@router.post("/analyze-for-campaign")
async def analyze_for_campaign(
    data: CampaignContentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze content and save the analysis to a campaign's settings.
    This analysis is then used by scoring, research, and copywriting phases.
    """
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == data.campaign_id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not data.content_urls and not data.content_text:
        raise HTTPException(status_code=400, detail="Provide at least one content_url or content_text")

    result = await content_analysis_service.analyze_campaign_content(
        campaign_id=str(data.campaign_id),
        db=db,
        content_urls=data.content_urls,
        content_text=data.content_text,
    )

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    await db.commit()
    return {
        "campaign_id": str(data.campaign_id),
        "analysis": result,
        "message": "Content analysis saved to campaign. It will be used in scoring, research, and DM generation.",
    }


@router.get("/campaign/{campaign_id}")
async def get_campaign_analysis(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the stored content analysis for a campaign."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    analysis = (campaign.settings or {}).get("content_analysis")
    if not analysis:
        return {
            "campaign_id": str(campaign_id),
            "has_analysis": False,
            "analysis": None,
        }

    return {
        "campaign_id": str(campaign_id),
        "has_analysis": True,
        "analysis": analysis,
        "content_urls": (campaign.settings or {}).get("content_urls", []),
    }

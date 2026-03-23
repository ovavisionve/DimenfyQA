import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign
from app.models.lead import Lead
from app.schemas.ab_testing import ABTestResults
from app.schemas.analytics import CampaignAnalytics
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

    if campaign.status not in ("pending", "ready", "failed", "paused"):
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is currently '{campaign.status}', cannot start. Reset first.",
        )

    task_id = run_campaign_pipeline(str(campaign_id))
    return {"message": "Pipeline started", "task_id": task_id, "campaign_id": str(campaign_id)}


@router.post("/{campaign_id}/reset")
async def reset_campaign(
    campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Reset a campaign: delete all leads and set status back to pending."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from sqlalchemy import delete
    await db.execute(delete(Lead).where(Lead.campaign_id == campaign_id))
    campaign.status = "pending"
    campaign.stats = {}
    await db.flush()

    return {"message": "Campaign reset", "campaign_id": str(campaign_id)}


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

    sent = await db.execute(
        select(func.count()).where(
            Lead.campaign_id == campaign_id, Lead.status == "sent"
        )
    )
    failed = await db.execute(
        select(func.count()).where(
            Lead.campaign_id == campaign_id, Lead.status == "failed"
        )
    )

    return CampaignStats(
        campaign_id=campaign_id,
        total_leads=total.scalar() or 0,
        scored_leads=scored.scalar() or 0,
        researched_leads=researched.scalar() or 0,
        dm_ready_leads=dm_ready.scalar() or 0,
        sent_leads=sent.scalar() or 0,
        failed_leads=failed.scalar() or 0,
        avg_score=avg_score.scalar(),
        status=campaign.status,
    )


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Pause a running campaign (stops DM sending)."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status != "sending":
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is '{campaign.status}', can only pause while sending.",
        )

    campaign.status = "paused"
    stats = dict(campaign.stats or {})
    stats["send_error"] = "Manually paused by user"
    campaign.stats = stats
    await db.flush()

    return {"message": "Campaign paused", "campaign_id": str(campaign_id)}


@router.post("/{campaign_id}/resume-sending")
async def resume_sending(
    campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Resume sending DMs for a paused campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status not in ("paused", "ready"):
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is '{campaign.status}', can only send from paused or ready.",
        )

    from app.tasks.sending_tasks import send_dms_task

    # Get dm_ready + retry leads for this campaign
    dm_leads = await db.execute(
        select(Lead.id).where(
            Lead.campaign_id == campaign_id,
            Lead.status.in_(["dm_ready", "retry"]),
        )
    )
    lead_ids = [str(lid) for lid in dm_leads.scalars().all()]

    if not lead_ids:
        raise HTTPException(status_code=400, detail="No leads ready to send")

    campaign.status = "sending"
    await db.flush()

    task_result = send_dms_task.delay(lead_ids)
    return {
        "message": "Sending started",
        "campaign_id": str(campaign_id),
        "task_id": task_result.id,
        "leads_to_send": len(lead_ids),
    }


@router.post("/{campaign_id}/check-inbox")
async def check_campaign_inbox(
    campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Manually trigger an inbox check for a campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.tasks.inbox_tasks import check_inbox_task

    task_result = check_inbox_task.delay(str(campaign_id))
    return {
        "message": "Inbox check started",
        "campaign_id": str(campaign_id),
        "task_id": task_result.id,
    }


@router.get("/{campaign_id}/replies")
async def get_campaign_replies(
    campaign_id: uuid.UUID,
    classification: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get all leads that have replied for a campaign, with classification info."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.schemas.lead import LeadRead

    query = select(Lead).where(
        Lead.campaign_id == campaign_id,
        Lead.replied_at.isnot(None),
    )

    if classification:
        query = query.where(Lead.reply_classification == classification)

    query = query.order_by(Lead.replied_at.desc())
    leads_result = await db.execute(query)
    leads = leads_result.scalars().all()

    return {
        "campaign_id": str(campaign_id),
        "total_replies": len(leads),
        "leads": [LeadRead.model_validate(lead) for lead in leads],
    }


@router.get("/{campaign_id}/ab-results", response_model=ABTestResults)
async def get_ab_results(
    campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Return A/B test results for a campaign's DM variants."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.services.ab_testing_service import ab_testing_service

    ab_results = await ab_testing_service.get_campaign_ab_results(str(campaign_id), db)
    return ab_results


@router.get("/{campaign_id}/analytics", response_model=CampaignAnalytics)
async def get_campaign_analytics(
    campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Return full analytics for a campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.services.analytics_service import analytics_service

    analytics = await analytics_service.get_campaign_analytics(str(campaign_id), db)
    return analytics


@router.get("/ig-accounts/health")
async def get_ig_accounts_health():
    """Return health metrics for all configured Instagram accounts."""
    from app.services.dm_sender_service import dm_sender_service
    return {"accounts": dm_sender_service.get_accounts_health()}

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

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
    query = select(Campaign).options(
        noload(Campaign.leads),
        noload(Campaign.scrape_jobs),
        noload(Campaign.follow_up_rules),
    )
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


@router.patch("/{campaign_id}", response_model=CampaignRead)
async def update_campaign(
    campaign_id: uuid.UUID, data: CampaignUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if data.name is not None:
        campaign.name = data.name
    if data.settings is not None:
        campaign.settings = data.settings
    if data.status is not None:
        campaign.status = data.status.value

    await db.flush()
    await db.refresh(campaign)
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
        # Idempotency: if already running, return existing task_id
        if campaign.celery_task_id:
            return {
                "message": "Pipeline already running",
                "task_id": campaign.celery_task_id,
                "campaign_id": str(campaign_id),
            }
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is currently '{campaign.status}', cannot start. Reset first.",
        )

    # Clear previous task_id before starting new pipeline
    campaign.celery_task_id = None
    await db.commit()

    task_id = run_campaign_pipeline(str(campaign_id))
    return {"message": "Pipeline started", "task_id": task_id, "campaign_id": str(campaign_id)}


@router.post("/{campaign_id}/reprocess")
async def reprocess_campaign(
    campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Re-run scoring → research → DM generation for existing leads.

    Useful when a previous run failed mid-pipeline (e.g. no API credits)
    and the leads are already scraped. Skips the scraping phase entirely.
    """
    from app.tasks.pipeline import resume_campaign

    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status not in ("ready", "failed", "paused", "completed"):
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is currently '{campaign.status}', cannot reprocess.",
        )

    lead_count = await db.execute(
        select(func.count()).where(Lead.campaign_id == campaign_id)
    )
    if lead_count.scalar() == 0:
        raise HTTPException(
            status_code=400,
            detail="No leads to reprocess. Use 'start' to run the full pipeline.",
        )

    # Reset lead statuses so scoring picks them up again
    from sqlalchemy import update
    await db.execute(
        update(Lead)
        .where(Lead.campaign_id == campaign_id)
        .values(status="scraped", score=None, dm_text=None, dm_variant_b=None)
    )

    campaign.celery_task_id = None
    campaign.status = "scoring"
    await db.commit()

    task_id = resume_campaign(str(campaign_id), "score")
    if not task_id:
        raise HTTPException(status_code=500, detail="Failed to start reprocessing")

    return {"message": "Reprocessing started (score → research → DMs)", "task_id": task_id, "campaign_id": str(campaign_id)}


@router.post("/{campaign_id}/reset")
async def reset_campaign(
    campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Reset a campaign: revoke tasks, delete all leads, set status to pending."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Revoke Celery task if running
    if campaign.celery_task_id:
        try:
            from app.tasks.celery_app import celery_app
            celery_app.control.revoke(campaign.celery_task_id, terminate=True)
        except Exception:
            pass

    from sqlalchemy import delete
    await db.execute(delete(Lead).where(Lead.campaign_id == campaign_id))
    campaign.status = "pending"
    campaign.stats = {}
    campaign.celery_task_id = None
    campaign.last_phase = None
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
    """Pause/stop a running campaign at any phase."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    active_statuses = ("sending", "scraping", "scoring", "researching", "writing_dms", "pending")
    if campaign.status not in active_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is '{campaign.status}', cannot pause.",
        )

    # Revoke Celery task if running
    if campaign.celery_task_id:
        try:
            from app.tasks.celery_app import celery_app
            celery_app.control.revoke(campaign.celery_task_id, terminate=True)
        except Exception:
            pass

    campaign.status = "failed"
    campaign.celery_task_id = None
    stats = dict(campaign.stats or {})
    stats["send_error"] = "Manually stopped by user"
    campaign.stats = stats
    await db.flush()

    return {"message": "Campaign stopped", "campaign_id": str(campaign_id)}


@router.post("/{campaign_id}/resume-sending")
@router.post("/{campaign_id}/send-dms")
async def resume_sending(
    campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Resume/start sending DMs for a campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status not in ("paused", "ready", "failed"):
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is '{campaign.status}', can only send from paused, ready, or failed.",
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


@router.post("/{campaign_id}/send-dm/{lead_id}")
async def send_single_dm(
    campaign_id: uuid.UUID, lead_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Send a single DM to a specific lead."""
    result = await db.execute(select(Lead).where(Lead.id == lead_id, Lead.campaign_id == campaign_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found in this campaign")

    if not lead.dm_message:
        raise HTTPException(status_code=400, detail="Lead has no DM generated")

    from app.tasks.sending_tasks import send_dms_task

    task_result = send_dms_task.delay([str(lead_id)])
    return {
        "message": f"Sending DM to @{lead.ig_username}",
        "campaign_id": str(campaign_id),
        "lead_id": str(lead_id),
        "task_id": task_result.id,
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

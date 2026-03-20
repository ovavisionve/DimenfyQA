import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign
from app.models.follow_up_rule import FollowUpRule
from app.schemas.follow_up import FollowUpRuleCreate, FollowUpRuleRead, FollowUpRuleUpdate

router = APIRouter()


@router.post("/", response_model=FollowUpRuleRead, status_code=201)
async def create_follow_up_rule(
    data: FollowUpRuleCreate, db: AsyncSession = Depends(get_db)
):
    """Create a follow-up rule for a campaign."""
    # Verify campaign exists and get client_id
    result = await db.execute(
        select(Campaign).where(Campaign.id == data.campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Check step_number uniqueness for this campaign
    existing = await db.execute(
        select(FollowUpRule).where(
            FollowUpRule.campaign_id == data.campaign_id,
            FollowUpRule.step_number == data.step_number,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Follow-up rule for step {data.step_number} already exists in this campaign",
        )

    rule = FollowUpRule(
        campaign_id=data.campaign_id,
        client_id=campaign.client_id,
        step_number=data.step_number,
        delay_days=data.delay_days,
        template_prompt=data.template_prompt,
        max_attempts=data.max_attempts,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


@router.get("/", response_model=list[FollowUpRuleRead])
async def list_follow_up_rules(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """List follow-up rules for a campaign."""
    result = await db.execute(
        select(FollowUpRule).where(
            FollowUpRule.campaign_id == campaign_id
        ).order_by(FollowUpRule.step_number)
    )
    return result.scalars().all()


@router.put("/{rule_id}", response_model=FollowUpRuleRead)
async def update_follow_up_rule(
    rule_id: uuid.UUID,
    data: FollowUpRuleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a follow-up rule."""
    result = await db.execute(
        select(FollowUpRule).where(FollowUpRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Follow-up rule not found")

    if data.delay_days is not None:
        rule.delay_days = data.delay_days
    if data.template_prompt is not None:
        rule.template_prompt = data.template_prompt
    if data.is_active is not None:
        rule.is_active = data.is_active

    await db.flush()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
async def delete_follow_up_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a follow-up rule."""
    result = await db.execute(
        select(FollowUpRule).where(FollowUpRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Follow-up rule not found")

    await db.delete(rule)
    await db.flush()


@router.post("/{campaign_id}/process")
async def trigger_follow_up_processing(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger follow-up processing for a campaign."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.tasks.followup_tasks import process_follow_ups_task

    task_result = process_follow_ups_task.delay(str(campaign_id))
    return {
        "message": "Follow-up processing started",
        "campaign_id": str(campaign_id),
        "task_id": task_result.id,
    }

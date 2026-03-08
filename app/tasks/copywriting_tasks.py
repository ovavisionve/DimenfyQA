import logging

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, fail_campaign, update_progress, sync_update_progress, RETRY_KWARGS
from app.database import create_worker_session
from app.services.copywriting_service import copywriting_service

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="write_dms", **RETRY_KWARGS)
def write_dms_task(self, lead_ids: list[str]) -> list[str]:
    """Generate DMs for leads with score >= threshold. Returns dm-ready lead_ids."""
    logger.info(f"Writing DMs for {len(lead_ids)} candidates (attempt {self.request.retries + 1}/{self.max_retries + 1})")

    async def _write():
        async with create_worker_session()() as db:
            from sqlalchemy import select
            from app.models.lead import Lead
            from app.models.campaign import Campaign

            campaign_id = None

            # Update campaign status to "writing"
            if lead_ids:
                result = await db.execute(
                    select(Lead.campaign_id).where(Lead.id == lead_ids[0])
                )
                campaign_id = result.scalar_one_or_none()
                if campaign_id:
                    campaign_result = await db.execute(
                        select(Campaign).where(Campaign.id == str(campaign_id))
                    )
                    campaign = campaign_result.scalar_one_or_none()
                    if campaign:
                        campaign.status = "writing_dms"
                        await db.flush()

            cid = str(campaign_id) if campaign_id else None
            if cid:
                await update_progress(cid, "writing_dms",
                                "Starting DM generation with Claude AI...",
                                current=0, total=len(lead_ids),
                                detail="Filtering qualified leads (score >= 70)")

            def _writing_progress(cur, tot, uname):
                """Sync callback — runs in ThreadPoolExecutor threads."""
                if cid:
                    sync_update_progress(cid, "writing_dms",
                                    f"Writing DM {cur}/{tot}: @{uname}",
                                    current=cur, total=tot,
                                    detail="Generating Variant A + B with 8 parallel threads")

            dm_ready_ids = await copywriting_service.write_dms_batch(
                lead_ids, db, progress_callback=_writing_progress
            )

            # Update campaign to "completed"
            if campaign_id:
                campaign_result = await db.execute(
                    select(Campaign).where(Campaign.id == str(campaign_id))
                )
                campaign = campaign_result.scalar_one_or_none()
                if campaign:
                    campaign.status = "completed"

            await db.commit()
            logger.info(f"Generated DMs for {len(dm_ready_ids)} leads")

            if cid:
                await update_progress(cid, "completed",
                                f"Pipeline complete! {len(dm_ready_ids)} DMs generated.",
                                current=len(dm_ready_ids), total=len(dm_ready_ids),
                                detail="Ready to export")

            return dm_ready_ids

    try:
        return _run_async(_write())
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            try:
                async def _get_campaign():
                    async with create_worker_session()() as db:
                        from sqlalchemy import select
                        from app.models.lead import Lead
                        result = await db.execute(
                            select(Lead.campaign_id).where(Lead.id == lead_ids[0])
                        )
                        return str(result.scalar_one_or_none())
                campaign_id = _run_async(_get_campaign()) if lead_ids else None
                if campaign_id:
                    fail_campaign(campaign_id, f"DM generation failed after {self.max_retries + 1} attempts: {exc}")
            except Exception:
                logger.exception("Could not mark campaign as failed")
        raise

import logging

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, fail_campaign, update_progress, sync_update_progress, RETRY_KWARGS
from app.database import create_worker_session
from app.services.browser_manager import get_sender_service

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="send_dms", **RETRY_KWARGS)
def send_dms_task(self, lead_ids: list[str]) -> list[str]:
    """Send DMs for leads with status=dm_ready. Returns sent lead_ids."""
    logger.info(f"Starting DM sending for {len(lead_ids)} candidates (attempt {self.request.retries + 1}/{self.max_retries + 1})")

    async def _send():
        async with create_worker_session()() as db:
            from sqlalchemy import select
            from app.models.lead import Lead
            from app.models.campaign import Campaign

            campaign_id = None

            # Get campaign_id from first lead
            if lead_ids:
                result = await db.execute(
                    select(Lead.campaign_id).where(Lead.id == lead_ids[0])
                )
                campaign_id = result.scalar_one_or_none()

            if not campaign_id:
                logger.error("Cannot determine campaign_id from leads")
                return lead_ids  # Pass through so pipeline doesn't break

            cid = str(campaign_id)

            # Update campaign status to "sending"
            campaign_result = await db.execute(
                select(Campaign).where(Campaign.id == cid)
            )
            campaign = campaign_result.scalar_one_or_none()
            if campaign:
                campaign.status = "sending"
                await db.commit()

            await update_progress(cid, "sending",
                            "Logging into Instagram...",
                            current=0, total=len(lead_ids),
                            detail="Establishing connection")

            # Get the right sender engine (Playwright or instagrapi)
            sender = get_sender_service()
            from app.config import settings
            use_pw = settings.USE_PLAYWRIGHT

            # Login to Instagram (async for Playwright, sync for instagrapi)
            if use_pw:
                logged_in = await sender.login()
            else:
                logged_in = sender.login()

            if not logged_in:
                await update_progress(cid, "sending",
                                "Instagram login failed — check credentials",
                                current=0, total=len(lead_ids),
                                detail="Login error")
                campaign_result = await db.execute(
                    select(Campaign).where(Campaign.id == cid)
                )
                campaign = campaign_result.scalar_one_or_none()
                if campaign:
                    campaign.status = "paused"
                    stats = dict(campaign.stats or {})
                    stats["send_error"] = "Instagram login failed"
                    campaign.stats = stats
                    await db.commit()
                return lead_ids

            engine_name = "Playwright" if use_pw else "instagrapi"
            accounts_health = sender.get_accounts_health()
            active_accounts = sum(1 for h in accounts_health if h.get("logged_in"))
            await update_progress(cid, "sending",
                            f"Logged in ({engine_name}). Starting DM delivery...",
                            current=0, total=len(lead_ids),
                            detail=f"Active accounts: {active_accounts}")

            def _sending_progress(cur, tot, uname, success):
                """Sync callback for send progress."""
                status_text = "sent" if success else "failed"
                sync_update_progress(cid, "sending",
                                f"DM {cur}/{tot}: @{uname} ({status_text})",
                                current=cur, total=tot,
                                detail=f"Delay {settings.DM_DELAY_MIN}-{settings.DM_DELAY_MAX}s between sends")

            send_result = await sender.send_campaign_dms(
                cid, db, progress_callback=_sending_progress
            )

            sent = send_result["sent_count"]
            failed = send_result["failed_count"]
            skipped = send_result.get("skipped_count", 0)
            paused = send_result["paused"]
            reason = send_result["reason"]

            # Update campaign final status
            campaign_result = await db.execute(
                select(Campaign).where(Campaign.id == cid)
            )
            campaign = campaign_result.scalar_one_or_none()
            if campaign:
                if paused:
                    campaign.status = "paused"
                    stats = dict(campaign.stats or {})
                    stats["send_error"] = reason
                    stats["send_summary"] = {"sent": sent, "failed": failed, "skipped": skipped}
                    campaign.stats = stats
                else:
                    campaign.status = "completed"
                    stats = dict(campaign.stats or {})
                    stats["send_summary"] = {"sent": sent, "failed": failed, "skipped": skipped}
                    campaign.stats = stats
                await db.commit()

            phase = "paused" if paused else "completed"
            detail = reason if paused else "Ready to export"
            summary = f"Sending done: {sent} sent, {failed} failed, {skipped} skipped. {reason}"
            await update_progress(cid, phase, summary,
                            current=sent, total=sent + failed + skipped,
                            detail=detail)

            # Send in-app + Slack notification
            try:
                from app.services.notification_service import notification_service
                campaign_name = campaign.name if campaign else cid
                if paused:
                    await notification_service.notify(
                        db, title="Campaign Paused",
                        message=f"*{campaign_name}*: {sent} sent, {failed} failed. Reason: {reason}",
                        level="warning", link=f"/campaigns/{cid}",
                    )
                else:
                    await notification_service.on_campaign_completed(
                        db, campaign_name=campaign_name, campaign_id=cid,
                        stats={"total_leads": sent + failed + skipped, "sent": sent},
                    )
            except Exception:
                pass

            logger.info(f"DM sending complete: {sent} sent, {failed} failed, {skipped} skipped, paused={paused}")

            # Return all lead_ids for downstream (export)
            return lead_ids

    try:
        return _run_async(_send())
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
                    fail_campaign(campaign_id, f"DM sending failed after {self.max_retries + 1} attempts: {exc}")
            except Exception:
                logger.exception("Could not mark campaign as failed")
        raise

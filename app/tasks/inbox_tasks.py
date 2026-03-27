import logging

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, update_progress, RETRY_KWARGS
from app.database import create_worker_session

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="check_all_inboxes")
def check_all_inboxes_task(self) -> dict:
    """Celery Beat task: check inbox for ALL campaigns with sent DMs.

    Runs periodically (default every 5 min via INBOX_CHECK_INTERVAL).
    Finds campaigns that have sent DMs and dispatches individual
    check_inbox_task for each.
    """
    logger.info("Checking all campaigns for inbox replies")

    async def _check():
        from sqlalchemy import select, distinct, func
        from app.models.lead import Lead
        from app.models.campaign import Campaign

        async with create_worker_session()() as db:
            # Find campaigns that have at least one sent DM and are active
            result = await db.execute(
                select(distinct(Lead.campaign_id)).where(
                    Lead.status == "sent",
                ).join(
                    Campaign, Campaign.id == Lead.campaign_id
                ).where(
                    Campaign.status.in_(["completed", "sending", "ready", "paused"]),
                )
            )
            campaign_ids = [str(cid) for cid in result.scalars().all()]

        return campaign_ids

    try:
        campaign_ids = _run_async(_check())
        dispatched = 0

        for cid in campaign_ids:
            check_inbox_task.delay(cid)
            dispatched += 1

        logger.info(f"Dispatched inbox check for {dispatched} campaigns")
        return {"campaigns_checked": len(campaign_ids), "dispatched": dispatched}

    except Exception as exc:
        logger.exception(f"Failed to check campaigns for inbox: {exc}")
        raise


@celery_app.task(bind=True, name="check_inbox", **RETRY_KWARGS)
def check_inbox_task(self, campaign_id: str) -> dict:
    """Check Instagram inbox for replies to sent DMs in a campaign.

    Returns dict with new_replies count and classifications.
    """
    logger.info(
        f"Starting inbox check for campaign {campaign_id} "
        f"(attempt {self.request.retries + 1}/{self.max_retries + 1})"
    )

    async def _check():
        async with create_worker_session()() as db:
            from sqlalchemy import select
            from app.services.inbox_service import inbox_service
            from app.services.unibox_service import unibox_service
            from app.services.crm_service import crm_service

            await update_progress(
                campaign_id, "inbox_check",
                "Checking Instagram inbox for replies...",
                current=0, total=0,
                detail="Logging in and fetching DM threads",
            )

            result = await inbox_service.process_campaign_inbox(campaign_id, db)

            # Auto-process new replies: CRM stage + dynamic scoring + AI suggestions
            if result.get("new_replies", 0) > 0 and result.get("replied_lead_ids"):
                classifications = result.get("classifications", {})
                for lead_id in result["replied_lead_ids"]:
                    try:
                        # CRM: auto-classify stage based on reply
                        # Check the individual lead's classification, not the global counts
                        from app.models.lead import Lead as InboxLead
                        lead_row = await db.execute(
                            select(InboxLead.reply_classification).where(InboxLead.id == lead_id)
                        )
                        lead_classification = lead_row.scalar_one_or_none()
                        event = "reply_positive" if lead_classification == "positive" else "reply_received"
                        await crm_service.auto_classify_stage(lead_id, db, event=event)
                    except Exception as e:
                        logger.warning(f"CRM auto-classify failed for lead {lead_id}: {e}")

                    try:
                        # CRM: dynamic scoring based on reply content
                        await crm_service.update_conversation_score(lead_id, db)
                    except Exception as e:
                        logger.warning(f"CRM dynamic scoring failed for lead {lead_id}: {e}")

                    try:
                        # Unibox: pre-generate AI reply suggestions
                        await unibox_service.auto_suggest_on_new_reply(lead_id, db)
                        logger.info(f"Auto-processed reply for lead {lead_id}")
                    except Exception as e:
                        logger.warning(f"Auto-suggest failed for lead {lead_id}: {e}")

            if result["errors"]:
                detail = "; ".join(result["errors"][:3])
            else:
                detail = "No errors"

            await update_progress(
                campaign_id, "inbox_check",
                f"Inbox check complete: {result['new_replies']} new replies",
                current=result["new_replies"], total=result["new_replies"],
                detail=detail,
            )

            logger.info(
                f"Inbox check done for campaign {campaign_id}: "
                f"{result['new_replies']} new replies, "
                f"classifications={result['classifications']}"
            )

            return result

    try:
        return _run_async(_check())
    except Exception as exc:
        logger.exception(f"Inbox check failed for campaign {campaign_id}: {exc}")
        raise

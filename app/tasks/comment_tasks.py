import logging

from app.tasks.celery_app import celery_app
from app.tasks.base import _run_async, update_progress, sync_update_progress, RETRY_KWARGS
from app.database import create_worker_session

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="fetch_posts_and_generate_comments", **RETRY_KWARGS)
def fetch_posts_and_generate_comments_task(self, lead_ids: list[str], campaign_id: str = None) -> list[str]:
    """Fetch posts for leads missing them, then generate comments.

    Can be called standalone with campaign_id, or chained in the pipeline
    where campaign_id is derived from the first lead.
    Returns lead_ids for pipeline chaining.
    """
    logger.info(f"Fetching posts for up to {len(lead_ids)} leads, then generating comments")

    async def _run():
        async with create_worker_session()() as db:
            from app.services.apify_service import apify_service
            from sqlalchemy import select
            from app.models.lead import Lead

            # Get campaign_id from leads if not provided
            nonlocal campaign_id
            if not campaign_id and lead_ids:
                result = await db.execute(
                    select(Lead.campaign_id).where(Lead.id == lead_ids[0])
                )
                cid = result.scalar_one_or_none()
                campaign_id = str(cid) if cid else None

            if not campaign_id:
                logger.warning("No campaign_id found, skipping comment generation")
                return lead_ids

            def _fetch_progress(cur, tot, uname):
                sync_update_progress(campaign_id, "fetching_posts",
                                     f"Obteniendo posts {cur}/{tot}: @{uname}",
                                     current=cur, total=tot)

            updated = await apify_service.fetch_posts_for_leads(
                lead_ids, db, progress_callback=_fetch_progress
            )
            await db.commit()
            logger.info(f"Posts fetched for {updated} leads")

            # Now get leads that have posts (either already had or just fetched)
            from sqlalchemy import select
            from app.models.lead import Lead
            result = await db.execute(
                select(Lead.id).where(
                    Lead.id.in_(lead_ids),
                    Lead.ig_posts.isnot(None),
                    Lead.comment_message.is_(None),
                )
            )
            eligible_ids = [str(r) for r in result.scalars().all()]

            if not eligible_ids:
                await update_progress(campaign_id, "comments_ready",
                                      "No se encontraron posts para generar comentarios",
                                      current=0, total=0)
                return lead_ids

            # Generate comments
            from app.services.comment_copywriting_service import comment_copywriting_service

            def _gen_progress(cur, tot, uname):
                sync_update_progress(campaign_id, "generating_comments",
                                     f"Comentario {cur}/{tot}: @{uname}",
                                     current=cur, total=tot)

            comment_ids = await comment_copywriting_service.write_comments_batch(
                eligible_ids, db, progress_callback=_gen_progress
            )
            await db.commit()

            await update_progress(campaign_id, "comments_ready",
                                  f"Comentarios generados: {len(comment_ids)}",
                                  current=len(comment_ids), total=len(comment_ids))

            logger.info(f"Comment generation complete: {len(comment_ids)} comments, {updated} posts fetched")
            return lead_ids

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.exception(f"Fetch posts + generate comments failed: {exc}")
        raise


@celery_app.task(bind=True, name="generate_comments", **RETRY_KWARGS)
def generate_comments_task(self, lead_ids: list[str]) -> list[str]:
    """Generate A/B comments for leads with posts. Returns lead_ids for chaining."""
    logger.info(f"Starting comment generation for {len(lead_ids)} candidates")

    async def _generate():
        async with create_worker_session()() as db:
            from app.services.comment_copywriting_service import comment_copywriting_service

            # Get campaign_id for progress updates
            from sqlalchemy import select
            from app.models.lead import Lead
            campaign_id = None
            if lead_ids:
                result = await db.execute(
                    select(Lead.campaign_id).where(Lead.id == lead_ids[0])
                )
                campaign_id = result.scalar_one_or_none()

            cid = str(campaign_id) if campaign_id else None

            def _progress(cur, tot, uname):
                if cid:
                    sync_update_progress(cid, "generating_comments",
                                         f"Comentario {cur}/{tot}: @{uname}",
                                         current=cur, total=tot)

            comment_ids = await comment_copywriting_service.write_comments_batch(
                lead_ids, db, progress_callback=_progress
            )
            await db.commit()

            if cid:
                await update_progress(cid, "comments_ready",
                                      f"Comentarios generados: {len(comment_ids)}",
                                      current=len(comment_ids), total=len(comment_ids))

            logger.info(f"Comment generation complete: {len(comment_ids)} comments ready")
            return lead_ids

    try:
        return _run_async(_generate())
    except Exception as exc:
        logger.exception(f"Comment generation failed: {exc}")
        raise


@celery_app.task(bind=True, name="send_comments", **RETRY_KWARGS)
def send_comments_task(self, campaign_id: str, lead_ids: list[str] | None = None) -> dict:
    """Send comments for a campaign. If lead_ids provided, send only those (single mode)."""
    mode = "single" if lead_ids else "bulk"
    logger.info(f"Starting comment sending ({mode}) for campaign {campaign_id}")

    async def _send():
        async with create_worker_session()() as db:
            from app.services.browser_manager import get_sender_service

            sender = get_sender_service()
            from app.config import settings
            use_pw = settings.USE_PLAYWRIGHT

            if use_pw:
                logged_in = await sender.login()
            else:
                logged_in = sender.login()

            if not logged_in:
                return {"sent_count": 0, "failed_count": 0, "skipped_count": 0,
                        "paused": True, "reason": "Instagram login failed"}

            def _progress(cur, tot, uname, success):
                status_text = "enviado" if success else "fallido"
                sync_update_progress(campaign_id, "sending_comments",
                                     f"Comentario {cur}/{tot}: @{uname} ({status_text})",
                                     current=cur, total=tot)

            result = await sender.send_campaign_comments(
                campaign_id, db,
                lead_ids=lead_ids,
                progress_callback=_progress,
            )

            sender.save_sessions()
            return result

    try:
        return _run_async(_send())
    except Exception as exc:
        logger.exception(f"Comment sending failed: {exc}")
        raise

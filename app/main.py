import asyncio
import json
import logging
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router, auth_router
from app.logging_config import request_id_var, setup_logging

# Configure logging before anything else
setup_logging()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="IG DM Engine",
    description="AI-powered Instagram DM lead generation and personalization platform",
    version="0.2.0",
)


# ---------------------------------------------------------------------------
# WebSocket Log Streaming
# ---------------------------------------------------------------------------
class LogBuffer:
    """In-memory ring buffer for log entries, broadcast to WebSocket clients."""

    def __init__(self, maxlen: int = 2000):
        self._buffer: deque[dict] = deque(maxlen=maxlen)
        self._clients: set[WebSocket] = set()

    def append(self, entry: dict):
        self._buffer.append(entry)
        # Fire-and-forget broadcast
        dead = set()
        for ws in self._clients:
            try:
                asyncio.get_event_loop().create_task(ws.send_json(entry))
            except Exception:
                dead.add(ws)
        self._clients -= dead

    def recent(self, n: int = 200) -> list[dict]:
        return list(self._buffer)[-n:]

    def add_client(self, ws: WebSocket):
        self._clients.add(ws)

    def remove_client(self, ws: WebSocket):
        self._clients.discard(ws)


log_buffer = LogBuffer()


class WebSocketLogHandler(logging.Handler):
    """Logging handler that sends log records to the WebSocket buffer."""

    def emit(self, record: logging.LogRecord):
        entry = {
            "timestamp": self.format_time(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get("-"),
        }
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = logging.Formatter().formatException(record.exc_info)
        if hasattr(record, "campaign_id"):
            entry["campaign_id"] = record.campaign_id
        if hasattr(record, "lead_username"):
            entry["lead_username"] = record.lead_username
        log_buffer.append(entry)

    @staticmethod
    def format_time(record: logging.LogRecord) -> str:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


# Attach WebSocket log handler to root logger
_ws_handler = WebSocketLogHandler()
_ws_handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(_ws_handler)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class RequestTracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = request_id_var.set(req_id)

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "%s %s %d (%.0fms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            response.headers["X-Request-ID"] = req_id
            return response
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception("%s %s failed (%.0fms)", request.method, request.url.path, duration_ms)
            raise
        finally:
            request_id_var.reset(token)


app.add_middleware(RequestTracingMiddleware)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(auth_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.2.0"}


# ---------------------------------------------------------------------------
# System settings endpoint (bot permissions / config)
# ---------------------------------------------------------------------------
@app.get("/api/v1/system/settings")
async def get_system_settings():
    """Return current bot settings (non-sensitive)."""
    from app.config import settings
    return {
        "scoring": {
            "default_score_threshold": settings.DEFAULT_SCORE_THRESHOLD,
            "research_score_threshold": settings.RESEARCH_SCORE_THRESHOLD,
            "dm_score_threshold": settings.DM_SCORE_THRESHOLD,
        },
        "sending": {
            "daily_dm_limit": settings.DAILY_DM_LIMIT,
            "hourly_dm_limit": settings.HOURLY_DM_LIMIT,
            "dm_delay_min": settings.DM_DELAY_MIN,
            "dm_delay_max": settings.DM_DELAY_MAX,
            "use_playwright": settings.USE_PLAYWRIGHT,
        },
        "warmup": {
            "warmup_days": settings.IG_WARMUP_DAYS,
            "warmup_start_limit": settings.IG_WARMUP_START_LIMIT,
        },
        "safety": {
            "pre_send_check_public": settings.PRE_SEND_CHECK_PUBLIC,
            "skip_private_accounts": settings.SKIP_PRIVATE_ACCOUNTS,
            "challenge_cooldown_minutes": settings.CHALLENGE_COOLDOWN_MINUTES,
            "block_cooldown_hours": settings.BLOCK_COOLDOWN_HOURS,
            "max_challenges_before_pause": settings.MAX_CHALLENGES_BEFORE_PAUSE,
        },
        "inbox": {
            "inbox_check_interval": settings.INBOX_CHECK_INTERVAL,
            "ab_test_enabled": settings.AB_TEST_ENABLED,
            "ab_test_split": settings.AB_TEST_SPLIT,
            "followup_check_interval": settings.FOLLOWUP_CHECK_INTERVAL,
            "max_follow_up_steps": settings.MAX_FOLLOW_UP_STEPS,
        },
        "comments": {
            "comment_enabled": settings.COMMENT_ENABLED,
            "comment_score_threshold": settings.COMMENT_SCORE_THRESHOLD,
            "daily_comment_limit": settings.DAILY_COMMENT_LIMIT,
            "hourly_comment_limit": settings.HOURLY_COMMENT_LIMIT,
            "comment_delay_min": settings.COMMENT_DELAY_MIN,
            "comment_delay_max": settings.COMMENT_DELAY_MAX,
        },
    }


# ---------------------------------------------------------------------------
# Comment endpoints
# ---------------------------------------------------------------------------
@app.post("/api/v1/campaigns/{campaign_id}/generate-comments")
async def generate_comments(campaign_id: str):
    """Generate A/B comments for leads in a campaign.

    Auto-fetches posts from Apify if leads don't have them yet.
    """
    from app.database import async_session
    from sqlalchemy import select, func
    from app.models.lead import Lead

    try:
        async with async_session() as db:
            # All leads with high score and no comment yet
            scored_result = await db.execute(
                select(Lead.id, Lead.ig_posts).where(
                    Lead.campaign_id == campaign_id,
                    Lead.score >= settings.COMMENT_SCORE_THRESHOLD,
                    Lead.comment_message.is_(None),
                )
            )
            scored_leads = scored_result.all()

        if not scored_leads:
            # Check if all already have comments
            async with async_session() as db:
                total = (await db.execute(
                    select(func.count()).select_from(Lead).where(
                        Lead.campaign_id == campaign_id,
                        Lead.score >= settings.COMMENT_SCORE_THRESHOLD,
                    )
                )).scalar() or 0
            if total == 0:
                msg = "No hay leads con score >= {} en esta campaña. Ejecuta el pipeline primero.".format(
                    settings.COMMENT_SCORE_THRESHOLD)
            else:
                msg = "Todos los leads elegibles ya tienen comentarios generados."
            return {"status": "no_leads", "message": msg}

        all_ids = [str(row[0]) for row in scored_leads]
        missing_posts = [row[1] is None for row in scored_leads]
        needs_fetch = any(missing_posts)
        missing_count = sum(missing_posts)

        if needs_fetch:
            # Auto-fetch posts first, then generate comments
            from app.tasks.comment_tasks import fetch_posts_and_generate_comments_task
            task = fetch_posts_and_generate_comments_task.delay(all_ids, campaign_id)
            return {
                "status": "started",
                "task_id": task.id,
                "lead_count": len(all_ids),
                "message": f"Obteniendo posts de {missing_count} leads y luego generando comentarios...",
            }
        else:
            # All leads already have posts — generate comments directly
            from app.tasks.comment_tasks import generate_comments_task
            task = generate_comments_task.delay(all_ids)
            return {"status": "started", "task_id": task.id, "lead_count": len(all_ids)}

    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"Error generating comments: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Error interno: {str(e)}"}
        )


@app.post("/api/v1/campaigns/{campaign_id}/send-comments")
async def send_comments(campaign_id: str, lead_id: Optional[str] = Query(None)):
    """Send comments. If lead_id provided, send only that one. Otherwise bulk send."""
    from app.tasks.comment_tasks import send_comments_task

    lead_ids = [lead_id] if lead_id else None
    task = send_comments_task.delay(campaign_id, lead_ids)
    mode = "individual" if lead_id else "masivo"
    return {"status": "started", "task_id": task.id, "mode": mode}


@app.get("/api/v1/system/health")
async def system_health():
    """System health: check DB, Redis, Celery status."""
    from app.config import settings
    health = {"db": "unknown", "redis": "unknown", "celery": "unknown"}

    # Check DB
    try:
        from app.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        health["db"] = "connected"
    except Exception as e:
        health["db"] = f"error: {str(e)[:80]}"

    # Check Redis
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_timeout=3)
        r.ping()
        health["redis"] = "connected"
    except Exception as e:
        health["redis"] = f"error: {str(e)[:80]}"

    # Check Celery
    try:
        from app.tasks.celery_app import celery_app
        insp = celery_app.control.inspect(timeout=3)
        active = insp.active()
        if active is not None:
            workers = list(active.keys())
            health["celery"] = f"connected ({len(workers)} workers)"
        else:
            health["celery"] = "no workers"
    except Exception as e:
        health["celery"] = f"error: {str(e)[:80]}"

    return health


# ---------------------------------------------------------------------------
# Audit log endpoint
# ---------------------------------------------------------------------------
@app.get("/api/v1/system/audit-log")
async def get_audit_log(limit: int = Query(100, le=500), offset: int = Query(0, ge=0)):
    """Return recent audit log entries."""
    from sqlalchemy import select
    from app.database import async_session
    from app.models.user import AuditLog

    async with async_session() as db:
        result = await db.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        )
        entries = result.scalars().all()
        return [
            {
                "id": str(e.id),
                "user_email": e.user_email,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "details": e.details,
                "ip_address": e.ip_address,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]


# ---------------------------------------------------------------------------
# Notifications endpoint
# ---------------------------------------------------------------------------
@app.get("/api/v1/notifications")
async def get_notifications(unread_only: bool = False, limit: int = Query(50, le=200)):
    """Get recent notifications."""
    from sqlalchemy import select
    from app.database import async_session
    from app.models.user import Notification

    async with async_session() as db:
        query = select(Notification).order_by(Notification.created_at.desc()).limit(limit)
        if unread_only:
            query = query.where(Notification.is_read == False)
        result = await db.execute(query)
        notifs = result.scalars().all()
        return [
            {
                "id": str(n.id),
                "title": n.title,
                "message": n.message,
                "level": n.level,
                "is_read": n.is_read,
                "link": n.link,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifs
        ]


@app.post("/api/v1/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str):
    """Mark a notification as read."""
    from sqlalchemy import select
    from app.database import async_session
    from app.models.user import Notification

    async with async_session() as db:
        result = await db.execute(select(Notification).where(Notification.id == notification_id))
        n = result.scalar_one_or_none()
        if n:
            n.is_read = True
            await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# WebSocket endpoint for live logs
# ---------------------------------------------------------------------------
@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket, level: Optional[str] = Query(None)):
    await websocket.accept()
    log_buffer.add_client(websocket)

    # Send recent history
    min_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    history = [e for e in log_buffer.recent(200) if getattr(logging, e.get("level", "INFO"), 0) >= min_level]
    for entry in history[-100:]:
        await websocket.send_json(entry)

    try:
        while True:
            # Keep connection alive, listen for filter changes
            data = await websocket.receive_text()
            # Client can send JSON to update filter level
            try:
                msg = json.loads(data)
                if "level" in msg:
                    min_level = getattr(logging, msg["level"].upper(), logging.INFO)
            except (json.JSONDecodeError, KeyError):
                pass
    except WebSocketDisconnect:
        pass
    finally:
        log_buffer.remove_client(websocket)


# ---------------------------------------------------------------------------
# Static files / SPA
# ---------------------------------------------------------------------------
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return (STATIC_DIR / "login.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")

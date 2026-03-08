import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.logging_config import request_id_var, setup_logging

# Configure logging before anything else
setup_logging()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="IG DM Engine",
    description="AI-powered Instagram DM lead generation and personalization platform",
    version="0.1.0",
)


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
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}


STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")

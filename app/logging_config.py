import json
import logging
import sys
import uuid
from contextvars import ContextVar

from app.config import settings

# Context variable for request tracing
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class JSONFormatter(logging.Formatter):
    """JSON log formatter for production environments."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get("-"),
        }

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "campaign_id"):
            log_entry["campaign_id"] = record.campaign_id
        if hasattr(record, "lead_username"):
            log_entry["lead_username"] = record.lead_username

        return json.dumps(log_entry, default=str)


class DevFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_var.get("-")
        prefix = f"[{req_id[:8]}] " if req_id != "-" else ""
        record.msg = f"{prefix}{record.msg}"
        return super().format(record)


def setup_logging():
    """Configure logging based on environment."""
    root_logger = logging.getLogger()

    # Clear existing handlers
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if settings.APP_ENV == "production":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(DevFormatter(
            fmt="%(asctime)s %(levelname)-8s %(name)-30s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.APP_ENV == "development" else logging.WARNING
    )

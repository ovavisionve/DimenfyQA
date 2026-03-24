import logging
from typing import Optional

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_valid_keys() -> list[str]:
    """Parse the comma-separated API_KEYS setting into a list of non-empty keys."""
    if not settings.API_KEYS:
        return []
    return [k.strip() for k in settings.API_KEYS.split(",") if k.strip()]


async def verify_api_key(api_key: Optional[str] = Security(_api_key_header)) -> Optional[str]:
    """FastAPI dependency that validates the X-API-Key header.

    Behaviour:
    - API_AUTH_ENABLED=False  -> skip validation entirely (local dev)
    - No API_KEYS configured  -> log warning, allow access (graceful degradation)
    - Valid key provided       -> allow access, return the key
    - Invalid / missing key    -> 401 Unauthorized
    """
    if not settings.API_AUTH_ENABLED:
        return None

    valid_keys = _get_valid_keys()

    if not valid_keys:
        logger.warning(
            "API_AUTH_ENABLED is True but no API_KEYS are configured. "
            "Allowing access. Set API_KEYS in .env to enforce authentication."
        )
        return None

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide a valid key in the X-API-Key header.",
        )

    if api_key not in valid_keys:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
        )

    return api_key

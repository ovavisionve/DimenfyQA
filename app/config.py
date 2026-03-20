import re

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ig_dm_engine"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Anthropic (Claude API)
    ANTHROPIC_API_KEY: str = ""

    # Perplexity (optional, fallback if GOOGLE_API_KEY is not set)
    PERPLEXITY_API_KEY: str = ""

    # Google Gemini (preferred for research)
    GOOGLE_API_KEY: str = ""

    # Apify
    APIFY_API_TOKEN: str = ""

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    DEFAULT_SCORE_THRESHOLD: int = 60
    RESEARCH_SCORE_THRESHOLD: int = 60
    DM_SCORE_THRESHOLD: int = 70

    # Phase 2 — Instagram DM Sending
    IG_USERNAME: str = ""
    IG_PASSWORD: str = ""
    PROXY_URL: str = ""
    DAILY_DM_LIMIT: int = 30
    DM_DELAY_MIN: int = 45
    DM_DELAY_MAX: int = 120
    IG_SESSION_DIR: str = "./ig_sessions"

    # Multi-account rotation: comma-separated "user:pass:proxy" entries
    # e.g. "bot1:pass1:http://proxy1,bot2:pass2:http://proxy2"
    IG_ACCOUNTS: str = ""

    # Warm-up: new accounts send fewer DMs, ramping up over days
    IG_WARMUP_DAYS: int = 7
    IG_WARMUP_START_LIMIT: int = 5

    @field_validator("DEFAULT_SCORE_THRESHOLD", "RESEARCH_SCORE_THRESHOLD", "DM_SCORE_THRESHOLD", mode="before")
    @classmethod
    def clean_int_value(cls, v: object) -> object:
        if isinstance(v, str):
            cleaned = re.sub(r"[^\d]", "", v)
            return int(cleaned) if cleaned else v
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

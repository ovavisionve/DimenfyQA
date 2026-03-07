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

    # Perplexity
    PERPLEXITY_API_KEY: str = ""

    # Apify
    APIFY_API_TOKEN: str = ""

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    DEFAULT_SCORE_THRESHOLD: int = 60
    RESEARCH_SCORE_THRESHOLD: int = 60
    DM_SCORE_THRESHOLD: int = 70

    @field_validator("DEFAULT_SCORE_THRESHOLD", "RESEARCH_SCORE_THRESHOLD", "DM_SCORE_THRESHOLD", mode="before")
    @classmethod
    def clean_int_value(cls, v: object) -> object:
        if isinstance(v, str):
            cleaned = re.sub(r"[^\d]", "", v)
            return int(cleaned) if cleaned else v
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

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

    # API Authentication
    API_KEYS: str = ""  # Comma-separated list of valid API keys
    API_AUTH_ENABLED: bool = True

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

    # Security — Rate limiting & cooldowns
    HOURLY_DM_LIMIT: int = 10  # Max DMs per hour per account
    CHALLENGE_COOLDOWN_MINUTES: int = 60  # Cooldown after challenge before retrying
    BLOCK_COOLDOWN_HOURS: int = 24  # Cooldown after block before retrying
    MAX_CHALLENGES_BEFORE_PAUSE: int = 3  # Pause account after N challenges in a day

    # Security — Session encryption key (Fernet, base64-encoded 32-byte key)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    IG_SESSION_ENCRYPTION_KEY: str = ""

    # Security — Pre-send validation
    PRE_SEND_CHECK_PUBLIC: bool = True  # Verify target is public before sending DM
    SKIP_PRIVATE_ACCOUNTS: bool = True  # Filter out private accounts during scraping

    # Playwright + Stealth (browser automation mode)
    USE_PLAYWRIGHT: bool = False  # True = use Playwright, False = use instagrapi
    PW_HEADLESS: bool = True  # Run browser headless (True for servers)
    PW_SLOW_MO: int = 0  # Slow down Playwright actions by N ms (debugging)
    PW_TYPING_MIN_DELAY: int = 50  # Min ms between keystrokes (human-like typing)
    PW_TYPING_MAX_DELAY: int = 150  # Max ms between keystrokes
    PW_SCREENSHOT_ON_ERROR: bool = True  # Save screenshot when errors occur
    PW_BROWSER_DATA_DIR: str = "./pw_sessions"  # Persistent browser profiles

    # Phase 3 — Inbox Monitoring
    INBOX_CHECK_INTERVAL: int = 300  # seconds between inbox checks (default 5 min)

    # Phase 3 — A/B Testing
    AB_TEST_ENABLED: bool = True
    AB_TEST_SPLIT: float = 0.5  # Ratio of leads that get variant A (0.0-1.0)

    # Phase 3 — Follow-up Automation
    FOLLOWUP_CHECK_INTERVAL: int = 3600  # seconds between follow-up checks (default 1 hour)
    MAX_FOLLOW_UP_STEPS: int = 3  # maximum number of follow-up steps per campaign

    # Slack Notifications
    SLACK_WEBHOOK_URL: str = ""  # Slack Incoming Webhook URL
    SLACK_CHANNEL: str = ""  # Override channel (optional, e.g. "#ig-alerts")

    # Phase 5 — Post Commenting
    COMMENT_ENABLED: bool = True
    COMMENT_SCORE_THRESHOLD: int = 70  # Minimum score to generate comments
    DAILY_COMMENT_LIMIT: int = 10  # Max comments per day per account
    HOURLY_COMMENT_LIMIT: int = 3  # Max comments per hour per account
    COMMENT_DELAY_MIN: int = 60  # Min seconds between comments
    COMMENT_DELAY_MAX: int = 180  # Max seconds between comments

    @field_validator("DEFAULT_SCORE_THRESHOLD", "RESEARCH_SCORE_THRESHOLD", "DM_SCORE_THRESHOLD", mode="before")
    @classmethod
    def clean_int_value(cls, v: object) -> object:
        if isinstance(v, str):
            cleaned = re.sub(r"[^\d]", "", v)
            return int(cleaned) if cleaned else v
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

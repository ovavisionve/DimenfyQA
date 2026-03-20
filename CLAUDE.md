# IG DM Engine — CLAUDE.md

## Project Overview

IG DM Engine is a Python-native platform that replaces an n8n + JarveePro workflow for Instagram DM automation. It handles the full pipeline end-to-end: deciding **who** to message, **what** to say, and **sending the DMs directly** — no external sending tool needed.

**Phase 1 (complete):** Generate qualified leads with personalized DMs as CSV/JSON. Pipeline: scrape → score → research → copywrite → export. Fully functional.

**Phase 2 (next):** Direct DM sending via `instagrapi` (unofficial Instagram API). Eliminates JarveePro dependency entirely. Requires: proxy rotation, rate limiting, account warm-up, challenge/2FA handling.

### Pipeline (6 phases)

```
1. COLLECTION → 2. SCORING → 3. RESEARCH → 4. COPYWRITING → 5. SENDING → 6. EXPORT
   (Apify)        (Claude)    (Gemini)      (Claude)        (instagrapi)   (CSV/API)
```

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API | FastAPI | REST endpoints, orchestration |
| Task Queue | Celery + Redis | Async tasks (scraping, scoring, etc.) |
| Database | PostgreSQL (async) | Leads, campaigns, DMs, metrics |
| Cache/Broker | Redis | Celery broker + cache |
| AI Scoring/Copy | Claude API (Anthropic) | Scoring 0-100 + DM generation |
| AI Research | Google Gemini API | Lead research for high-score leads |
| Scraping | Apify API | Followers, comments, IG profiles |
| DM Sending | instagrapi (planned) | Direct Instagram DM delivery |
| Containers | Docker + Docker Compose | Dev and deploy |

## Repository Structure

```
ig-dm-engine/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
├── alembic.ini
├── alembic/versions/
│   ├── 001_create_all_tables.py     # All 5 tables
│   └── 002_source_value_to_text.py  # VARCHAR→TEXT migration
├── app/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Settings (pydantic-settings)
│   ├── database.py                # SQLAlchemy async engine + session
│   ├── logging_config.py          # JSON/Dev logging with request tracing
│   ├── models/                    # SQLAlchemy models
│   │   ├── base.py                # Base, TimestampMixin, UUIDMixin
│   │   ├── client.py, campaign.py, lead.py, message.py, scrape_job.py
│   ├── schemas/                   # Pydantic request/response schemas
│   │   ├── enums.py               # CampaignStatus, LeadStatus, SourceType, LeadCategory
│   │   ├── client.py, campaign.py, lead.py, message.py
│   ├── api/endpoints/             # FastAPI route handlers
│   │   ├── clients.py, campaigns.py, leads.py, messages.py
│   │   ├── scraping.py, export.py
│   ├── services/                  # Business logic
│   │   ├── apify_service.py       # Apify scraping (217 lines)
│   │   ├── scoring_service.py     # Claude batch scoring (216 lines)
│   │   ├── copywriting_service.py # Claude DM batch generation (310 lines)
│   │   ├── research_service.py    # Gemini/Perplexity research (177 lines)
│   │   └── export_service.py      # CSV/JSON/Excel export (160 lines)
│   ├── tasks/                     # Celery tasks + pipeline orchestration
│   │   ├── celery_app.py, base.py, pipeline.py
│   │   ├── scraping_tasks.py, scoring_tasks.py
│   │   ├── research_tasks.py, copywriting_tasks.py
│   ├── utils/                     # Dedup, text cleanup
│   └── static/
│       └── dashboard.html         # Frontend SPA (1,739 lines, vanilla JS)
├── tests/                         # 11 test files, ~850 lines
│   ├── conftest.py
│   ├── test_api.py, test_clients.py, test_enums.py
│   ├── test_scoring.py            # ⚠️ OUTDATED - calls non-existent methods
│   ├── test_copywriting.py        # ⚠️ OUTDATED - calls non-existent methods
│   ├── test_export.py, test_research.py
│   ├── test_tasks_config.py, test_utils.py
└── scripts/
    ├── seed_db.py                 # Test data (1 client, 1 campaign, 3 leads)
    ├── clean_and_seed.py          # Reset DB + seed
    └── create_100_campaign.py     # 100-lead test campaign
```

## Build & Run Commands

```bash
# Start all services (API + DB + Redis + Worker)
docker compose up --build

# Start only infrastructure (DB + Redis)
docker compose up db redis

# Run API locally (without Docker)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run Celery worker locally
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4

# Run database migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description"

# Run tests
pytest

# Run tests with coverage
pytest --cov=app

# Seed database with test data
python scripts/seed_db.py
```

## Environment Variables

Copy `.env.example` to `.env` and fill in real values. Required:
- `DATABASE_URL` — PostgreSQL connection string (asyncpg)
- `REDIS_URL` — Redis connection string
- `ANTHROPIC_API_KEY` — Claude API key for scoring + copywriting
- `APIFY_API_TOKEN` — Apify API token for Instagram scraping

Optional (research phase):
- `GOOGLE_API_KEY` — Google Gemini API key (preferred for research)
- `PERPLEXITY_API_KEY` — Perplexity API key (fallback if no Google key)
- If neither is set, research phase is skipped automatically

Planned (Phase 2 — DM sending):
- `IG_USERNAME` / `IG_PASSWORD` — Instagram account credentials
- `PROXY_URL` — Rotating proxy for Instagram requests
- `DAILY_DM_LIMIT` — Max DMs per day per account (default: 20-40)
- `DM_DELAY_MIN` / `DM_DELAY_MAX` — Random delay between sends (seconds)

## Key Conventions

### Code Style
- **Python 3.11+** with type hints everywhere
- **Async-first**: all DB operations and HTTP calls use async/await
- **Pydantic v2** for all data validation and serialization
- **SQLAlchemy 2.0** async style with mapped_column

### API Patterns
- All endpoints under `/api/v1/`
- UUID primary keys on all tables
- JSON responses with Pydantic model serialization
- Standard HTTP status codes (201 for creation, 404 for not found, etc.)

### Database
- Multi-tenant: every lead and campaign has a `client_id`
- Deduplication via UNIQUE constraint on `(client_id, ig_username)`
- Alembic for all schema changes — never modify DB directly
- Lead model has 6 indexes: campaign, client, status, score, username + unique constraint

### AI Services
- **Scoring**: Claude Sonnet 4.6 (`claude-sonnet-4-6`) — batch mode, 20 leads per API call, returns JSON array with score 0-100, reason, category, bio_clean. Leads with no data (no bio, no followers, no name) are auto-scored 0 without API call.
- **Copywriting**: Claude Sonnet 4.6 (`claude-sonnet-4-6`) — batch mode (5 leads/call) with individual fallback if batch fails. Generates variant A + B in one call.
- **Research**: Google Gemini (`gemini-2.0-flash`) preferred, Perplexity sonar fallback — only for leads with score >= 60. If no API key configured, research is skipped and leads marked as researched.
- DMs only generated for leads with score >= 70

### Task Pipeline
- Celery chains: scrape → score → research → write DMs (→ send DMs in Phase 2)
- Scoring uses batch API calls (20 leads/call, 3 parallel batches) — NOT individual calls
- DM generation uses batch API calls (5 leads/call, 3 parallel batches) — NOT individual calls
- Research uses asyncio.Semaphore(8) for parallel async requests
- `task_acks_late=True` for reliability
- Campaign status updates at each phase transition
- Progress tracked via `campaign.stats["progress"]` dict, polled by frontend

### Known Issues & Lessons Learned
- Celery workers run in forked processes — each task creates its own async event loop via `_run_async()`
- DB sessions in workers use `create_worker_session()` with `NullPool` to avoid event loop conflicts
- MUST `commit()` (not `flush()`) before calling `update_progress()` to avoid deadlocks (row lock held by session 1, update_progress opens session 2 on same row)
- `sync_update_progress()` exists for ThreadPoolExecutor callbacks (creates its own event loop per thread)
- Model names must be exact — wrong model name causes silent failures (errors caught by safe wrappers)
- **Tests outdated**: `test_scoring.py` calls `score_lead()` (singular) but implementation only has `score_leads_batch()`. Same issue in `test_copywriting.py` — calls `generate_dm()` but actual methods are `generate_single_dm()` and `generate_dms_batch()`. Tests need to be rewritten to match batch API.
- **"followers" Apify actor**: Currently maps to profile scraper (free-tier fallback), not actual followers list
- **Research API key check is brittle**: Uses `"XXXXX" not in api_key` — could use length check instead

### Thresholds (configurable via env)
- `DEFAULT_SCORE_THRESHOLD=60` — minimum score to keep a lead
- `RESEARCH_SCORE_THRESHOLD=60` — minimum score to run research
- `DM_SCORE_THRESHOLD=70` — minimum score to generate a DM

### Testing
- pytest + pytest-asyncio for async tests
- Mock external APIs (Anthropic, Gemini, Perplexity, Apify) in tests
- Test files mirror source structure: `tests/test_scoring.py`, etc.
- **⚠️ test_scoring.py and test_copywriting.py are BROKEN** — call methods that were refactored to batch. Must be rewritten before adding new tests.

## API Keys & Secrets
- **NEVER** commit API keys or secrets to the repository
- All secrets go in `.env` (gitignored)
- Use `pydantic-settings` to load configuration

## Important Notes
- Multi-tenant from day 1 — all queries must filter by client_id
- Apify rate limits must be respected per client plan
- Profile scraping uses synchronous Apify endpoint (`run-sync-get-dataset-items`)
- The n8n workflow reference is in `Instagram_DM_Engine_-_Step_1.json`
- Frontend dashboard is in `static/` directory, served by FastAPI as static files
- Campaign progress is polled by frontend via `/api/v1/campaigns/{id}` endpoint
- Scripts: `scripts/seed_db.py` (test data), `scripts/clean_and_seed.py` (reset DB), `scripts/create_100_campaign.py` (100-lead test campaign)

## Phase 2 — Direct DM Sending (TODO)

### Architecture Plan
JarveePro is being eliminated. DMs will be sent directly via `instagrapi` (unofficial Instagram Private API wrapper for Python).

### New Components Needed
1. **`app/services/dm_sender_service.py`** — Instagram login, session management, DM sending with rate limiting
2. **`app/tasks/sending_tasks.py`** — Celery task for sending DMs with random delays between sends
3. **Migration** — Add to Lead model: `send_error`, `delivery_status`, `send_attempts`
4. **Config additions** — IG credentials, proxy settings, daily limits, delay ranges
5. **Dashboard updates** — Sending progress view, success/failure rates, account health

### Key Considerations
- `instagrapi` simulates the Instagram mobile app — not officially supported by Meta
- **Account safety**: Need random delays (30-120s between DMs), daily limits (20-40 DMs/day), warm-up period for new accounts
- **Challenge handling**: Instagram may trigger login challenges (SMS, email verification, CAPTCHA)
- **Proxy rotation**: Each IG account should use a consistent residential proxy
- **Account rotation**: Support multiple IG accounts to distribute sending load
- **Session persistence**: Save/restore `instagrapi` sessions to avoid re-login

### Sending Pipeline Flow
```
1. Pick next unsent lead (status=dm_ready, ordered by score DESC)
2. Check daily send limit not exceeded
3. Random delay (configurable min/max)
4. Send DM via instagrapi (variant A by default)
5. Update lead: status=sent, sent_at=now()
6. On failure: increment send_attempts, log error, skip to next
7. On challenge: pause sending, alert via dashboard
```

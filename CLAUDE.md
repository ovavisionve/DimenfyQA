# IG DM Engine — CLAUDE.md

## Project Overview

IG DM Engine is a Python-native platform that replaces an n8n + JarveePro workflow for Instagram DM automation. It handles the full pipeline end-to-end: deciding **who** to message, **what** to say, and **sending the DMs directly** — no external sending tool needed.

**Phase 1 (complete):** Generate qualified leads with personalized DMs as CSV/JSON. Pipeline: scrape → score → research → copywrite → export. Fully functional.

**Phase 2 (complete):** Direct DM sending via `instagrapi` (unofficial Instagram API). Eliminates JarveePro dependency entirely. Includes: proxy rotation, rate limiting (daily + hourly), account warm-up, challenge/block cooldowns, session encryption, anti-detection (device fingerprints, user-agents), multi-account rotation, A/B testing, pre-send public account validation.

**Phase 3 (complete):** Inbox monitoring, reply classification, follow-up automation. Services fully implemented: inbox_service.py, followup_service.py, webhook_service.py, ab_testing_service.py, analytics_service.py.

**Phase 4 (complete):** Full SaaS platform. User auth (register/login/JWT), role-based access (admin/manager/viewer), sidebar navigation, client management with custom prompts, bot permission levels panel, real-time WebSocket log viewer, system health dashboard, notification center, audit log.

**Phase 5 (complete):** Operational automation. Celery Beat for periodic inbox monitoring (every 5 min) and follow-up processing (every hour). Slack notifications for campaign events, reply alerts, and account health. GitHub Actions CI/CD pipeline for automated testing on push/PR.

### Pipeline (6 phases)

```
1. COLLECTION → 2. SCORING → 3. RESEARCH → 4. COPYWRITING → 5. SENDING → 6. EXPORT
   (Apify)        (Claude)    (Gemini)      (Claude)        (instagrapi)   (CSV/API)
```

### Public Account Filter (3 layers)

Only public Instagram accounts are processed — private accounts cannot receive DMs:

1. **Scraping** — `save_leads()` skips profiles with `isPrivate=true` (never stored)
2. **Scoring** — Auto-score 0 for any private account before calling Claude API + explicit prompt rule
3. **Pre-send** — `get_next_leads_to_send()` filters `ig_is_private != True` + real-time instagrapi check before each DM

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API | FastAPI | REST endpoints, orchestration |
| Task Queue | Celery + Redis | Async tasks (scraping, scoring, etc.) |
| Task Scheduler | Celery Beat | Periodic inbox checks + follow-ups |
| Database | PostgreSQL (async) | Leads, campaigns, DMs, metrics |
| Cache/Broker | Redis | Celery broker + cache |
| AI Scoring/Copy | Claude API (Anthropic) | Scoring 0-100 + DM generation |
| AI Research | Google Gemini API | Lead research for high-score leads |
| Scraping | Apify API | Followers, comments, IG profiles |
| DM Sending | instagrapi | Direct Instagram DM delivery |
| Session Security | cryptography (Fernet) | Encrypt IG sessions at rest |
| Notifications | Slack Incoming Webhooks | Real-time alerts to Slack |
| CI/CD | GitHub Actions | Automated tests on push/PR |
| Containers | Docker + Docker Compose | Dev and deploy |

## Repository Structure

```
ig-dm-engine/
├── docker-compose.yml              # 5 services: api, worker, beat, db, redis
├── Dockerfile
├── .env.example
├── requirements.txt
├── alembic.ini
├── .github/workflows/ci.yml        # GitHub Actions CI pipeline
├── alembic/versions/
│   ├── 001_create_all_tables.py          # All 5 tables
│   ├── 002_source_value_to_text.py       # VARCHAR→TEXT migration
│   ├── 003_add_phase2_sending_fields.py  # send_attempts, send_error, delivery_status, dm_variant_used
│   ├── 004_add_inbox_tracking_fields.py  # replied_at, reply_text, reply_classification, conversation_status
│   ├── 005_add_follow_up_system.py       # follow_up_rules table, follow_up fields on leads
│   ├── 006_add_webhooks_table.py         # webhooks table
│   ├── 007_add_lead_posts_and_analysis.py # ig_posts, ig_post_analysis (JSONB)
│   └── 008_add_users_audit_notifications.py # users, audit_logs, notifications tables
├── app/
│   ├── main.py                    # FastAPI entry point + inline notification endpoints
│   ├── config.py                  # Settings (pydantic-settings) — includes Slack config
│   ├── database.py                # SQLAlchemy async engine + session
│   ├── logging_config.py          # JSON/Dev logging with request tracing
│   ├── models/                    # SQLAlchemy models
│   │   ├── base.py                # Base, TimestampMixin, UUIDMixin
│   │   ├── client.py, campaign.py, lead.py, message.py, scrape_job.py
│   │   ├── follow_up_rule.py, webhook.py
│   │   └── user.py                # User, AuditLog, Notification models
│   ├── schemas/                   # Pydantic request/response schemas
│   │   ├── enums.py               # CampaignStatus, LeadStatus, SourceType, LeadCategory, ConversationStatus, ReplyClassification
│   │   ├── client.py, campaign.py, lead.py, message.py
│   ├── api/endpoints/             # FastAPI route handlers
│   │   ├── clients.py, campaigns.py, leads.py, messages.py
│   │   ├── scraping.py, export.py
│   ├── services/                  # Business logic
│   │   ├── apify_service.py       # Apify multi-actor scraping (~400 lines)
│   │   ├── scoring_service.py     # Claude batch scoring (~250 lines) — filters private accounts
│   │   ├── copywriting_service.py # Claude DM batch generation (~410 lines)
│   │   ├── research_service.py    # Gemini/Perplexity research (~240 lines)
│   │   ├── dm_sender_service.py   # Instagram DM sending with full security (~530 lines)
│   │   ├── content_analysis_service.py # Multimodal content analysis (~300 lines)
│   │   ├── notification_service.py # In-app + Slack dual-channel notifications
│   │   ├── webhook_service.py     # Webhook event triggers
│   │   └── export_service.py      # CSV/JSON/Excel export (~160 lines)
│   ├── tasks/                     # Celery tasks + pipeline orchestration
│   │   ├── celery_app.py          # Celery config + Beat schedule (inbox 5min, follow-ups 1hr)
│   │   ├── base.py, pipeline.py
│   │   ├── scraping_tasks.py, scoring_tasks.py
│   │   ├── research_tasks.py, copywriting_tasks.py
│   │   ├── sending_tasks.py       # DM sending Celery task + completion notifications
│   │   ├── inbox_tasks.py         # check_all_inboxes_task (Beat) + check_inbox_task
│   │   └── followup_tasks.py      # check_all_follow_ups_task (Beat) + process_follow_ups_task
│   ├── utils/                     # Dedup, text cleanup
│   └── static/
│       └── dashboard.html         # Frontend SPA (~2,760 lines, vanilla JS)
├── tests/                         # 12+ test files
│   ├── conftest.py
│   ├── test_api.py, test_clients.py, test_enums.py
│   ├── test_scoring.py            # ✅ 17 tests (batch scoring, auto-score, edge cases)
│   ├── test_copywriting.py        # ✅ 21 tests (single DM, batch, write_dms_batch)
│   ├── test_dm_sender.py          # ✅ Phase 2 tests (62 passed, 3 skipped)
│   ├── test_export.py, test_research.py
│   ├── test_tasks_config.py, test_utils.py
└── scripts/
    ├── seed_db.py                 # Test data (1 client, 1 campaign, 3 leads)
    ├── clean_and_seed.py          # Reset DB + seed
    └── create_100_campaign.py     # 100-lead test campaign
```

## Build & Run Commands

```bash
# Start all services (API + DB + Redis + Worker + Beat)
docker compose up --build

# Start only infrastructure (DB + Redis)
docker compose up db redis

# Start specific services (e.g., test Beat scheduler)
docker compose up --build beat worker db redis

# Run API locally (without Docker)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run Celery worker locally
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4

# Run Celery Beat locally (periodic tasks)
celery -A app.tasks.celery_app beat --loglevel=info

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

# Generate Fernet encryption key for session security
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Manually trigger periodic tasks (from inside worker container)
docker compose exec worker python -c "from app.tasks.inbox_tasks import check_all_inboxes_task; print(check_all_inboxes_task.delay())"
docker compose exec worker python -c "from app.tasks.followup_tasks import check_all_follow_ups_task; print(check_all_follow_ups_task.delay())"
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

Slack Notifications (optional):
- `SLACK_WEBHOOK_URL` — Slack Incoming Webhook URL (create at https://api.slack.com/apps → Incoming Webhooks)
- `SLACK_CHANNEL` — Override channel (e.g. `#ig-alerts`). Optional — defaults to webhook's configured channel.
- If `SLACK_WEBHOOK_URL` is empty, only in-app notifications are created (no Slack).

Phase 2 — DM sending:
- `IG_USERNAME` / `IG_PASSWORD` — Instagram account credentials (single account mode)
- `IG_ACCOUNTS` — Multi-account rotation: `"user1:pass1:proxy1,user2:pass2:proxy2"`
- `PROXY_URL` — Proxy for single account mode
- `DAILY_DM_LIMIT` — Max DMs per day per account (default: 30)
- `HOURLY_DM_LIMIT` — Max DMs per hour per account (default: 10)
- `DM_DELAY_MIN` / `DM_DELAY_MAX` — Random delay between sends in seconds (default: 45/120)
- `IG_SESSION_DIR` — Directory for session files (default: `./ig_sessions`)
- `IG_WARMUP_DAYS` — Days for warm-up ramp (default: 7)
- `IG_WARMUP_START_LIMIT` — DMs/day for new accounts (default: 5)

Phase 2 — Security:
- `IG_SESSION_ENCRYPTION_KEY` — Fernet key for encrypting session files at rest (optional but recommended)
- `CHALLENGE_COOLDOWN_MINUTES` — Cooldown after Instagram challenge (default: 60)
- `BLOCK_COOLDOWN_HOURS` — Cooldown after Instagram block (default: 24)
- `MAX_CHALLENGES_BEFORE_PAUSE` — Auto-pause account after N challenges in a day (default: 3)
- `PRE_SEND_CHECK_PUBLIC` — Verify target account is public before sending (default: true)
- `SKIP_PRIVATE_ACCOUNTS` — Filter out private accounts during scraping (default: true)

Phase 3 — Inbox & Follow-up:
- `INBOX_CHECK_INTERVAL` — Seconds between inbox checks (default: 300, used by Celery Beat)
- `AB_TEST_ENABLED` — Enable A/B testing for DM variants (default: true)
- `AB_TEST_SPLIT` — Ratio of leads getting variant A (default: 0.5)
- `FOLLOWUP_CHECK_INTERVAL` — Seconds between follow-up checks (default: 3600, used by Celery Beat)
- `MAX_FOLLOW_UP_STEPS` — Maximum follow-up steps per campaign (default: 3)

## Docker Compose Services

| Service | Command | Purpose |
|---------|---------|---------|
| `api` | `uvicorn app.main:app` | FastAPI server (port 1000) |
| `worker` | `celery worker` | Executes async tasks (scraping, scoring, sending, etc.) |
| `beat` | `celery beat` | Schedules periodic tasks (inbox checks, follow-ups) |
| `db` | PostgreSQL 16 | Primary database |
| `redis` | Redis 7 | Celery broker + cache |

### Celery Beat Schedule

| Task | Interval | What it does |
|------|----------|-------------|
| `check_all_inboxes` | Every 5 min (`INBOX_CHECK_INTERVAL`) | Finds campaigns with sent DMs, dispatches `check_inbox_task` per campaign |
| `check_all_follow_ups` | Every 1 hour (`FOLLOWUP_CHECK_INTERVAL`) | Finds campaigns with active follow-up rules, dispatches `process_follow_ups_task` per campaign |

## Notification System

Dual-channel: **in-app** (stored in DB, shown in dashboard dropdown) + **Slack** (via Incoming Webhook).

### Events that trigger notifications

| Event | Level | Slack | When |
|-------|-------|-------|------|
| Campaign completed | success | Yes | All DMs sent successfully |
| Campaign paused | warning | Yes | Rate limit, block, or all accounts in cooldown |
| Reply received | success/info | Yes | Lead responds to DM (positive = success, others = info) |
| Account blocked | error | Yes | Instagram blocks an account |

### How it works
- `notification_service.py` creates a `Notification` DB record + sends Slack POST
- Dashboard polls `GET /api/v1/notifications` every 60 seconds
- Slack messages include emoji by level and link to dashboard
- If `SLACK_WEBHOOK_URL` is empty, only in-app notifications are created

## CI/CD — GitHub Actions

**File:** `.github/workflows/ci.yml`

Runs on every push to `main`/`develop` and on PRs:
1. Spins up PostgreSQL 16 + Redis 7 as service containers
2. Installs Python 3.11 + dependencies
3. Runs Alembic migrations
4. Runs pytest (84+ tests)

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
- Lead model has 6+ indexes: campaign, client, status, score, username, delivery_status, send_attempts, conversation_status, next_follow_up_at + unique constraint
- 8 migrations total (001-008)

### AI Services
- **Scoring**: Claude Sonnet 4.6 (`claude-sonnet-4-6`) — batch mode, 20 leads per API call, returns JSON array with score 0-100, reason, category, bio_clean. Private accounts are auto-scored 0 without API call. Leads with no data (no bio, no followers, no name) are also auto-scored 0.
- **Copywriting**: Claude Sonnet 4.6 (`claude-sonnet-4-6`) — batch mode (5 leads/call) with individual fallback if batch fails. Generates variant A + B in one call.
- **Research**: Google Gemini (`gemini-2.0-flash`) preferred, Perplexity sonar fallback — only for leads with score >= 60. If no API key configured, research is skipped and leads marked as researched.
- DMs only generated for leads with score >= 70

### Task Pipeline
- Celery chains: scrape → score → research → write DMs → send DMs
- Celery Beat: inbox monitoring (5 min) + follow-up processing (1 hour)
- Scoring uses batch API calls (20 leads/call, 3 parallel batches) — NOT individual calls
- DM generation uses batch API calls (5 leads/call, 3 parallel batches) — NOT individual calls
- Research uses asyncio.Semaphore(8) for parallel async requests
- DM sending uses sequential sends with random delays (45-120s) between each
- `task_acks_late=True` for reliability
- Campaign status updates at each phase transition
- Progress tracked via `campaign.stats["progress"]` dict, polled by frontend

### DM Sending — Architecture & Security

#### Multi-Account System
- `IGAccount` class: one instance per Instagram account with its own instagrapi client, session, health metrics
- `DMSenderService` orchestrates multiple accounts with round-robin rotation
- Accounts parsed from `IG_ACCOUNTS` env var or fallback to single `IG_USERNAME`/`IG_PASSWORD`
- Each account has persistent session file + health file on disk

#### Anti-Detection Measures
- **Device fingerprinting**: 5 realistic Android device profiles (Samsung, Google Pixel, OnePlus, Xiaomi) assigned consistently per account via username hash
- **User-Agent**: Realistic Instagram mobile app user-agent matching the device profile
- **Request delays**: instagrapi `delay_range = [2, 5]` between internal API calls
- **Pre-send jitter**: Random 1-3s delay before each `direct_send` call
- **Human-like delays**: 45-120s between DMs (configurable), with 1.5x-2x longer delays after failures, plus random ±5-10s jitter. Minimum 15s enforced.

#### Rate Limiting (3 layers)
1. **Daily limit**: Sum of all accounts' warm-up limits (default 30/day per mature account)
2. **Hourly limit**: 10 DMs/hour per account (configurable via `HOURLY_DM_LIMIT`)
3. **Warm-up ramp**: New accounts start at 5 DMs/day, linearly ramping to full limit over 7 days

#### Cooldown System
- **Challenge cooldown**: 60 minutes after Instagram challenge (configurable)
- **Block cooldown**: 24 hours after Instagram block (configurable)
- **Daily challenge limit**: Auto-pause account after 3 challenges in one day (configurable)
- Account rotation automatically skips accounts in cooldown
- Campaign pauses if ALL accounts are in cooldown/blocked

#### Session Security
- **Encryption at rest**: Session files and health files encrypted with Fernet (AES-128-CBC) when `IG_SESSION_ENCRYPTION_KEY` is configured
- **Transparent encryption**: Files are encrypted on save, decrypted on load. Handles both encrypted and plaintext files gracefully.
- **Temp file cleanup**: Decrypted session data written to temp file for instagrapi load, then deleted

#### Pre-Send Validation
- **Public account check**: Before each DM, verifies target account is public via `user_info_by_username()`. Private accounts are skipped and marked with `delivery_status = "skipped_private"` + updates `ig_is_private = True` for future filtering.
- **Proxy validation**: Checks proxy connectivity before login via httpbin.org ping
- **User not found**: Handles deleted/renamed accounts gracefully (`delivery_status = "user_not_found"`)

#### Sending Pipeline Flow
```
1. Check daily limit not exceeded
2. Query leads: status in (dm_ready, retry), send_attempts < 3, ig_is_private != True, ordered by score DESC
3. For each lead:
   a. Pre-send check: verify target is public (real-time instagrapi check)
   b. Select DM variant: A/B test random assignment, or switch variant on retry
   c. Send DM via round-robin account rotation
   d. On success: status=sent, trigger webhook + notification
   e. On rate limit: pause campaign, return
   f. On challenge/block: record cooldown, rotate to next account or pause if none available
   g. On user_not_found: status=failed immediately
   h. On other failure: increment send_attempts, retry up to 3 times
   i. Human-like delay before next send (longer after failures)
4. Save all account sessions (encrypted) after batch
5. Send completion notification (in-app + Slack)
```

#### A/B Testing
- Each lead gets randomly assigned variant A or B based on `AB_TEST_SPLIT` ratio
- On retry, automatically switches to the other variant
- Variant used is tracked in `lead.dm_variant_used`

### Scraping — Multi-Actor Comment Strategy
- 3 comment scrapers run in parallel to maximize free-tier results:
  1. `apify~instagram-comment-scraper` (Official) — best free tier (~2,100/month)
  2. `louisdeconinck~instagram-comments-scraper` — cheapest at scale ($0.50/1K)
  3. `datadoping~instagram-comments-and-replies-scraper` — richest data (verification status, reply threads)
- Results deduplicated by username across all actors
- Reply comments also extracted for additional leads
- Private accounts filtered out during `save_leads()`

### Known Issues & Lessons Learned
- Celery workers run in forked processes — each task creates its own async event loop via `_run_async()`
- DB sessions in workers use `create_worker_session()` with `NullPool` to avoid event loop conflicts
- MUST `commit()` (not `flush()`) before calling `update_progress()` to avoid deadlocks (row lock held by session 1, update_progress opens session 2 on same row)
- `sync_update_progress()` exists for ThreadPoolExecutor callbacks (creates its own event loop per thread)
- Model names must be exact — wrong model name causes silent failures (errors caught by safe wrappers)
- **Tests fixed**: `test_scoring.py` and `test_copywriting.py` have been updated to match batch API methods. All 103 tests pass (3 skipped for encryption in non-Docker env).
- **Pre-existing test failures**: `test_dm_sender.py::test_ig_username_default_empty` fails when `.env` has `IG_USERNAME` set; `test_research.py::test_research_lead_returns_text` has a KeyError. Both are environment-dependent, not code bugs.
- **"followers" Apify actor**: Currently maps to profile scraper (free-tier fallback), not actual followers list
- **Research API key check**: Uses `len(key.strip()) >= 20` validation (previously used brittle `"XXXXX" not in` check)
- **Free-tier comment limits**: Each Apify actor returns ~15 comments on free tier. Multi-actor strategy yields ~45 max. For more, scrape comments from multiple posts or upgrade Apify plan.
- **Docker Compose version warning**: `version: "3.9"` is obsolete but harmless. Can be removed.

### Thresholds (configurable via env)
- `DEFAULT_SCORE_THRESHOLD=60` — minimum score to keep a lead
- `RESEARCH_SCORE_THRESHOLD=60` — minimum score to run research
- `DM_SCORE_THRESHOLD=70` — minimum score to generate a DM

### Testing
- pytest + pytest-asyncio for async tests
- Mock external APIs (Anthropic, Gemini, Perplexity, Apify, instagrapi) in tests
- Test files mirror source structure: `tests/test_scoring.py`, etc.
- `test_dm_sender.py` — 62 passed, 3 skipped (encryption tests require working `cryptography` package)
- `test_scoring.py` — 17 tests covering batch scoring, auto-score for empty/private profiles, progress callbacks, API failure handling
- `test_copywriting.py` — 21 tests covering single DM generation, batch DMs, write_dms_batch with campaign/client mocks, progress callbacks
- GitHub Actions CI runs on push to main/develop and on PRs

## API Keys & Secrets
- **NEVER** commit API keys or secrets to the repository
- All secrets go in `.env` (gitignored)
- Use `pydantic-settings` to load configuration
- Instagram session files should be encrypted with `IG_SESSION_ENCRYPTION_KEY`

## Important Notes
- Multi-tenant from day 1 — all queries must filter by client_id
- Apify rate limits must be respected per client plan
- Profile scraping uses synchronous Apify endpoint (`run-sync-get-dataset-items`)
- The n8n workflow reference is in `Instagram_DM_Engine_-_Step_1.json`
- Frontend dashboard is in `static/` directory, served by FastAPI as static files
- Campaign progress is polled by frontend via `/api/v1/campaigns/{id}` endpoint
- Scripts: `scripts/seed_db.py` (test data), `scripts/clean_and_seed.py` (reset DB), `scripts/create_100_campaign.py` (100-lead test campaign)
- `instagrapi` simulates the Instagram mobile app — not officially supported by Meta. Use at your own risk.
- Always use residential proxies for Instagram accounts to avoid detection

## SaaS Roadmap — Remaining Items

### Done
- [x] Celery Beat for automated inbox monitoring + follow-ups
- [x] Slack notifications (campaign completed/paused, reply received, account blocked)
- [x] GitHub Actions CI/CD pipeline
- [x] In-app notification center with dashboard dropdown

### TODO
- [ ] Next.js dashboard (currently vanilla JS SPA — functional but not production-grade for SaaS)
- [ ] CRM pipeline visual (kanban: scraped → qualified → DM sent → replied → closed)
- [ ] User onboarding flow (guided setup wizard for new clients)
- [ ] API documentation (auto-generated Swagger is available at /docs, but needs customer-facing docs)
- [ ] WhatsApp notifications (complement Slack for mobile-first clients)
- [ ] Stripe billing integration (usage-based pricing per client)

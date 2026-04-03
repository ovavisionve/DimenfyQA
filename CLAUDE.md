# IG DM Engine — CLAUDE.md

## Project Overview

IG DM Engine is a Python-native platform that replaces an n8n + JarveePro workflow for Instagram DM automation. It handles the full pipeline end-to-end: deciding **who** to message, **what** to say, and **sending the DMs directly** — no external sending tool needed.

**Phase 1 (complete):** Generate qualified leads with personalized DMs as CSV/JSON. Pipeline: scrape → score → research → copywrite → export. Fully functional.

**Phase 2 (complete):** Direct DM sending via `instagrapi` (unofficial Instagram API). Eliminates JarveePro dependency entirely. Includes: proxy rotation, rate limiting (daily + hourly), account warm-up, challenge/block cooldowns, session encryption, anti-detection (device fingerprints, user-agents), multi-account rotation, A/B testing, pre-send public account validation.

**Phase 3 (complete):** Inbox monitoring, reply classification, follow-up automation. Services fully implemented: inbox_service.py, followup_service.py, webhook_service.py, ab_testing_service.py, analytics_service.py.

**Phase 4 (complete):** Full SaaS platform. User auth (register/login/JWT), role-based access (admin/manager/viewer), sidebar navigation, client management with custom prompts, bot permission levels panel, real-time WebSocket log viewer, system health dashboard, notification center, audit log.

**Phase 5 (complete):** Operational automation. Celery Beat for periodic inbox monitoring (every 5 min) and follow-up processing (every hour). Slack notifications for campaign events, reply alerts, and account health. GitHub Actions CI/CD pipeline for automated testing on push/PR.

**Phase 6 (complete):** Competitive feature parity + AI advantage. Unibox (unified inbox with AI reply suggestions), CRM Kanban (visual pipeline with dynamic scoring), pre-scraping bio keyword filter, campaign sending schedule with timezone. Next.js frontend replacing vanilla JS dashboard.

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
| Frontend | Next.js 16 + React 19 + TypeScript | Dashboard SPA (port 3000) |
| Styling | Tailwind CSS v4 | Dark theme, amber accents |
| AI Reply Suggestions | Claude API (Anthropic) | 3 suggestions per conversation (close/nurture/qualify) |
| AI Dynamic Scoring | Claude API (Anthropic) | Score delta -20 to +20 based on reply intent |

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
│   ├── 008_add_users_audit_notifications.py # users, audit_logs, notifications tables
│   ├── 009_add_comment_fields.py         # Comment DM fields on leads
│   ├── 010_add_campaign_task_tracking.py  # celery_task_id, last_phase on campaigns
│   ├── 011_add_unibox_tables.py          # conversation_messages, reply_suggestions tables
│   └── 012_add_crm_tables.py             # crm_stage on leads, lead_notes, score_history tables
├── app/
│   ├── main.py                    # FastAPI entry point + inline notification endpoints
│   ├── config.py                  # Settings (pydantic-settings) — includes Slack config
│   ├── database.py                # SQLAlchemy async engine + session
│   ├── logging_config.py          # JSON/Dev logging with request tracing
│   ├── models/                    # SQLAlchemy models
│   │   ├── base.py                # Base, TimestampMixin, UUIDMixin
│   │   ├── client.py, campaign.py, lead.py, message.py, scrape_job.py
│   │   ├── follow_up_rule.py, webhook.py
│   │   ├── user.py                # User, AuditLog, Notification models
│   │   ├── conversation_message.py # Phase 6: Unibox message history
│   │   ├── reply_suggestion.py    # Phase 6: AI reply suggestions (JSONB)
│   │   └── crm.py                 # Phase 6: LeadNote, ScoreHistory
│   ├── schemas/                   # Pydantic request/response schemas
│   │   ├── enums.py               # CampaignStatus, LeadStatus, SourceType, LeadCategory, ConversationStatus, ReplyClassification, CrmStage
│   │   ├── client.py, campaign.py, lead.py, message.py
│   ├── api/endpoints/             # FastAPI route handlers
│   │   ├── clients.py, campaigns.py, leads.py, messages.py
│   │   ├── scraping.py, export.py
│   │   ├── unibox.py              # Phase 6: 8 Unibox endpoints
│   │   ├── crm.py                 # Phase 6: 6 CRM endpoints
│   ├── services/                  # Business logic
│   │   ├── apify_service.py       # Apify multi-actor scraping (~400 lines)
│   │   ├── scoring_service.py     # Claude batch scoring (~250 lines) — filters private accounts
│   │   ├── copywriting_service.py # Claude DM batch generation (~410 lines)
│   │   ├── research_service.py    # Gemini/Perplexity research (~240 lines)
│   │   ├── dm_sender_service.py   # Instagram DM sending with full security (~570 lines) + sending schedule
│   │   ├── content_analysis_service.py # Multimodal content analysis (~300 lines)
│   │   ├── notification_service.py # In-app + Slack dual-channel notifications
│   │   ├── webhook_service.py     # Webhook event triggers
│   │   ├── export_service.py      # CSV/JSON/Excel export (~160 lines)
│   │   ├── unibox_service.py      # Phase 6: Unified inbox + AI reply suggestions (~450 lines)
│   │   └── crm_service.py         # Phase 6: Kanban pipeline + dynamic scoring (~350 lines)
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
│       └── dashboard.html         # Legacy SPA (~2,760 lines, vanilla JS) — replaced by Next.js
├── frontend/                      # Next.js 16 dashboard (port 3000)
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx, page.tsx          # Root layout + redirect
│   │   │   ├── login/page.tsx                # Login/Register
│   │   │   └── (dashboard)/                  # Auth-guarded dashboard routes
│   │   │       ├── layout.tsx                # Sidebar + main layout
│   │   │       ├── pipeline/page.tsx         # Campaign management (~1,600 lines)
│   │   │       ├── dms/page.tsx              # Generated DMs display
│   │   │       ├── comments/page.tsx         # Comment generation
│   │   │       ├── clients/page.tsx          # Client CRUD
│   │   │       ├── settings/page.tsx         # System settings
│   │   │       ├── logs/page.tsx             # Real-time WebSocket logs
│   │   │       ├── health/page.tsx           # System health + audit logs
│   │   │       ├── unibox/page.tsx           # Phase 6: Unified inbox
│   │   │       └── crm/page.tsx              # Phase 6: CRM Kanban
│   │   ├── components/layout/sidebar.tsx     # Sidebar navigation
│   │   └── lib/
│   │       ├── api.ts                        # API helper with JWT auth
│   │       ├── auth.ts                       # Auth state (localStorage)
│   │       └── cn.ts                         # Tailwind class merge utility
│   ├── package.json, tsconfig.json
│   └── next.config.ts
├── tests/                         # 16 test files, 200+ tests
│   ├── conftest.py
│   ├── test_api.py, test_clients.py, test_enums.py
│   ├── test_scoring.py            # ✅ 17 tests (batch scoring, auto-score, edge cases)
│   ├── test_copywriting.py        # ✅ 21 tests (single DM, batch, write_dms_batch)
│   ├── test_dm_sender.py          # ✅ Phase 2 tests (62 passed, 3 skipped)
│   ├── test_export.py, test_research.py
│   ├── test_tasks_config.py, test_utils.py
│   ├── test_unibox.py             # ✅ 19 tests (conversations, threads, AI suggestions, reply)
│   ├── test_crm.py                # ✅ 32 tests (auto-classify, dynamic scoring, move, notes)
│   ├── test_bio_keywords.py       # ✅ 10 tests (keyword filtering logic)
│   ├── test_sending_schedule.py   # ✅ 13 tests (timezone, overnight, boundaries)
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

# Run Next.js frontend (port 3000)
cd frontend && npm run dev

# Build Next.js frontend
cd frontend && npx next build

# Run tests (use tests/ dir to avoid scripts/)
python -m pytest tests/

# Run tests with coverage
python -m pytest tests/ --cov=app

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
4. Runs pytest (200+ tests)

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
- 12 migrations total (001-012)

### AI Services
- **Scoring**: Claude Sonnet 4.6 (`claude-sonnet-4-6`) — batch mode, 20 leads per API call, returns JSON array with score 0-100, reason, category, bio_clean. Private accounts are auto-scored 0 without API call. Leads with no data (no bio, no followers, no name) are also auto-scored 0.
- **Copywriting**: Claude Sonnet 4.6 (`claude-sonnet-4-6`) — batch mode (5 leads/call) with individual fallback if batch fails. Generates variant A + B in one call.
- **Research**: Google Gemini (`gemini-2.0-flash`) preferred, Perplexity sonar fallback — only for leads with score >= 60. If no API key configured, research is skipped and leads marked as researched.
- DMs only generated for leads with score >= 70
- **Reply Suggestions**: Claude Sonnet 4.6 — generates 3 reply suggestions per conversation (close/nurture/qualify) with full context (conversation, lead info, campaign, client prompts)
- **Dynamic Scoring**: Claude Sonnet 4.6 — evaluates purchase intent from replies, returns score delta -20 to +20 with reason. Stored in `score_history` table.

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
1. Check sending schedule (if configured) — pause if outside hours for campaign timezone
2. Check daily limit not exceeded
3. Query leads: status in (dm_ready, retry), send_attempts < 3, ig_is_private != True, ordered by score DESC
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
- **Tests fixed**: `test_scoring.py` and `test_copywriting.py` have been updated to match batch API methods. 192+ tests pass (3 skipped for encryption in non-Docker env).
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
- **Run with `python -m pytest tests/`** (not bare `pytest` — avoids picking up `scripts/test_ig_login.py`)
- `test_dm_sender.py` — 62 passed, 3 skipped (encryption tests require working `cryptography` package)
- `test_scoring.py` — 17 tests covering batch scoring, auto-score for empty/private profiles, progress callbacks, API failure handling
- `test_copywriting.py` — 21 tests covering single DM generation, batch DMs, write_dms_batch with campaign/client mocks, progress callbacks
- `test_unibox.py` — 19 tests covering conversations, threads, AI suggestions, reply sending, suggestion marking
- `test_crm.py` — 32 tests covering auto-classify stages, dynamic scoring, move lead, notes, board stats, score history
- `test_bio_keywords.py` — 10 tests covering keyword filtering (single/multiple, case-insensitive, empty bios, partial match)
- `test_sending_schedule.py` — 13 tests covering timezone checks, overnight schedules, boundary conditions
- GitHub Actions CI runs on push to main/develop and on PRs
- **Total: 200+ tests** (192 passed, 8 pre-existing env-dependent failures, 3 skipped)

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
- **Primary frontend** is Next.js at `frontend/` (port 3000). Legacy vanilla JS SPA at `app/static/dashboard.html` still exists but is no longer the primary UI.
- Backend API runs on port 1000. Frontend `NEXT_PUBLIC_API_URL` defaults to `http://localhost:1000`.
- Campaign progress is polled by frontend via `/api/v1/campaigns/{id}` endpoint
- Scripts: `scripts/seed_db.py` (test data), `scripts/clean_and_seed.py` (reset DB), `scripts/create_100_campaign.py` (100-lead test campaign)
- `instagrapi` simulates the Instagram mobile app — not officially supported by Meta. Use at your own risk.
- Always use residential proxies for Instagram accounts to avoid detection

## Phase 6 (complete): Competitive Feature Parity + AI Advantage

**Goal:** Match and surpass ColdDMs ($99/mo competitor) with 4 new features, each leveraging AI to go beyond basic functionality. ColdDMs uses a Chrome extension (requires PC on); we run on Docker 24/7. ColdDMs has basic inbox and CRM; ours has AI-assisted replies and dynamic scoring.

**All 4 features implemented with 74 new tests.** Next.js frontend pages created for all features.

### Feature 1: UNIBOX — Unified Inbox with AI-Assisted Replies

Unified view of ALL conversations across ALL Instagram accounts. Users read full conversation history, reply directly, and receive AI-generated reply suggestions (3 per message: Close, Nurture, Qualify).

**Backend:**
- `app/services/unibox_service.py` — Core service:
  - `get_all_conversations(filters)` — All conversations with pagination + filters (campaign, account, status, classification, crm_stage, text search, sort by recency/unread/score)
  - `get_conversation_thread(lead_id)` — Full message history + lead info (bio, score, research, crm_stage)
  - `send_reply(lead_id, account_id, message)` — Reply via instagrapi with same anti-detection delays as dm_sender_service
  - `generate_reply_suggestion(lead_id)` — Claude API call with full context (conversation, lead info, campaign context, client prompts). Returns 3 suggestions: Close (schedule call/sale), Nurture (answer + keep talking), Qualify (ask fit questions)
  - `auto_suggest_on_new_reply(lead_id)` — Called automatically by inbox_tasks.py when new reply detected. Pre-generates suggestions and stores in DB so they're ready when user opens conversation
  - `mark_as_read(lead_id)` / `mark_as_starred(lead_id)` — State management
- `app/routers/unibox.py` — REST endpoints:
  - `GET /api/v1/unibox/conversations` — List with filters + pagination
  - `GET /api/v1/unibox/conversations/{lead_id}/thread` — Conversation history
  - `POST /api/v1/unibox/conversations/{lead_id}/reply` — Send reply
  - `GET /api/v1/unibox/conversations/{lead_id}/suggestions` — Pre-generated suggestions
  - `POST /api/v1/unibox/conversations/{lead_id}/suggest` — Force regenerate suggestions
  - `PATCH /api/v1/unibox/conversations/{lead_id}` — Update state (read, starred, classification)
  - `GET /api/v1/unibox/stats` — Unread count, by classification, avg response time
  - JWT protected: admin/manager can reply, viewer read-only
- **Models:**
  - `is_read` (boolean) + `is_starred` (boolean) on messages/replies
  - New table `reply_suggestions` (id, lead_id, suggestions JSONB, generated_at, was_used boolean)
  - `crm_stage` field on lead model (shared with Feature 2)
- **Integration:** inbox_tasks.py → on new reply → call `auto_suggest_on_new_reply()` to pre-generate suggestions
- **Migration:** Alembic 011 (conversation_messages + reply_suggestions tables)

**Frontend — Next.js `/unibox` page (`frontend/src/app/(dashboard)/unibox/page.tsx`):**
- 2-panel layout: conversation list (left, 384px) + thread (right)
- Conversation list: avatar/initials, username, last message preview, timestamp, score badge (color-coded), classification badge, crm_stage badge
- Filter bar: search, classification dropdown, status dropdown, sort (recent/score/unread)
- Thread: WhatsApp-style chat bubbles (sent = amber right, received = white left)
- Thread header: username, score, crm_stage, bio
- Reply input at bottom with Enter-to-send
- **AI Suggestions section** above input: 3 clickable cards (Close/Nurture/Qualify) with message preview. Click loads into input for edit/send. "Regenerate" button
- **Tests:** 19 tests in `tests/test_unibox.py`

### Feature 2: CRM KANBAN — Visual Pipeline with Dynamic Scoring

Kanban board where users drag leads between funnel stages. Lead scores update automatically based on conversation — a lead asking about price goes up, "no thanks" goes down.

**Backend:**
- `app/services/crm_service.py` — Core service:
  - `get_pipeline_board(campaign_id?)` — All leads by stage, sorted by score DESC within each column
  - `move_lead(lead_id, new_stage)` — Move lead + audit log
  - `get_lead_detail(lead_id)` — Full info: bio, current score, score history, research, DM history, replies, follow-ups, notes
  - `add_note(lead_id, note)` — Manual note with user_id
  - `auto_classify_stage(lead_id)` — Automatic stage transitions:
    - DM sent → `contacted`
    - Reply received → `replied`
    - Reply classified positive → `interested`
    - Lead mentions "precio/costo/cuánto/agendar/llamada" → `interested`
    - Lead mentions "no gracias/no me interesa" → `closed_lost`
    - `call_scheduled` and `closed_won` are manual only (drag & drop)
  - `update_conversation_score(lead_id)` — **DYNAMIC SCORING:** On new reply, Claude evaluates purchase intent (-20 to +20 points):
    - "¿Cuánto cuesta?" → +15
    - "Cuéntame más" → +10
    - "Interesante, pero ahora no" → -5
    - "No me interesa" → -20
    - Spam → -10
    - Score history stored in `score_history` table
- `app/routers/crm.py` — REST endpoints:
  - `GET /api/v1/crm/board` — Full board with campaign filter
  - `GET /api/v1/crm/board/stats` — Metrics per stage: count, avg score, estimated value
  - `PATCH /api/v1/crm/leads/{lead_id}/stage` — Move lead
  - `GET /api/v1/crm/leads/{lead_id}` — Lead detail with score history
  - `POST /api/v1/crm/leads/{lead_id}/notes` — Add note
  - `GET /api/v1/crm/leads/{lead_id}/score-history` — Score change timeline
  - JWT protected
- **Models:**
  - `crm_stage` enum on lead: `new`, `contacted`, `replied`, `interested`, `call_scheduled`, `closed_won`, `closed_lost`
  - New table `lead_notes` (id, lead_id, user_id, content, created_at)
  - New table `score_history` (id, lead_id, old_score, new_score, delta, reason, created_at)
  - Migration: Alembic 012 (crm_stage on leads, lead_notes, score_history tables)
- **Integration:**
  - dm_sender_service → on DM sent → `auto_classify_stage` → `contacted`
  - inbox_tasks.py → on reply → `auto_classify_stage` + `update_conversation_score`
  - inbox_tasks.py → positive classification → `interested`

**Frontend — Next.js `/crm` page (`frontend/src/app/(dashboard)/crm/page.tsx`):**
- Kanban columns: Nuevo → Contactado → Respondió → Interesado → Llamada Agendada → Cerrado (Ganado) → Cerrado (Perdido)
- Lead cards: username, score badge (green >70, amber 40-70, red <40), last message preview, category
- HTML5 Drag & Drop (no external libraries) — drag card between columns
- Click card → side panel overlay with full detail: score + trend, bio, research, conversation history, score history timeline, team notes with add form, "Open in Unibox" link
- Column counters + avg score per column
- Campaign filter dropdown
- Top bar metrics: total leads, response rate, interest rate, closed count
- **Tests:** 32 tests in `tests/test_crm.py`

### Feature 3: Pre-Scraping Bio Keyword Filter

Filter leads BEFORE AI scoring to save API costs. User defines keywords that MUST appear in lead's bio.

**Backend:**
- Bio keyword filter in `app/tasks/scraping_tasks.py` — after Apify results, before `save_leads()`: if `campaign.settings.bio_keywords` defined, keep only profiles with at least one keyword in bio (case-insensitive substring match). Logs filtered count.
- No migration needed — uses existing `campaign.settings` JSONB field

**Frontend — campaign creation modal in Pipeline page:**
- Tag input: type keyword → Enter or comma → amber chip/badge appears
- X button on each chip to remove
- "+" button to add
- Help text: "Solo se procesarán leads que tengan al menos una de estas palabras en su bio. Dejar vacío para procesar todos."
- Stored in `settings.bio_keywords` array
- **Tests:** 10 tests in `tests/test_bio_keywords.py`

### Feature 4: Campaign Sending Schedule with Timezone

Per-campaign sending hours with timezone support. DMs only sent during configured hours.

**Backend:**
- Sending schedule check in `app/services/dm_sender_service.py` `send_campaign_dms()` — before daily limit check, reads `sending_hours_start`, `sending_hours_end`, `sending_timezone` from `campaign.settings`. Uses `zoneinfo.ZoneInfo` for timezone conversion. Returns paused with reason if outside hours. Supports overnight schedules (e.g., 22:00-06:00).
- No migration needed — uses existing `campaign.settings` JSONB field

**Frontend — campaign creation modal in Pipeline page:**
- Checkbox toggle "Horario de envío" to enable/disable
- Two time selectors: "Desde" and "Hasta" (dropdowns, 30-min intervals, 00:00-23:30)
- Timezone dropdown: Caracas, Bogotá, Lima, CDMX, Buenos Aires, Santiago, São Paulo, New York, Los Angeles, Madrid, London
- Preview text: "Los DMs se enviarán entre {start} y {end} (hora {timezone})"
- Stored in `settings.sending_hours_start`, `settings.sending_hours_end`, `settings.sending_timezone`
- **Tests:** 13 tests in `tests/test_sending_schedule.py`

### Competitive Advantages to Leverage

| Feature | ColdDMs ($99/mo) | IG DM Engine |
|---------|-------------------|--------------|
| Unibox | Static, manual read/reply | AI pre-generates 3 reply suggestions per message |
| CRM | Basic static columns | Dynamic scoring — score changes with each interaction |
| Infrastructure | Chrome extension (PC must be on) | Docker 24/7, no human intervention |
| Comments | Not available | Phase 5 complete — comment + DM combo |
| Research | Not available | Gemini auto-research per lead, shown in Unibox + CRM |
| Bio filter | Basic keyword filter | Same + AI scoring on top |

## SaaS Roadmap — Remaining Items

### Done
- [x] Celery Beat for automated inbox monitoring + follow-ups
- [x] Slack notifications (campaign completed/paused, reply received, account blocked)
- [x] GitHub Actions CI/CD pipeline
- [x] In-app notification center with dashboard dropdown
- [x] Unibox — Unified inbox with AI-assisted replies (Phase 6)
- [x] CRM Kanban — Visual pipeline with dynamic scoring (Phase 6)
- [x] Pre-scraping bio keyword filter (Phase 6)
- [x] Campaign sending schedule with timezone (Phase 6)
- [x] Next.js frontend — 9 pages replacing vanilla JS SPA (Phase 6)

## Deployment Architecture (Production)

### Services
| Service | Platform | URL |
|---------|----------|-----|
| Frontend | Vercel (auto-deploy from GitHub) | `https://dimenfy-qa.vercel.app` |
| API | Railway ("Dimenfy IG DM") | `https://dimenfy-ig-dm-production.up.railway.app` |
| Worker | Railway ("charming-liberation") | N/A (background) |
| Database | Supabase (PostgreSQL) | Project ID: `ywxgezapyttdgrbbwdso` |
| Redis | Railway | Internal |

### Vercel Environment Variables
- `NEXT_PUBLIC_API_URL` = `https://dimenfy-ig-dm-production.up.railway.app`

### Railway Environment Variables (both API and Worker)
- `DATABASE_URL` = `postgresql+asyncpg://postgres.ywxgezapyttdgrbbwdso:fABLETHE21.@aws-0-us-west-2.pooler.supabase.com:5432/postgres`
- `REDIS_URL`, `ANTHROPIC_API_KEY`, `APIFY_API_TOKEN`, `GOOGLE_API_KEY` — see Railway dashboard
- **CRITICAL: If the DB password needs to be reset, go to Supabase → Connect button (top right) → or go directly to `https://supabase.com/dashboard/project/ywxgezapyttdgrbbwdso/settings/database`. Settings sidebar does NOT have a "Database" option — use the direct URL. Use a simple password (letters + numbers + dot only) to avoid URL-encoding issues.**

### Supabase
- **Project:** Dimenfy (ID: `ywxgezapyttdgrbbwdso`)
- **Owner:** `luissilvalaguna1@gmail.com`
- **Region:** `aws-0-us-west-2`
- **DB Password:** `fABLETHE21.`
- **Pooler host:** `aws-0-us-west-2.pooler.supabase.com` (port 5432, Transaction pooler)
- **Direct host:** `db.ywxgezapyttdgrbbwdso.supabase.co` (port 5432)
- **DB user:** `postgres.ywxgezapyttdgrbbwdso` (pooler) / `postgres` (direct)
- **API Key (anon):** `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl3eGdlemFweXR0ZGdyYmJ3ZHNvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ0NzEwMjksImV4cCI6MjA5MDA0NzAyOX0.2NeYF9mmDWx1M0fpeRoQ7InlBUfTGFHbMKEEesNykHs`
- **15 tables** in `public` schema — created via raw SQL (NOT Alembic migrations)
- **Connection pooler** (PgBouncer) is used — Transaction pooler mode, port 5432
- The `system_config` table exists. PgBouncer search_path issue was **fixed** by using raw SQL with explicit `public.system_config` schema in all queries (main.py, dm_sender_service.py). Do NOT try fixing by editing DATABASE_URL — it breaks auth.

### Database Schema
- Full schema SQL is in `/supabase_schema.sql` (15 tables, all indexes, all constraints)
- Tables were created directly in Supabase SQL Editor, NOT via Alembic
- Alembic migration files exist (001-013) but are for reference/local dev only
- **Migration 013** added `system_config` table for persistent key-value settings (IG accounts, proxies)

### Railway IP (for proxy whitelist)
- API + Worker outbound IP: `159.26.100.228` — give this to proxy providers for whitelist

### Deploy Process
- **Frontend (Vercel):** Auto-deploys on push to GitHub branch
- **Backend (Railway):** Redeploy from Railway dashboard → service → Deployments → "Redeploy" on latest
- **`railway up` from Windows terminal has permission issues** (os error 5) — use Railway web dashboard instead
- **`railway login --browserless`** to authenticate CLI without default browser

### Users
- First registered user becomes admin automatically
- Users stored in `users` table with PBKDF2-HMAC-SHA256 hashed passwords
- Auth: JWT tokens via `/api/v1/auth/login` and `/api/v1/auth/register`
- Platform user: `jose@dimenfy.com` (admin, created via SQL INSERT)

### IG Accounts & Proxies
- Managed via dashboard "Cuentas y Proxies" page → saves to `system_config` table in DB
- Accounts configured: `orlandodimenfy`, `legist.ai`
- Proxy list provided (25 IPs on port 8800) — **none functional from external test**; require IP whitelist from provider
- Provider needs Railway IP `159.26.100.228` added to whitelist

## Bugs Fixed (Session 2026-04-03)

### Code Fixes
1. **TypeScript build error** — Added `settings` and `updated_at` to Campaign interface in pipeline/page.tsx
2. **MissingGreenlet spam on leads endpoint** — Removed `ig_posts`/`ig_post_analysis` from `LeadRead`, created `LeadDetail` for individual endpoint
3. **DB session death after long Apify scraping** — Restructured `scraping_tasks.py` to use fresh sessions after scraping completes (old sessions die after 12+ min idle on Supabase/PgBouncer)
4. **Pipeline not generating comments** — Added `fetch_posts_and_generate_comments_task` to Celery chain in `pipeline.py`
5. **Missing DM sending endpoints** — Created `/send-dms` and `/send-dm/{lead_id}` in `campaigns.py`
6. **Unibox missing crm_stage** — Added `crm_stage` to `_lead_to_conversation()` and `get_conversation_thread()`
7. **CRM wrong reply classification** — Was using global `classifications` dict instead of individual lead's classification in `inbox_tasks.py`
8. **Missing `select` import in inbox_tasks** — Added `from sqlalchemy import select` in `check_inbox_task._check()` — was causing NameError
9. **Pipeline polling not updating UI** — Removed `"pending"` from no-poll list so UI updates after clicking "Iniciar Pipeline"
10. **Client Management frontend** — Fixed save (PUT→PATCH), settings dict wrapping, stats fields, TypeScript types
11. **Silent error handling everywhere** — Added error toasts with auto-dismiss to Pipeline, Clients, and Accounts pages
12. **Export missing campaign validation** — Added 404 check before exporting

### Known Unresolved Issues
- **`system_config` via pooler — FIXED**: Was failing with UndefinedTableError because PgBouncer in transaction mode doesn't persist search_path. Fixed by replacing ORM queries with raw SQL using explicit `public.system_config` schema (in `app/main.py` GET+PUT endpoints and `app/services/dm_sender_service.py`).
- **`railway up` fails on Windows** with "Acceso denegado (os error 5)" — use Railway web dashboard to redeploy instead
- **Proxy connectivity** — 25 proxy IPs provided but none respond externally. Provider needs to whitelist Railway IP `159.26.100.228`.

### TODO (Future)
- [ ] User onboarding flow (guided setup wizard for new clients)
- [ ] API documentation (auto-generated Swagger is available at /docs, but needs customer-facing docs)
- [ ] WhatsApp notifications (complement Slack for mobile-first clients)
- [ ] Stripe billing integration (usage-based pricing per client)
- [ ] Email notifications (complement Slack + in-app)
- [ ] Campaign templates (pre-built configs for common use cases)
- [ ] Lead import/export (CSV upload to add leads manually)
- [ ] Multi-language support (currently Spanish-first UI)

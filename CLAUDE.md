# IG DM Engine — CLAUDE.md

## Project Overview

IG DM Engine is a Python-native platform that replaces an n8n + JarveePro workflow for Instagram DM automation. It provides the intelligence layer: deciding **who** to message and **what** to say, using AI-powered lead scoring and personalized DM generation.

**Phase 1 (current):** Generate qualified leads with personalized DMs as CSV/JSON. JarveePro still handles sending.

### Pipeline (5 phases)

```
1. COLLECTION → 2. SCORING → 3. RESEARCH → 4. COPYWRITING → 5. EXPORT
   (Apify)        (Claude)    (Perplexity)    (Claude)        (CSV/API)
```

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API | FastAPI | REST endpoints, orchestration |
| Task Queue | Celery + Redis | Async tasks (scraping, scoring, etc.) |
| Database | PostgreSQL (async) | Leads, campaigns, DMs, metrics |
| Cache/Broker | Redis | Celery broker + cache |
| AI Scoring/Copy | Claude API (Anthropic) | Scoring 0-100 + DM generation |
| AI Research | Perplexity API | Lead research for high-score leads |
| Scraping | Apify API | Followers, comments, IG profiles |
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
├── app/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Settings (pydantic-settings)
│   ├── database.py                # SQLAlchemy async engine + session
│   ├── models/                    # SQLAlchemy models
│   │   ├── lead.py, campaign.py, message.py, client.py, scrape_job.py
│   ├── schemas/                   # Pydantic request/response schemas
│   ├── api/endpoints/             # FastAPI route handlers
│   ├── services/                  # Business logic (apify, scoring, research, copywriting, export)
│   ├── tasks/                     # Celery tasks + pipeline orchestration
│   └── utils/                     # Dedup, text cleanup
├── tests/
└── scripts/seed_db.py
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
- `PERPLEXITY_API_KEY` — Perplexity API key for lead research
- `APIFY_API_TOKEN` — Apify API token for Instagram scraping

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

### AI Services
- **Scoring**: Claude claude-sonnet-4-5-20250514 — returns JSON with score 0-100, reason, category
- **Copywriting**: Claude claude-sonnet-4-5-20250514 — returns plain text DM
- **Research**: Perplexity sonar — only for leads with score >= 60
- DMs only generated for leads with score >= 70

### Task Pipeline
- Celery chains: scrape → score → research → write DMs
- Each phase processes leads in parallel (Celery groups)
- `task_acks_late=True` for reliability
- Campaign status updates at each phase transition

### Thresholds (configurable via env)
- `DEFAULT_SCORE_THRESHOLD=60` — minimum score to keep a lead
- `RESEARCH_SCORE_THRESHOLD=60` — minimum score to run Perplexity research
- `DM_SCORE_THRESHOLD=70` — minimum score to generate a DM

### Testing
- pytest + pytest-asyncio for async tests
- Mock external APIs (Anthropic, Perplexity, Apify) in tests
- Test files mirror source structure: `tests/test_scoring.py`, etc.

## API Keys & Secrets
- **NEVER** commit API keys or secrets to the repository
- All secrets go in `.env` (gitignored)
- Use `pydantic-settings` to load configuration

## Important Notes
- Phase 1 does NOT send DMs — output is CSV/JSON for JarveePro import
- Multi-tenant from day 1 — all queries must filter by client_id
- Apify rate limits must be respected per client plan
- Profile scraping uses synchronous Apify endpoint (`run-sync-get-dataset-items`)
- The n8n workflow reference is in `Instagram_DM_Engine_-_Step_1.json`

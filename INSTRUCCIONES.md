# IG DM Engine — Instrucciones Paso a Paso

## Resumen de lo que se hizo

Se creó el scaffold completo del proyecto IG DM Engine: **56 archivos, 2,274 líneas de Python**. Esto incluye toda la estructura base del proyecto según el documento de kickoff, listo para levantar con Docker y empezar a probar cada servicio individualmente.

### Lo que se construyó

| Componente | Archivos | Descripción |
|---|---|---|
| Infraestructura | `Dockerfile`, `docker-compose.yml`, `.env.example`, `requirements.txt` | Contenedores para API, Worker, PostgreSQL, Redis |
| App Core | `main.py`, `config.py`, `database.py` | FastAPI entry point, configuración con pydantic-settings, SQLAlchemy async |
| Modelos (5 tablas) | `models/client.py`, `campaign.py`, `lead.py`, `message.py`, `scrape_job.py` | Todas las tablas del esquema con relaciones, índices y constraint UNIQUE para dedup |
| Schemas | `schemas/client.py`, `campaign.py`, `lead.py`, `message.py` | Validación Pydantic v2 para request/response |
| Servicios (5) | `services/apify_service.py`, `scoring_service.py`, `research_service.py`, `copywriting_service.py`, `export_service.py` | Toda la lógica de negocio: scraping Apify, scoring Claude, research Perplexity, DMs Claude, export CSV/JSON |
| Tasks Celery (5) | `tasks/celery_app.py`, `scraping_tasks.py`, `scoring_tasks.py`, `research_tasks.py`, `copywriting_tasks.py`, `pipeline.py` | Pipeline encadenado: scrape → score → research → write DMs |
| API Endpoints (5 routers) | `api/endpoints/campaigns.py`, `leads.py`, `messages.py`, `scraping.py`, `export.py` | Todos los endpoints REST definidos en el kickoff |
| Utilidades | `utils/dedup.py`, `utils/text_cleanup.py` | Deduplicación de leads y limpieza de texto/emojis |
| Migraciones | `alembic/env.py`, `alembic.ini` | Setup de Alembic para migraciones async |
| Tests | `tests/test_scoring.py`, `test_copywriting.py`, `test_api.py`, `test_utils.py` | Tests unitarios con mocks de APIs externas |
| Seed | `scripts/seed_db.py` | Datos de prueba para desarrollo |
| Docs | `CLAUDE.md` | Documentación completa del proyecto para asistentes IA |

---

## Instrucciones: Cómo Levantar el Proyecto

### Paso 1: Clonar y configurar variables de entorno

```bash
# Clonar el repositorio
git clone <URL_DEL_REPO> ig-dm-engine
cd ig-dm-engine

# Copiar el archivo de variables de entorno
cp .env.example .env

# Editar .env con tus API keys reales
nano .env
```

Las API keys que NECESITAS tener:
- **ANTHROPIC_API_KEY** — Clave de la API de Claude (para scoring y copywriting)
- **PERPLEXITY_API_KEY** — Clave de la API de Perplexity (para research)
- **APIFY_API_TOKEN** — Token de la API de Apify (para scraping de Instagram)

### Paso 2: Levantar con Docker Compose

```bash
# Levantar todos los servicios (API + Worker + PostgreSQL + Redis)
docker compose up --build

# O en background:
docker compose up --build -d
```

Esto levanta:
- **API** en `http://localhost:8000` (FastAPI con auto-reload)
- **Worker** Celery con 4 workers concurrentes
- **PostgreSQL** en puerto `5432`
- **Redis** en puerto `6379`

### Paso 3: Ejecutar migraciones de base de datos

```bash
# Con Docker corriendo, ejecutar en el contenedor de la API:
docker compose exec api alembic upgrade head

# O si trabajas localmente:
alembic upgrade head
```

**NOTA:** Antes de esto necesitas crear la primera migración:
```bash
docker compose exec api alembic revision --autogenerate -m "initial tables"
docker compose exec api alembic upgrade head
```

### Paso 4: Cargar datos de prueba (opcional)

```bash
docker compose exec api python scripts/seed_db.py
```

Esto crea: 1 cliente de prueba, 1 campaña, 3 leads de ejemplo.

### Paso 5: Verificar que funciona

```bash
# Health check
curl http://localhost:8000/health
# Debe responder: {"status": "healthy", "version": "0.1.0"}

# Ver documentación interactiva de la API
# Abrir en navegador: http://localhost:8000/docs
```

### Paso 6: Ejecutar tests

```bash
# Con Docker:
docker compose exec api pytest

# Localmente (necesitas un virtualenv):
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest
```

---

## Instrucciones: Cómo Usar la API

### Flujo completo de una campaña

#### 1. Crear un cliente

```bash
curl -X POST http://localhost:8000/api/v1/campaigns/ \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "<UUID_DEL_CLIENTE>",
    "name": "Campaña Followers de @marketingguru",
    "source_type": "followers",
    "source_value": "marketingguru"
  }'
```

> **Nota:** Primero necesitas un cliente en la DB. Usa el seed script o crea uno directamente en PostgreSQL.

#### 2. Iniciar el pipeline completo

```bash
curl -X POST http://localhost:8000/api/v1/campaigns/<CAMPAIGN_ID>/start
```

Esto dispara automáticamente las 4 fases:
1. **Scraping** — Descarga followers/comentarios via Apify
2. **Scoring** — Califica cada lead 0-100 con Claude
3. **Research** — Investiga leads con score >= 60 via Perplexity
4. **Copywriting** — Genera DMs personalizados para leads con score >= 70

#### 3. Ver el progreso

```bash
# Estadísticas de la campaña
curl http://localhost:8000/api/v1/campaigns/<CAMPAIGN_ID>/stats

# Ver todos los leads
curl http://localhost:8000/api/v1/leads/?campaign_id=<CAMPAIGN_ID>

# Ver solo leads con score
curl http://localhost:8000/api/v1/leads/scored?campaign_id=<CAMPAIGN_ID>

# Ver leads listos para enviar DM
curl http://localhost:8000/api/v1/leads/dm-ready?campaign_id=<CAMPAIGN_ID>
```

#### 4. Exportar para JarveePro

```bash
# CSV (para importar en JarveePro)
curl http://localhost:8000/api/v1/export/<CAMPAIGN_ID>/csv -o leads.csv

# JSON
curl http://localhost:8000/api/v1/export/<CAMPAIGN_ID>/json
```

---

## Instrucciones: Desarrollo Local (sin Docker)

Si prefieres desarrollar sin Docker:

```bash
# 1. Crear virtualenv
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Levantar PostgreSQL y Redis manualmente (o con Docker solo para infra)
docker compose up db redis -d

# 3. Ejecutar migraciones
alembic upgrade head

# 4. Levantar la API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. En otra terminal, levantar el worker Celery
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
```

---

## Convenciones del Proyecto

1. **Siempre usar async/await** para operaciones de DB y HTTP
2. **Nunca commitear API keys** — van en `.env`
3. **Usar Alembic** para cambios de esquema — nunca modificar DB directamente
4. **Filtrar por client_id** en todas las queries — el sistema es multi-tenant
5. **Mockear APIs externas** en tests — nunca llamar a Claude/Perplexity/Apify en tests
6. **UUIDs** como primary keys en todas las tablas
7. **Pydantic v2** para toda validación de datos

# IG DM Engine — Status del Proyecto

> Última actualización: 2 de marzo de 2026

---

## Resumen General

| Métrica | Antes | Ahora |
|---|---|---|
| Archivos totales | 56 | 66 |
| Archivos Python | 48 | 57 |
| Líneas de Python | 2,274 | 3,235 |
| Modelos de DB | 5 tablas | 5 tablas |
| Endpoints API | 16 | **21** (+5 Client CRUD) |
| Servicios | 5 | 5 (mejorados) |
| Celery Tasks | 5 | 5 (con retry + error handling) |
| Tests | 14 (4 archivos) | **54 (9 archivos)** |

---

## Estado por Sprint

### Sprint 1: Infraestructura Base — 85% completado

| Tarea | Estado | Notas |
|---|---|---|
| Estructura del repositorio | HECHO | 66 archivos creados |
| Docker Compose (API + DB + Redis + Worker) | HECHO | `docker-compose.yml` con 4 servicios |
| Modelos SQLAlchemy + setup Alembic | HECHO | 5 modelos + `alembic/env.py` async |
| FastAPI app con health check | HECHO | `GET /health` funcionando |
| Configuración Celery + task pipeline | HECHO | Pipeline encadenado de 4 fases |
| Tests básicos | HECHO | 9 archivos de tests, 54 tests |
| **Migración inicial de DB** | PENDIENTE | Falta ejecutar `alembic revision --autogenerate` (requiere DB corriendo) |
| **Probar Docker Compose end-to-end** | PENDIENTE | Requiere instalar Docker |

---

### Sprint 2: Scraping + Scoring — 75% completado

| Tarea | Estado | Notas |
|---|---|---|
| `apify_service.py` — integración completa | HECHO | 3 actors configurados, sync + async scraping |
| `scoring_service.py` — scoring con Claude | HECHO | Prompt completo, output JSON, scoring 0-100 |
| Integración `text_cleanup` en scoring | HECHO | Bio se limpia antes de enviar a Claude |
| Celery tasks para scrape + score | HECHO | Con retry logic (3 reintentos, backoff exponencial) |
| Endpoints: crear campaña, iniciar scraping, ver leads | HECHO | 16 endpoints de campaigns + leads + scraping |
| Deduplicación por (client_id, ig_username) | HECHO | Constraint UNIQUE + `utils/dedup.py` |
| Tests de scoring con mocks | HECHO | 3 test cases en `test_scoring.py` |
| **Probar con API key real de Apify** | PENDIENTE | Necesita token real |
| **Probar scoring con API key real de Claude** | PENDIENTE | Necesita key real |

---

### Sprint 3: Research + Copywriting — 75% completado

| Tarea | Estado | Notas |
|---|---|---|
| `research_service.py` — integración Perplexity | HECHO | Prompt completo, modelo `sonar` |
| `copywriting_service.py` — generación DMs | HECHO | Prompt con 10 reglas, formato DM definido |
| **DM Variant B para A/B testing** | HECHO | Prompt separado con ángulo diferente |
| Pipeline completo: scrape → score → research → DM | HECHO | `pipeline.py` con Celery chain |
| Endpoint de export CSV/JSON | HECHO | `GET /export/{id}/csv` y `/json` |
| Tests de research y copywriting | HECHO | 3 tests research + 5 tests copywriting |
| **Probar con API key real de Perplexity** | PENDIENTE | Necesita key real |
| **Probar DM generation con datos reales** | PENDIENTE | Necesita leads reales |

---

### Sprint 4: Hardening + Deploy — 60% completado

| Tarea | Estado | Notas |
|---|---|---|
| Retry logic en Celery tasks | HECHO | `autoretry_for`, `max_retries=3`, `retry_backoff=True`, `retry_jitter=True` |
| Error handling robusto | HECHO | Campaign se marca "failed" con error en stats |
| Shared task base (`tasks/base.py`) | HECHO | Elimina duplicación de `_run_async`, helper `fail_campaign` |
| Client CRUD endpoints | HECHO | 5 endpoints (POST/GET/LIST/PATCH/DELETE con soft delete) |
| Validación con Enums | HECHO | `SourceType`, `CampaignStatus`, `LeadStatus`, `LeadCategory` |
| Structured logging (JSON) | HECHO | `JSONFormatter` para prod, `DevFormatter` para dev |
| Request tracing middleware | HECHO | `X-Request-ID` header, logging por request |
| Stats por campaña | HECHO | Endpoint `GET /campaigns/{id}/stats` |
| Documentación API (OpenAPI) | HECHO | Auto-generada por FastAPI en `/docs` |
| **Deploy inicial** | PENDIENTE | No iniciado (requiere Docker + API keys) |
| **Autenticación/autorización** | PENDIENTE | Endpoints abiertos, necesita API key o JWT |
| **Rate limiting en API** | PENDIENTE | No implementado |

---

## Lo que falta (requiere tu participación)

### Requiere Docker (instalar + correr)

1. **Generar la migración inicial de Alembic**
   ```bash
   docker compose up db redis -d
   alembic revision --autogenerate -m "initial tables"
   alembic upgrade head
   ```

2. **Probar Docker Compose end-to-end**
   ```bash
   docker compose up --build
   # Verificar: API en localhost:8000, Worker conectado, DB creada
   ```

### Requiere API Keys (registrarse + configurar)

3. **Crear `.env` con keys reales**
   ```bash
   cp .env.example .env
   # Llenar: ANTHROPIC_API_KEY, APIFY_API_TOKEN, PERPLEXITY_API_KEY
   ```

4. **Probar scoring con Claude** — Verificar que el prompt devuelve JSON válido
5. **Probar scraping con Apify** — Verificar que los perfiles se guardan correctamente
6. **Probar research con Perplexity** — Verificar calidad del research
7. **Probar pipeline completo** — Campaña real de 50-100 leads

### Mejoras futuras (post-validación)

8. **Autenticación** — API key o JWT para proteger endpoints
9. **Rate limiting** — Limitar requests por IP/cliente
10. **Webhooks de Apify** — Reemplazar polling por webhooks
11. **Dashboard frontend** — Fuera de Fase 1

---

## Qué se puede hacer 100% sin APIs ni Docker

| Tarea | Estado |
|---|---|
| Retry logic en Celery tasks | HECHO |
| Error handling con campaign "failed" | HECHO |
| Client CRUD endpoints | HECHO |
| Integrar text_cleanup en scoring | HECHO |
| Enums de validación | HECHO |
| Expandir tests (14 → 54) | HECHO |
| DM Variant B para A/B testing | HECHO |
| Structured logging + request tracing | HECHO |

**Todo lo que se podía hacer sin APIs ni Docker está completado.**

---

## Arquitectura del Pipeline

```
POST /campaigns/{id}/start
         │
         ▼
┌─────────────────┐
│  SCRAPE LEADS   │ → Apify API (followers/comments/profiles)
│  scraping_tasks │ → Filtra privados, guarda en DB con dedup
│  retry: 3x      │ → Campaign → "failed" si falla
└────────┬────────┘
         │ lead_ids[]
         ▼
┌─────────────────┐
│  SCORE LEADS    │ → Claude API (claude-sonnet-4-5-20250514)
│  scoring_tasks  │ → Score 0-100 + categoría + razón
│  text_cleanup   │ → Bio limpia antes de enviar a Claude
└────────┬────────┘
         │ scored_lead_ids[]
         ▼
┌─────────────────┐
│ RESEARCH LEADS  │ → Perplexity API (sonar)
│ research_tasks  │ → Solo leads con score >= 60
└────────┬────────┘
         │ researched_lead_ids[]
         ▼
┌─────────────────────┐
│  WRITE DMs          │ → Claude API (claude-sonnet-4-5-20250514)
│  copywriting_tasks  │ → Solo leads con score >= 70
│  + Variant B (A/B)  │ → Genera 2 variantes con ángulo diferente
└────────┬────────────┘
         │
         ▼
   Campaign status = "ready"
   GET /export/{id}/csv → CSV para JarveePro
   GET /export/{id}/json → JSON con datos completos
```

---

## Archivos Clave para Referencia Rápida

| Qué necesitas | Archivo |
|---|---|
| Levantar todo | `docker-compose.yml` |
| Variables de entorno | `.env.example` |
| Entry point de la API | `app/main.py` |
| Configuración | `app/config.py` |
| Logging configuración | `app/logging_config.py` |
| Prompt de scoring | `app/services/scoring_service.py` |
| Prompt de DMs + Variant B | `app/services/copywriting_service.py` |
| Prompt de research | `app/services/research_service.py` |
| Pipeline Celery | `app/tasks/pipeline.py` |
| Task base (retry/errors) | `app/tasks/base.py` |
| Modelo de leads | `app/models/lead.py` |
| Enums de validación | `app/schemas/enums.py` |
| Endpoints de campañas | `app/api/endpoints/campaigns.py` |
| Endpoints de clientes | `app/api/endpoints/clients.py` |
| Export CSV/JSON | `app/services/export_service.py` |
| Tests | `tests/` (9 archivos, 54 tests) |

---

## Nuevos Endpoints (Sesión 2 de marzo)

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/v1/clients/` | Crear cliente |
| GET | `/api/v1/clients/` | Listar clientes (filtro por is_active) |
| GET | `/api/v1/clients/{id}` | Ver detalle de cliente |
| PATCH | `/api/v1/clients/{id}` | Actualizar cliente |
| DELETE | `/api/v1/clients/{id}` | Soft delete (desactivar) |

---

## Tests Nuevos (Sesión 2 de marzo)

| Archivo | Tests | Cobertura |
|---|---|---|
| `test_clients.py` | 10 | CRUD endpoints con mock DB |
| `test_export.py` | 7 | CSV/JSON export, campos nulos, vacío |
| `test_research.py` | 3 | Perplexity API mock, prompt, clean bio |
| `test_enums.py` | 6 | Validación de enums + schema |
| `test_tasks_config.py` | 11 | Retry config, excepciones, decorators |
| `test_copywriting.py` | +2 | Variant B generation + prompt |
| **Total nuevos** | **39** | — |

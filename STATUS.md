# IG DM Engine — Status del Proyecto

> Última actualización: 27 de febrero de 2026

---

## Resumen General

| Métrica | Valor |
|---|---|
| Archivos creados | 56 |
| Líneas de Python | 2,274 |
| Modelos de DB | 5 tablas |
| Endpoints API | 14 |
| Servicios | 5 |
| Celery Tasks | 5 |
| Tests | 4 archivos |

---

## Estado por Sprint

### Sprint 1 (Semana 1): Infraestructura Base

| Tarea | Estado | Notas |
|---|---|---|
| Estructura del repositorio | HECHO | 56 archivos creados |
| Docker Compose (API + DB + Redis + Worker) | HECHO | `docker-compose.yml` con 4 servicios |
| Modelos SQLAlchemy + setup Alembic | HECHO | 5 modelos + `alembic/env.py` async |
| FastAPI app con health check | HECHO | `GET /health` funcionando |
| Configuración Celery + task pipeline | HECHO | Pipeline encadenado de 4 fases |
| Tests básicos | HECHO | 4 archivos de tests con mocks |
| **Migración inicial de DB** | PENDIENTE | Falta ejecutar `alembic revision --autogenerate` |
| **Probar Docker Compose end-to-end** | PENDIENTE | Falta levantar y verificar que todo conecta |

**Sprint 1 progreso: ~85% completado**

---

### Sprint 2 (Semana 2): Scraping + Scoring

| Tarea | Estado | Notas |
|---|---|---|
| `apify_service.py` — integración completa | HECHO (código) | 3 actors configurados, sync + async scraping |
| `scoring_service.py` — scoring con Claude | HECHO (código) | Prompt completo, output JSON, scoring 0-100 |
| Celery tasks para scrape + score | HECHO (código) | `scrape_leads_task`, `score_leads_task` |
| Endpoints: crear campaña, iniciar scraping, ver leads | HECHO (código) | 8 endpoints de campaigns + leads + scraping |
| Deduplicación por (client_id, ig_username) | HECHO | Constraint UNIQUE + `utils/dedup.py` |
| Tests de scoring con mocks | HECHO | 3 test cases en `test_scoring.py` |
| **Probar con API key real de Apify** | PENDIENTE | Necesita token real para validar |
| **Probar scoring con API key real de Claude** | PENDIENTE | Necesita key real para validar output JSON |
| **Test de integración scrape → score** | PENDIENTE | Falta test end-to-end con DB real |

**Sprint 2 progreso: ~60% completado** (código listo, falta validación con APIs reales)

---

### Sprint 3 (Semana 3): Research + Copywriting

| Tarea | Estado | Notas |
|---|---|---|
| `research_service.py` — integración Perplexity | HECHO (código) | Prompt completo, modelo `sonar` |
| `copywriting_service.py` — generación DMs | HECHO (código) | Prompt con 10 reglas, formato DM definido |
| Pipeline completo: scrape → score → research → DM | HECHO (código) | `pipeline.py` con Celery chain |
| Endpoint de export CSV/JSON | HECHO (código) | `GET /export/{id}/csv` y `/json` |
| Tests del pipeline end-to-end | PARCIAL | Tests unitarios hechos, falta integration test |
| **Probar con API key real de Perplexity** | PENDIENTE | Necesita key real |
| **Probar DM generation con datos reales** | PENDIENTE | Necesita leads reales para validar calidad |
| **Validar calidad de DMs generados** | PENDIENTE | Revisar que cumplan las 10 reglas |

**Sprint 3 progreso: ~50% completado** (código listo, falta toda la validación)

---

### Sprint 4 (Semana 4): Polish + Deploy

| Tarea | Estado | Notas |
|---|---|---|
| Manejo de errores robusto (retry, fallback) | PARCIAL | Tasks tienen try/except, falta retry policy |
| Logging estructurado | PARCIAL | Logger básico, falta formato JSON |
| Stats por campaña (contadores en tiempo real) | HECHO | Endpoint `GET /campaigns/{id}/stats` |
| Documentación API (OpenAPI) | HECHO | Auto-generada por FastAPI en `/docs` |
| Deploy inicial (Railway o Hetzner) | PENDIENTE | No iniciado |
| Prueba con datos reales del cliente | PENDIENTE | No iniciado |

**Sprint 4 progreso: ~20% completado**

---

## Lo que falta hacer (ordenado por prioridad)

### Prioridad ALTA (bloqueantes)

1. **Generar la migración inicial de Alembic**
   - Ejecutar `alembic revision --autogenerate -m "initial tables"`
   - Ejecutar `alembic upgrade head`
   - Verificar que las 5 tablas se crean correctamente

2. **Probar Docker Compose end-to-end**
   - `docker compose up --build`
   - Verificar que API responde en `localhost:8000`
   - Verificar que Worker Celery conecta con Redis
   - Verificar que la DB PostgreSQL acepta conexiones

3. **Validar con API keys reales**
   - Poner keys reales en `.env`
   - Probar scoring de un perfil real con Claude
   - Probar research de un perfil real con Perplexity
   - Probar scraping de una cuenta real con Apify

### Prioridad MEDIA (necesarios para producción)

4. **Test de integración del pipeline completo**
   - Crear campaña → scrape → score → research → write DM → export CSV
   - Validar que cada paso pasa los datos correctos al siguiente

5. **Retry policy en Celery tasks**
   - Agregar `autoretry_for`, `retry_backoff`, `max_retries` a cada task
   - Manejar rate limits de Claude y Perplexity

6. **Endpoint CRUD de clientes**
   - Actualmente no hay endpoints para crear/editar clientes
   - Necesario para multi-tenant real

7. **Logging estructurado (JSON)**
   - Configurar logging con formato JSON para producción
   - Agregar request_id para trazabilidad

### Prioridad BAJA (mejoras futuras)

8. **Variante B de DMs** para A/B testing
9. **Webhooks de Apify** en vez de polling para jobs largos
10. **Dashboard frontend** (fuera de Fase 1)
11. **Rate limiting en la API**
12. **Autenticación/autorización** en endpoints

---

## Arquitectura del Pipeline

```
POST /campaigns/{id}/start
         │
         ▼
┌─────────────────┐
│  SCRAPE LEADS   │ → Apify API (followers/comments/profiles)
│  scraping_tasks │ → Filtra privados, guarda en DB con dedup
└────────┬────────┘
         │ lead_ids[]
         ▼
┌─────────────────┐
│  SCORE LEADS    │ → Claude API (claude-sonnet-4-5-20250514)
│  scoring_tasks  │ → Score 0-100 + categoría + razón
└────────┬────────┘
         │ scored_lead_ids[]
         ▼
┌─────────────────┐
│ RESEARCH LEADS  │ → Perplexity API (sonar)
│ research_tasks  │ → Solo leads con score >= 60
└────────┬────────┘
         │ researched_lead_ids[]
         ▼
┌─────────────────┐
│  WRITE DMs      │ → Claude API (claude-sonnet-4-5-20250514)
│ copywriting_tasks│ → Solo leads con score >= 70
└────────┬────────┘
         │
         ▼
   Campaign status = "ready"
   GET /export/{id}/csv → CSV para JarveePro
```

---

## Archivos Clave para Referencia Rápida

| Qué necesitas | Archivo |
|---|---|
| Levantar todo | `docker-compose.yml` |
| Variables de entorno | `.env.example` |
| Entry point de la API | `app/main.py` |
| Configuración | `app/config.py` |
| Prompt de scoring | `app/services/scoring_service.py` |
| Prompt de DMs | `app/services/copywriting_service.py` |
| Prompt de research | `app/services/research_service.py` |
| Pipeline Celery | `app/tasks/pipeline.py` |
| Modelo de leads | `app/models/lead.py` |
| Endpoints de campañas | `app/api/endpoints/campaigns.py` |
| Export CSV | `app/services/export_service.py` |
| Tests | `tests/` |

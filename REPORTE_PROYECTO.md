# IG DM Engine — Reporte de Estado del Proyecto

**Fecha:** 23 de marzo de 2026
**Proyecto:** IG DM Engine — Plataforma de automatización de DMs de Instagram
**Repositorio:** DimenfyQA (GitHub)
**Estado general:** Operativo en entorno local con Docker

---

## Resumen Ejecutivo

IG DM Engine es una plataforma desarrollada 100% en Python que **reemplaza completamente** el flujo anterior basado en **n8n + JarveePro**. El sistema maneja el pipeline completo de forma autónoma: decide a quién enviar mensajes, qué decir, y **envía los DMs directamente** a Instagram sin depender de herramientas externas de envío.

**El sistema fue probado exitosamente el 23 de marzo de 2026**, enviando DMs reales a cuentas de Instagram desde el dashboard web.

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    IG DM ENGINE                             │
│                                                             │
│  1. COLLECTION  →  2. SCORING  →  3. RESEARCH              │
│    (Apify)         (Claude AI)    (Gemini AI)               │
│       ↓                                                     │
│  4. COPYWRITING →  5. SENDING  →  6. EXPORT                │
│    (Claude AI)     (instagrapi)   (CSV/JSON/Excel)          │
│                                                             │
│  Dashboard Web ←── FastAPI ←── PostgreSQL + Redis + Celery  │
└─────────────────────────────────────────────────────────────┘
```

### Stack Tecnológico

| Componente | Tecnología | Propósito |
|---|---|---|
| API | FastAPI | Endpoints REST, orquestación |
| Cola de tareas | Celery + Redis | Tareas asíncronas |
| Base de datos | PostgreSQL (async) | Leads, campañas, DMs, métricas |
| IA — Scoring | Claude Sonnet 4.6 | Puntuación 0-100 por lead |
| IA — Copywriting | Claude Sonnet 4.6 | Generación de DMs personalizados |
| IA — Research | Google Gemini 2.0 Flash | Investigación de leads |
| Scraping | Apify API | Perfiles, comentarios de IG |
| Envío de DMs | instagrapi | Envío directo sin JarveePro |
| Seguridad | Fernet (AES-128) | Encriptación de sesiones IG |
| Infraestructura | Docker + Docker Compose | Despliegue completo |

---

## Métricas del Código

| Métrica | Valor |
|---|---|
| Archivos Python | 90 |
| Líneas de código Python | 10,390 |
| Líneas en servicios de negocio | 3,999 |
| Líneas del dashboard HTML/JS | 2,782 |
| Migraciones de DB | 7 |
| Archivos de test | 10 |
| Tests totales | 103 (100 passed, 3 skipped) |
| Commits totales | 78 |

---

## Fases Completadas

### FASE 1 — Pipeline de generación de leads (COMPLETADA)

Pipeline completo: scraping de Instagram → scoring con IA → research → generación de DMs personalizados → exportación.

**Funcionalidades:**
- Scraping multi-actor con 3 scrapers de comentarios en paralelo (3x más leads)
- Scoring por lotes con Claude AI (20 leads por llamada API)
- Investigación automática con Gemini para leads con score >= 60
- Generación de DMs por lotes con variantes A/B (5 leads por llamada)
- Exportación a CSV, JSON y Excel
- Filtro automático de cuentas privadas en 3 capas

### FASE 2 — Envío directo de DMs (COMPLETADA)

**Esto es lo que elimina JarveePro.** El sistema envía DMs directamente a Instagram usando `instagrapi`.

**Funcionalidades de seguridad anti-detección:**
- Fingerprinting de dispositivo (5 perfiles Android realistas)
- User-Agent realista que coincide con el perfil de dispositivo
- Delays aleatorios entre DMs (45-120 segundos)
- Jitter de 1-3s antes de cada envío
- Rotación de múltiples cuentas de Instagram
- Rate limiting en 3 capas (diario, por hora, warm-up)
- Cooldown automático ante challenges y bloqueos de Instagram
- Encriptación de sesiones de Instagram en disco (Fernet/AES)
- Validación pre-envío: verifica que la cuenta destino es pública

**Sistema de rate limiting:**
- Límite diario: 30 DMs/día por cuenta madura
- Límite por hora: 10 DMs/hora por cuenta
- Warm-up: cuentas nuevas empiezan con 5 DMs/día, subiendo linealmente en 7 días

### FASE 3 — Inbox y follow-ups (PARCIAL)

Modelos y schemas creados para:
- Monitoreo de inbox
- Clasificación de respuestas
- Follow-ups automáticos
- Servicios de inbox, follow-up y A/B testing implementados

---

## Prueba de Funcionamiento — 23 de marzo de 2026

### Envío exitoso de DM

El sistema fue ejecutado localmente el 23 de marzo de 2026 y se completó un envío real de DM a Instagram.

**Configuración utilizada:**
```
Docker Compose: API + PostgreSQL + Redis + Celery Worker
Cuenta IG: orlandodimenfy
Puerto: http://localhost:8000
```

**Flujo ejecutado:**
1. Se levantaron los servicios con `docker compose up --build`
2. Se creó una campaña desde el dashboard web
3. Se ejecutó el pipeline completo (scrape → score → copywrite)
4. Se presionó "Send DMs" desde el dashboard
5. El DM fue entregado exitosamente a la cuenta destino en Instagram

**Log de confirmación:** El usuario confirmó recepción del DM enviado por el sistema.

---

## Comparación: Antes vs Ahora

| Aspecto | Antes (n8n + JarveePro) | Ahora (IG DM Engine) |
|---|---|---|
| Herramientas necesarias | n8n + JarveePro + config manual | Solo Docker Compose |
| Envío de DMs | JarveePro (licencia paga, Windows) | instagrapi (gratis, multiplataforma) |
| Personalización | Templates estáticos | IA genera DMs únicos por lead |
| Scoring de leads | Manual o reglas básicas | Claude AI scoring 0-100 |
| Research | Manual | Gemini automático |
| Anti-detección | Configuración manual en JarveePro | Automático (fingerprint, delays, rotation) |
| Multi-cuenta | Manual en JarveePro | Rotación automática round-robin |
| Rate limiting | Manual | 3 capas automáticas |
| Costo de envío | Licencia JarveePro (~$30-60/mes) | $0 (instagrapi es open source) |
| Plataforma | Solo Windows (JarveePro) | Cualquier OS con Docker |
| Dashboard | Ninguno | Dashboard web incluido |
| A/B Testing | No disponible | Integrado con variantes A/B |
| Encriptación | No | Sesiones encriptadas con AES |

---

## Cómo Ejecutar el Sistema

### Requisitos
- Docker y Docker Compose instalados
- Archivo `.env` con las API keys configuradas

### Comandos

```bash
# 1. Clonar el repositorio
git clone <repo-url>
cd DimenfyQA

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con las API keys reales

# 3. Levantar todos los servicios
docker compose up --build

# 4. Acceder al dashboard
# Abrir http://localhost:8000 en el navegador

# 5. Ejecutar tests
pytest
```

### Variables de entorno esenciales

```env
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/igdm
REDIS_URL=redis://redis:6379/0
ANTHROPIC_API_KEY=sk-ant-...          # Para scoring y copywriting
APIFY_API_TOKEN=apify_api_...         # Para scraping de Instagram
GOOGLE_API_KEY=AI...                  # Para research con Gemini
IG_ACCOUNTS=usuario:contraseña        # Cuenta(s) de Instagram para envío
```

---

## Estructura de Archivos Clave

```
DimenfyQA/
├── docker-compose.yml              # Orquestación de servicios
├── app/
│   ├── main.py                     # FastAPI entry point
│   ├── services/
│   │   ├── apify_service.py        # Scraping (401 líneas)
│   │   ├── scoring_service.py      # Scoring con Claude (253 líneas)
│   │   ├── copywriting_service.py  # DMs con Claude (408 líneas)
│   │   ├── research_service.py     # Research con Gemini (237 líneas)
│   │   ├── dm_sender_service.py    # Envío directo de DMs (828 líneas)
│   │   ├── content_analysis_service.py  # Análisis multimodal (431 líneas)
│   │   ├── analytics_service.py    # Analíticas (256 líneas)
│   │   └── webhook_service.py      # Webhooks (238 líneas)
│   ├── static/
│   │   └── dashboard.html          # Frontend SPA (2,782 líneas)
│   └── tasks/
│       └── pipeline.py             # Orquestación del pipeline
├── alembic/versions/               # 7 migraciones de DB
├── tests/                          # 10 archivos, 103 tests
└── scripts/                        # Seeds y utilidades
```

---

## Historial de Commits (resumen de hitos)

| # | Commit | Descripción |
|---|---|---|
| 1 | `e587467` | Scaffold inicial — estructura completa Phase 1 |
| 10 | `be931ca` | Dashboard premium con pipeline visualizer |
| 20 | `de62efb` | Fix JSON parsing de respuestas de Claude |
| 30 | `2aefe14` | Pipeline paralelo + galería de DMs + exportación Excel |
| 40 | `92c3058` | Batch scoring y DM generation (10x más rápido) |
| 50 | `9b7ce4c` | Phase 2: servicio de envío de DMs + integración Celery |
| 55 | `9b36f48` | Phase 2 completa: multi-cuenta, warm-up, health |
| 60 | `9d55afe` | Análisis multimodal de contenido con Gemini |
| 65 | `bde9a31` | Multi-actor comment scraping (3 scrapers en paralelo) |
| 70 | `21bdabf` | Filtro de cuentas públicas + seguridad completa |
| 78 | `a15041d` | Fix: registro de tarea send_dms en Celery |

---

## Estado de Tests

```
tests/test_api.py           — API endpoints
tests/test_clients.py       — Client CRUD
tests/test_enums.py         — Enumeraciones
tests/test_scoring.py       — 17 tests (batch scoring, auto-score, edge cases)
tests/test_copywriting.py   — 21 tests (single DM, batch, write_dms_batch)
tests/test_dm_sender.py     — 62 passed, 3 skipped (envío, seguridad, rotación)
tests/test_export.py        — Exportación CSV/JSON/Excel
tests/test_research.py      — Research con Gemini/Perplexity
tests/test_tasks_config.py  — Configuración de Celery
tests/test_utils.py         — Utilidades
─────────────────────────────────────────
TOTAL: 103 tests (100 passed, 3 skipped)
```

---

## Conclusión

El proyecto **IG DM Engine** está operativo y cumple su objetivo principal: **reemplazar completamente n8n + JarveePro** con una solución propia, más segura, más inteligente y sin costos de licencia.

El envío de DMs fue verificado el 23 de marzo de 2026 en un entorno real.

**Próximos pasos sugeridos:**
1. Completar Phase 3 (monitoreo de inbox y follow-ups automáticos)
2. Desplegar en un servidor cloud (VPS con Docker)
3. Configurar proxies residenciales para mayor seguridad
4. Escalar a múltiples cuentas de Instagram en rotación

---

*Reporte generado el 23 de marzo de 2026*
*IG DM Engine v1.0 — Dimenfy*

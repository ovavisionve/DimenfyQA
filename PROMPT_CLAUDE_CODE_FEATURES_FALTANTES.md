# PROMPT PARA CLAUDE CODE — IG DM Engine: Features Faltantes

## Contexto del Proyecto

IG DM Engine es una plataforma de automatización de DMs de Instagram construida en Python. El stack es:
- **Backend:** FastAPI + PostgreSQL (async con SQLAlchemy) + Celery + Redis
- **Frontend:** Dashboard SPA en HTML/JS (archivo `app/static/dashboard.html`) — NO es React ni Next.js, es vanilla JS con fetch API
- **Envío:** instagrapi (API directa de Instagram)
- **IA:** Claude API (scoring + copywriting) + Gemini API (research)
- **Infra:** Docker Compose (5 servicios: api, worker, beat, db, redis)
- **Auth:** JWT con roles admin/manager/viewer

### Estructura actual relevante:
```
app/
├── main.py                          # FastAPI entry point
├── models/                          # SQLAlchemy models
├── services/
│   ├── dm_sender_service.py         # Envío de DMs + comentarios (828 líneas)
│   ├── inbox_service.py             # Monitoreo de inbox (clasifica respuestas)
│   ├── followup_service.py          # Follow-ups automáticos
│   ├── scoring_service.py           # Scoring con Claude
│   ├── copywriting_service.py       # Generación de DMs con Claude
│   ├── comment_copywriting_service.py
│   ├── research_service.py          # Research con Gemini
│   ├── analytics_service.py
│   ├── auth_service.py              # JWT auth
│   └── notification_service.py      # Notificaciones in-app + Slack
├── static/
│   └── dashboard.html               # Frontend SPA completo (tema oscuro, sidebar, 7 módulos)
├── tasks/
│   ├── pipeline.py                  # Orquestación del pipeline
│   ├── inbox_tasks.py               # Celery Beat: inbox check cada 5min
│   └── followup_tasks.py            # Celery Beat: follow-ups cada 1h
└── routers/                         # FastAPI routers
```

### Lo que YA existe y funciona:
- Pipeline completo: scrape → score → research → copywrite → send
- Envío de DMs con anti-detección (fingerprinting, delays, rotación multi-cuenta, rate limiting 3 capas, warm-up)
- Envío de comentarios en Instagram (Phase 5)
- Inbox monitoring automático con Celery Beat (cada 5 min) que clasifica respuestas (positiva, negativa, pregunta, spam)
- Follow-ups automáticos cada 1 hora
- Dashboard con 7 módulos (Pipeline, DMs, Comentarios, Clientes, Config, Logs, Health)
- Auth JWT con roles
- Notificaciones in-app + Slack
- Recuperación ante caídas + idempotencia
- CI/CD con GitHub Actions

### Contexto Competitivo — Por qué construimos esto

Existe una herramienta llamada ColdDMs que cobra $99/mes y ofrece: scraping de leads por seguidores/hashtags/keywords, envío automatizado de DMs con follow-ups, unibox para gestionar respuestas, CRM básico tipo Kanban, y multi-cuenta. Funciona como extensión de Chrome (necesita computadora encendida con Chrome abierto).

**Lo que nosotros YA les ganamos:**
- Ellos scrapean en bruto y filtran solo por keywords en bio. Nosotros hacemos smart over-scrape + scoring con IA + research automático por lead. DMs infinitamente más personalizados.
- Ellos dependen de extensión de Chrome (usuario necesita PC encendida). Nosotros corremos en servidor con Docker — 24/7 sin intervención humana.
- Ellos no tienen comentarios en posts. Nosotros tenemos Phase 5 completa — canal de outreach adicional.
- Ellos no tienen research de leads. Nosotros investigamos cada lead con Gemini antes de escribirle.
- Ellos no tienen anti-detección avanzada (8 categorías, 5 perfiles GPU). Nosotros sí.

**Lo que ellos tienen y nosotros NO (lo que vamos a construir ahora):**
- Unibox (inbox unificado para gestionar conversaciones) — PERO el de ellos es estático, el usuario lee y responde manual. El nuestro tendrá sugerencias de respuesta con IA.
- CRM Kanban visual — PERO el de ellos es columnas básicas sin inteligencia. El nuestro tendrá scoring dinámico de conversación que re-puntúa leads automáticamente según lo que responden.
- Filtro por keywords en bio como paso pre-scraping — Sencillo pero útil, ahorra costos de API.
- Horarios de envío configurables por campaña con zona horaria.

**La meta: que cada feature nueva no solo iguale lo de ColdDMs sino que lo supere con IA.**

---

## QUÉ CONSTRUIR

Necesito que implementes 4 features nuevas. Cada una debe integrarse con la arquitectura existente (FastAPI + SQLAlchemy + el dashboard HTML/JS existente). NO crear proyecto nuevo, agregar a lo que ya existe.

---

### FEATURE 1: UNIBOX — Inbox Unificado con Respuesta Asistida por IA

**Qué es:** Una vista unificada donde el usuario ve TODAS las conversaciones de TODAS las cuentas de Instagram en un solo lugar, puede leer el historial completo de cada conversación, responder directamente desde ahí, y recibir sugerencias de respuesta generadas por Claude.

**Diferencial competitivo:** ColdDMs tiene un unibox estático donde el usuario lee y responde manual. El nuestro tiene IA integrada: cuando llega una respuesta, Claude analiza el contexto completo de la conversación y sugiere respuestas. El usuario solo aprueba o edita. Esto reduce el tiempo de respuesta de minutos a segundos y es lo que cierra ventas.

**Backend:**

1. Crear `app/services/unibox_service.py`:
   - `get_all_conversations(filters)` — Trae todas las conversaciones de todas las cuentas, con paginación y filtros opcionales:
     - Por campaña
     - Por cuenta de Instagram
     - Por estado (sin responder, respondido, pendiente)
     - Por clasificación (positiva, negativa, pregunta, spam)
     - Por CRM stage (new, interested, call_scheduled, etc.)
     - Por búsqueda de texto
     - Ordenar por: más reciente, no leídos primero, score más alto primero
   - `get_conversation_thread(lead_id)` — Historial completo de mensajes con un lead específico (DM inicial, respuestas, follow-ups), incluyendo info del lead (bio, score, research, crm_stage)
   - `send_reply(lead_id, account_id, message)` — Enviar respuesta directa a un lead usando instagrapi, a través de la cuenta asignada. Debe respetar los mismos delays anti-detección del dm_sender_service
   - `generate_reply_suggestion(lead_id)` — Llama a Claude API con:
     - Conversación completa (todos los mensajes enviados y recibidos)
     - Info del lead (bio, score, research data si existe)
     - Contexto de la campaña (qué servicio/producto se ofrece)
     - Prompt del cliente (si tiene prompts personalizados en la tabla de clientes)
     - Genera 3 sugerencias con intenciones diferentes:
       1. **Cerrar:** Intenta agendar llamada o cerrar venta directa
       2. **Nutrir:** Responde la pregunta y mantiene la conversación
       3. **Calificar:** Hace preguntas para entender si el lead es buen fit
   - `auto_suggest_on_new_reply(lead_id)` — Se llama automáticamente cuando inbox_service detecta una nueva respuesta (integrar con inbox_tasks.py). Pre-genera las sugerencias y las almacena en BD para que cuando el usuario abra la conversación ya estén listas (no tenga que esperar la llamada a Claude)
   - `mark_as_read(lead_id)` / `mark_as_starred(lead_id)` — Gestión de estado

2. Crear `app/routers/unibox.py`:
   - `GET /api/v1/unibox/conversations` — Lista con filtros y paginación
   - `GET /api/v1/unibox/conversations/{lead_id}/thread` — Historial de conversación
   - `POST /api/v1/unibox/conversations/{lead_id}/reply` — Enviar respuesta
   - `GET /api/v1/unibox/conversations/{lead_id}/suggestions` — Obtener sugerencias pre-generadas
   - `POST /api/v1/unibox/conversations/{lead_id}/suggest` — Forzar regeneración de sugerencias
   - `PATCH /api/v1/unibox/conversations/{lead_id}` — Actualizar estado (leído, starred, clasificación)
   - `GET /api/v1/unibox/stats` — Métricas: total no leídos, por clasificación, tiempo promedio de respuesta
   - Todos protegidos con JWT, roles admin y manager pueden responder, viewer solo lee

3. Integración con inbox_tasks.py:
   - Cuando Celery Beat detecta una nueva respuesta en el inbox check cada 5 min, además de clasificarla, llamar a `auto_suggest_on_new_reply()` para pre-generar sugerencias
   - Almacenar las sugerencias en una tabla `reply_suggestions` (id, lead_id, suggestions JSON, generated_at, used boolean)

4. Modelos — agregar a los modelos existentes:
   - Campo `is_read` (boolean, default False) en la tabla de mensajes/respuestas
   - Campo `is_starred` (boolean, default False) para marcar conversaciones importantes
   - Tabla `reply_suggestions` (id, lead_id, suggestions JSONB, generated_at, was_used boolean)
   - Campo `crm_stage` (enum) para la Feature 2

**Frontend — nuevo tab "Unibox" en el dashboard:**

- Layout de 2 paneles: lista de conversaciones a la izquierda (con avatar/iniciales, username, preview del último mensaje, badge de no leído, timestamp, badge de score con color, badge de crm_stage), hilo de conversación a la derecha
- Barra de filtros arriba: dropdown campaña, dropdown cuenta, dropdown estado, dropdown clasificación, búsqueda por texto
- Ordenamiento: más reciente, no leídos primero, score más alto
- En el hilo: burbujas de chat estilo WhatsApp (mensajes enviados a la derecha en amber, respuestas del lead a la izquierda en gris oscuro)
- Header del hilo con info del lead: username, score, crm_stage, botón para ver perfil completo
- Input de respuesta abajo con botón de enviar
- **Sección de sugerencias IA** arriba del input: si hay sugerencias pre-generadas, mostrar 3 cards clickeables con el label (Cerrar/Nutrir/Calificar) y preview del mensaje. Al clickear una, se carga en el input para editar o enviar directo. Botón de "regenerar sugerencias" si ninguna sirve
- Si no hay sugerencias pre-generadas, mostrar botón "Generar sugerencias con IA" que llama al endpoint
- Badge con contador de no leídos en el sidebar (actualizar con poll cada 30s o WebSocket si ya existe)
- Indicador de cuál cuenta de IG se está usando para responder
- Seguir el estilo visual existente del dashboard (tema oscuro, acentos amber, font Space Grotesk)

---

### FEATURE 2: CRM KANBAN — Pipeline Visual con Scoring Dinámico

**Qué es:** Un tablero Kanban tipo Trello donde el usuario arrastra leads entre columnas que representan etapas del funnel de ventas, con la diferencia de que el score de cada lead se actualiza automáticamente conforme avanza la conversación.

**Diferencial competitivo:** ColdDMs tiene un CRM con columnas básicas estáticas. El nuestro tiene scoring dinámico de conversación: cuando un lead responde, Claude analiza el mensaje y ajusta el score automáticamente. Un lead que pregunta precio sube de score, uno que dice "no gracias" baja. Esto prioriza automáticamente a quién atender primero — el usuario abre el Unibox y los leads más calientes están arriba.

**Backend:**

1. Crear `app/services/crm_service.py`:
   - `get_pipeline_board(campaign_id?)` — Trae todos los leads organizados por etapa, ordenados por score dentro de cada columna (más alto primero)
   - `move_lead(lead_id, new_stage)` — Mueve un lead a otra etapa. Loggear el movimiento en audit log
   - `get_lead_detail(lead_id)` — Info completa del lead: bio, score actual, historial de score (cómo ha cambiado), research, historial de DMs, respuestas, follow-ups, notas
   - `add_note(lead_id, note)` — Agregar nota manual a un lead (con user_id de quién la escribió)
   - `auto_classify_stage(lead_id)` — Lógica automática:
     - DM enviado → `contacted`
     - Respuesta recibida → `replied`
     - Respuesta clasificada como positiva → `interested`
     - Lead menciona "precio", "costo", "cuánto", "agendar", "llamada" → `interested`
     - Lead menciona "no gracias", "no me interesa", "no" → `closed_lost`
     - Las etapas `call_scheduled` y `closed_won` son solo manuales (drag & drop)
   - `update_conversation_score(lead_id)` — **SCORING DINÁMICO:** Cuando se recibe una nueva respuesta del lead, llamar a Claude con el mensaje y el contexto para que evalúe la intención de compra en una escala de -20 a +20 puntos. Sumar/restar al score existente del lead. Ejemplos:
     - "¿Cuánto cuesta?" → +15 (alta intención)
     - "Cuéntame más" → +10
     - "Interesante, pero ahora no" → -5
     - "No me interesa" → -20
     - Spam o irrelevante → -10
     - Almacenar el historial de cambios de score en una tabla `score_history` (lead_id, old_score, new_score, reason, timestamp)

2. Crear `app/routers/crm.py`:
   - `GET /api/v1/crm/board` — Tablero completo con filtros por campaña
   - `GET /api/v1/crm/board/stats` — Métricas por etapa: cantidad de leads, score promedio, valor estimado
   - `PATCH /api/v1/crm/leads/{lead_id}/stage` — Mover lead de etapa
   - `GET /api/v1/crm/leads/{lead_id}` — Detalle del lead con historial de score
   - `POST /api/v1/crm/leads/{lead_id}/notes` — Agregar nota
   - `GET /api/v1/crm/leads/{lead_id}/score-history` — Historial de cambios de score
   - Protegido con JWT

3. Modelos:
   - Agregar campo `crm_stage` al modelo de lead con enum: `new`, `contacted`, `replied`, `interested`, `call_scheduled`, `closed_won`, `closed_lost`
   - Agregar tabla `lead_notes` (id, lead_id, user_id, content, created_at)
   - Agregar tabla `score_history` (id, lead_id, old_score, new_score, delta, reason, created_at)
   - Migración con Alembic

4. Integración automática:
   - Cuando dm_sender_service envía un DM → llamar `auto_classify_stage` → lead pasa a `contacted`
   - Cuando inbox_service detecta respuesta → llamar `auto_classify_stage` + `update_conversation_score` → lead se mueve y score se actualiza
   - Cuando inbox_service clasifica como positiva → lead pasa a `interested`
   - Las etapas `call_scheduled` y `closed_won` son manuales (drag & drop)
   - Integrar `update_conversation_score` en inbox_tasks.py junto con `auto_suggest_on_new_reply` de la Feature 1

**Frontend — nuevo tab "CRM" en el dashboard:**

- Tablero Kanban con columnas: Nuevo → Contactado → Respondió → Interesado → Llamada Agendada → Cerrado (Ganado) → Cerrado (Perdido)
- Cards de lead con: avatar (o iniciales con color basado en score), username, score actual (badge de color: verde >70, amber 40-70, rojo <40), indicador de tendencia de score (↑ subió, ↓ bajó, = igual), preview del último mensaje, timestamp
- Drag & drop entre columnas (usar HTML5 Drag and Drop API, no librerías externas)
- Al clickear un card → panel lateral con detalle completo:
  - Header: username, avatar, score con gráfico mini de evolución
  - Bio de Instagram
  - Research data (si existe)
  - Historial de conversación (mensajes enviados y respuestas)
  - Historial de score (timeline de cambios con razón)
  - Notas del equipo
  - Botón para abrir en Unibox (link directo a la conversación)
- Contador de leads por columna + score promedio por columna
- Filtro por campaña
- Barra superior con métricas: total leads, tasa de respuesta, tasa de interés, leads cerrados
- Seguir el estilo visual del dashboard existente

---

### FEATURE 3: FILTRO PRE-SCRAPING POR KEYWORDS EN BIO

**Qué es:** Una capa de filtrado rápido que descarta leads antes de gastar tokens de IA en el scoring. El usuario define keywords que DEBEN aparecer en la bio del lead para ser considerado.

**Backend:**

1. Modificar `app/services/apify_service.py`:
   - Agregar parámetro `bio_keywords` (lista de strings) a la función de scraping
   - Después de recibir los leads de Apify y antes de pasarlos al scoring, filtrar: si `bio_keywords` tiene valores, solo mantener leads cuya bio contenga AL MENOS UNA de las keywords (case-insensitive)
   - Loggear cuántos leads fueron descartados por este filtro
   - Este filtro se aplica ANTES del scoring con Claude (ahorra costos de API)

2. Modificar los endpoints de campaña:
   - Agregar campo `bio_keywords` al modelo de campaña (JSON array)
   - Pasar los keywords al pipeline cuando se ejecuta el scraping

**Frontend:**

- En la creación/edición de campaña, agregar sección "Filtro por Keywords en Bio"
- Input tipo tag: el usuario escribe una keyword y presiona Enter, se agrega como un chip/badge
- Botón X en cada chip para eliminar
- Texto de ayuda: "Solo se procesarán leads que tengan al menos una de estas palabras en su biografía de Instagram. Déjalo vacío para procesar todos."
- Ubicarlo entre la configuración de scraping y el botón de ejecutar pipeline

---

### FEATURE 4: HORARIOS DE TRABAJO POR CAMPAÑA CON ZONA HORARIA

**Qué es:** Permitir que cada campaña tenga definido un rango de horas en las que se pueden enviar DMs, y en qué zona horaria se calculan esas horas.

**Backend:**

1. Modificar el modelo de campaña:
   - Agregar campo `sending_hours_start` (time, default 09:00)
   - Agregar campo `sending_hours_end` (time, default 21:00)
   - Agregar campo `sending_timezone` (string, default "America/Caracas")
   - Migración con Alembic

2. Modificar `app/services/dm_sender_service.py`:
   - Antes de enviar cada DM, verificar si la hora actual (convertida a la timezone de la campaña) está dentro del rango permitido
   - Si no está en horario → no enviar, re-encolar la tarea para el próximo slot de horario disponible
   - Loggear cuando se pospone un envío por horario

**Frontend:**

- En la creación/edición de campaña, agregar sección "Horario de Envío"
- Dos selectores de hora: "Desde" y "Hasta" (dropdowns con intervalos de 30 min)
- Dropdown de zona horaria con las zonas más comunes de LATAM, US y Europa
- Preview: "Los DMs se enviarán entre las 9:00 AM y 9:00 PM (hora de Caracas)"
- Ubicarlo en la configuración de la campaña, después del nombre y descripción

---

## INSTRUCCIONES GENERALES

1. **No romper nada existente.** Todo lo nuevo se agrega, no se reemplaza.
2. **Migraciones Alembic** para cada cambio de modelo. Generarlas con `alembic revision --autogenerate`.
3. **Tests** — crear tests para cada servicio nuevo. Mínimo: test del unibox_service, test del crm_service, test del filtro de keywords, test de la lógica de horarios, test del scoring dinámico.
4. **El dashboard es un SPA en vanilla JS** dentro de `app/static/dashboard.html`. Los nuevos tabs (Unibox, CRM) se agregan ahí siguiendo el patrón existente de navegación por sidebar.
5. **Registrar los routers** en `app/main.py`.
6. **Mantener el estilo visual:** tema oscuro, sidebar negro, acentos amber (#e2a84b), font Space Grotesk, botones negros, terminal dark para logs.
7. **Orden de implementación:** Feature 1 (Unibox) → Feature 2 (CRM Kanban) → Feature 3 (Keywords en bio) → Feature 4 (Horarios). El Unibox es lo que cierra ventas, va primero. El CRM es lo que el cliente ve y donde siente el valor, va segundo. Keywords y horarios son optimización, van al final.

## RECORDATORIO: VENTAJAS COMPETITIVAS A EXPLOTAR

Cada feature que construyas debe ser SUPERIOR a lo que ofrece ColdDMs ($99/mes):

- **Unibox:** El de ellos es estático (leer y responder manual). El nuestro pre-genera sugerencias de IA automáticamente en cada respuesta nueva. El usuario abre la conversación y ya tiene 3 opciones listas. Eso es el diferencial #1.
- **CRM:** El de ellos es columnas estáticas. El nuestro tiene scoring dinámico — el score cambia con cada interacción y los leads se reordenan solos por temperatura. El usuario siempre ve los leads más calientes primero.
- **Servidor vs Extensión de Chrome:** Ellos necesitan PC encendida con Chrome abierto. Nuestro sistema corre en Docker 24/7. Esto ya lo tenemos, pero el Unibox y CRM deben diseñarse asumiendo que el sistema trabaja solo y el usuario solo entra a gestionar.
- **Comentarios en posts:** Ellos no los tienen. Nosotros sí (Phase 5). Los leads que reciben comentario + DM tienen mayor tasa de respuesta. Integrar esto en el CRM — que se vea en el historial del lead si también recibió comentario.
- **Research automático:** Ellos no lo tienen. Mostrar la research data del lead de forma prominente en el Unibox y en el CRM para que el usuario tenga contexto completo al responder.

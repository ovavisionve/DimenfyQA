# IG DM Engine — Guía Paso a Paso para Levantar el Proyecto Real

> Última actualización: 7 de marzo de 2026
>
> Esta guía asume que partes desde CERO en una máquina limpia.
> Cada paso incluye QUÉ hacer, POR QUÉ y CÓMO verificar que salió bien.

---

## Índice

1. [Requisitos previos (instalar en tu máquina)](#1-requisitos-previos)
2. [Obtener las API keys (dónde, cómo, cuánto cuesta)](#2-obtener-las-api-keys)
3. [Configurar el entorno (.env)](#3-configurar-el-entorno)
4. [Levantar la infraestructura con Docker](#4-levantar-la-infraestructura-con-docker)
5. [Crear la base de datos (migraciones)](#5-crear-la-base-de-datos)
6. [Verificar que la API funciona](#6-verificar-que-la-api-funciona)
7. [Probar cada servicio individualmente](#7-probar-cada-servicio-individualmente)
8. [Ejecutar el pipeline completo (primera campaña real)](#8-ejecutar-el-pipeline-completo)
9. [Exportar resultados](#9-exportar-resultados)
10. [Troubleshooting (problemas comunes)](#10-troubleshooting)
11. [Desarrollo local sin Docker (alternativa)](#11-desarrollo-local-sin-docker)

---

## 1. Requisitos previos

### 1.1 Docker Desktop

**Qué es:** Docker permite correr PostgreSQL, Redis, la API y el Worker Celery en contenedores aislados sin instalar nada más en tu máquina.

**Cómo instalarlo:**

```bash
# macOS — con Homebrew
brew install --cask docker

# Windows — descargar el instalador
# Ir a: https://www.docker.com/products/docker-desktop/
# Descargar > Instalar > Reiniciar

# Linux (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install docker.io docker-compose-plugin
sudo systemctl start docker
sudo usermod -aG docker $USER  # para no usar sudo cada vez
# Cierra sesión y vuelve a abrir
```

**Verificar que está instalado:**

```bash
docker --version
# Esperado: Docker version 24.x o superior

docker compose version
# Esperado: Docker Compose version v2.x
```

**Si algo falla:**
- macOS: Abre Docker Desktop desde Applications, espera a que el icono de la ballena en la barra de menú deje de moverse
- Windows: Asegúrate de tener WSL2 habilitado (Docker Desktop te guía)
- Linux: Si dice "permission denied", cierra y vuelve a abrir la terminal después del `usermod`

### 1.2 Git

```bash
git --version
# Si no está: brew install git (mac) / sudo apt install git (linux)
```

### 1.3 Python 3.11+ (solo si quieres desarrollo local sin Docker)

```bash
python3 --version
# Necesitas 3.11 o superior

# Si no lo tienes:
# macOS: brew install python@3.11
# Ubuntu: sudo apt install python3.11 python3.11-venv
```

### 1.4 curl o Postman (para probar la API)

```bash
curl --version
# Viene preinstalado en macOS y la mayoría de Linux
# Windows: instala desde https://curl.se/windows/ o usa Postman
```

**Alternativa recomendada:** Usa la interfaz Swagger que viene incluida. Cuando la API esté corriendo, abre `http://localhost:8000/docs` en tu navegador — te deja probar todos los endpoints sin curl.

---

## 2. Obtener las API keys

Necesitas 3 API keys. Aquí te explico dónde obtener cada una, cuánto cuesta, y qué plan elegir.

### 2.1 Anthropic (Claude API) — Para scoring y DMs

**Para qué se usa:** Calificar leads (score 0-100) y generar DMs personalizados.

**Pasos:**
1. Ve a [console.anthropic.com](https://console.anthropic.com/)
2. Click en "Sign Up" — puedes usar Google o email
3. Confirma tu email
4. Ve a "API Keys" en el menú lateral izquierdo
5. Click en "Create Key"
6. Ponle un nombre descriptivo: `ig-dm-engine-dev`
7. **Copia la key inmediatamente** — solo se muestra una vez
8. Se ve así: `sk-ant-api03-xxxxxxxxxxxxxxxx`

**Configurar créditos:**
1. Ve a "Billing" en el menú lateral
2. Click en "Add Credits" o "Add Payment Method"
3. Para empezar: agrega $5-10 USD (suficiente para ~5,000 leads)
4. El modelo que usamos es `claude-sonnet-4-5-20250514`

**Costos estimados:**
| Operación | Costo aprox por lead |
|---|---|
| Scoring (1 call) | ~$0.003 |
| DM Variant A (1 call) | ~$0.005 |
| DM Variant B (1 call) | ~$0.005 |
| **Total por lead calificado** | **~$0.013** |
| **800 leads scrapeados → ~200 calificados** | **~$5.00** |

**Verificar que funciona:**
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: TU_KEY_AQUI" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-5-20250514","max_tokens":50,"messages":[{"role":"user","content":"Di hola"}]}'
```
Si responde con JSON que contiene `"content"`, tu key funciona.

### 2.2 Perplexity API — Para research de leads

**Para qué se usa:** Investigar quién es cada lead calificado (score >= 60) antes de escribir el DM.

**Pasos:**
1. Ve a [perplexity.ai](https://www.perplexity.ai/)
2. Crea una cuenta (Google, Apple, o email)
3. Ve a [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api)
4. Click en "Generate" para crear una API key
5. **Copia la key** — se ve así: `pplx-xxxxxxxxxxxxxxxx`

**Créditos:**
1. En la misma página de API, click en "Add Credits"
2. Empieza con $5 USD — suficiente para ~500 research queries

**Costos estimados:**
| Modelo | Input/1M tokens | Output/1M tokens |
|---|---|---|
| `sonar` | ~$1.00 | ~$1.00 |
| **Por lead (1 query)** | **~$0.005** | |
| **200 leads calificados** | **~$1.00** | |

**Verificar que funciona:**
```bash
curl https://api.perplexity.ai/chat/completions \
  -H "Authorization: Bearer TU_KEY_AQUI" \
  -H "Content-Type: application/json" \
  -d '{"model":"sonar","messages":[{"role":"user","content":"Quién es Gary Vaynerchuk?"}]}'
```

### 2.3 Apify API — Para scraping de Instagram

**Para qué se usa:** Extraer followers, comentarios y perfiles de cuentas de Instagram.

**Pasos:**
1. Ve a [apify.com](https://apify.com/)
2. Click en "Sign Up" — Google o email
3. Una vez dentro, ve a [console.apify.com/settings/integrations](https://console.apify.com/settings/integrations)
4. Tu API token aparece ahí — **cópialo**
5. Se ve así: `apify_api_xxxxxxxxxxxxxxxx`

**Plan gratuito vs pago:**
- **Free:** 5 USD en créditos por mes + $5 de bienvenida
- Suficiente para ~500-1,000 perfiles al mes
- Si necesitas más: el plan Personal ($49/mes) incluye 100 USD en créditos

**Los 3 actors que usa el proyecto:**
1. `louisdeconinck~instagram-following-scraper` — Followers de una cuenta
2. `apidojo~instagram-comments-scraper` — Comentarios de un post
3. `danek~instagram-profiles-scraper-ppr` — Detalles de perfiles

**IMPORTANTE:** La primera vez que uses cada actor, Apify te pide "activarlo" en su marketplace. Ve a cada uno y dale click en "Try for free":
- [Instagram Following Scraper](https://apify.com/louisdeconinck/instagram-following-scraper)
- [Instagram Comments Scraper](https://apify.com/apidojo/instagram-comments-scraper)
- [Instagram Profiles Scraper](https://apify.com/danek/instagram-profiles-scraper-ppr)

**Verificar que funciona:**
```bash
curl "https://api.apify.com/v2/acts?limit=1" \
  -H "Authorization: Bearer TU_TOKEN_AQUI"
```
Si responde con JSON que contiene `"data"`, tu token funciona.

---

## 3. Configurar el entorno

### 3.1 Clonar el repositorio (si aún no lo tienes)

```bash
git clone <URL_DEL_REPO> ig-dm-engine
cd ig-dm-engine
```

### 3.2 Crear el archivo .env

```bash
cp .env.example .env
```

### 3.3 Editar .env con tus keys reales

Abre `.env` con tu editor preferido:

```bash
# Con VS Code
code .env

# Con nano (terminal)
nano .env

# Con vim
vim .env
```

Reemplaza los valores placeholder con tus keys reales:

```env
# Base de datos — NO CAMBIAR estos valores (Docker los configura automáticamente)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/ig_dm_engine

# Redis — NO CAMBIAR
REDIS_URL=redis://redis:6379/0

# ===== ESTAS SÍ LAS CAMBIAS =====

# Anthropic (Claude API) — la key que obtuviste en el paso 2.1
ANTHROPIC_API_KEY=sk-ant-api03-TU-KEY-REAL-AQUI

# Perplexity — la key que obtuviste en el paso 2.2
PERPLEXITY_API_KEY=pplx-TU-KEY-REAL-AQUI

# Apify — el token que obtuviste en el paso 2.3
APIFY_API_TOKEN=apify_api_TU-TOKEN-REAL-AQUI

# App — puedes dejar estos valores por defecto
APP_ENV=development
LOG_LEVEL=INFO
DEFAULT_SCORE_THRESHOLD=60
RESEARCH_SCORE_THRESHOLD=60
DM_SCORE_THRESHOLD=70
```

**IMPORTANTE sobre DATABASE_URL y REDIS_URL:**
- Si corres con **Docker Compose**: usa `db` y `redis` como hosts (son los nombres de los servicios en docker-compose.yml)
- Si corres **localmente sin Docker**: usa `localhost` como host

```env
# Para Docker Compose (default)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/ig_dm_engine
REDIS_URL=redis://redis:6379/0

# Para desarrollo local (sin Docker para la API)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ig_dm_engine
REDIS_URL=redis://localhost:6379/0
```

### 3.4 Verificar que .env no se sube a git

```bash
cat .gitignore | grep .env
# Debe mostrar: .env
# Si NO aparece, agrégalo:
echo ".env" >> .gitignore
```

---

## 4. Levantar la infraestructura con Docker

### 4.1 Asegúrate de que Docker está corriendo

```bash
docker info
# Si da error "Cannot connect to the Docker daemon":
# - macOS/Windows: Abre Docker Desktop
# - Linux: sudo systemctl start docker
```

### 4.2 Construir y levantar todos los servicios

```bash
# Desde la raíz del proyecto (donde está docker-compose.yml)
docker compose up --build
```

**Qué hace este comando:**
1. Descarga las imágenes de PostgreSQL 16 y Redis 7 (primera vez, ~200MB)
2. Construye la imagen de la API (instala Python + dependencias)
3. Levanta 4 contenedores:
   - `db` — PostgreSQL en puerto 5432
   - `redis` — Redis en puerto 6379
   - `api` — FastAPI en puerto 8000
   - `worker` — Celery worker (4 procesos concurrentes)

**Qué verás en la terminal:**

```
✔ Container ig-dm-engine-db-1      Created
✔ Container ig-dm-engine-redis-1   Created
✔ Container ig-dm-engine-api-1     Created
✔ Container ig-dm-engine-worker-1  Created
```

Luego los logs de cada servicio. Busca estas líneas que confirman que todo está bien:

```
db-1      | database system is ready to accept connections
redis-1   | Ready to accept connections
api-1     | Uvicorn running on http://0.0.0.0:8000
worker-1  | celery@xxxxxx ready.
```

### 4.3 Correr en background (opcional)

Si no quieres ver los logs todo el tiempo:

```bash
# Levantar en background
docker compose up --build -d

# Ver logs cuando quieras
docker compose logs -f          # todos los servicios
docker compose logs -f api      # solo la API
docker compose logs -f worker   # solo el worker

# Ver qué contenedores están corriendo
docker compose ps
```

### 4.4 Parar todo

```bash
# Parar pero mantener datos de DB
docker compose down

# Parar Y borrar datos de DB (empezar limpio)
docker compose down -v
```

---

## 5. Crear la base de datos

La API y el Worker ya están corriendo, pero las tablas de la DB aún no existen. Hay que crearlas con Alembic (herramienta de migraciones).

### 5.1 Generar la migración inicial

```bash
# Ejecutar dentro del contenedor de la API
docker compose exec api alembic revision --autogenerate -m "initial tables"
```

**Qué hace:** Lee los modelos SQLAlchemy (`app/models/*.py`) y genera un script de migración en `alembic/versions/` que crea las tablas: `clients`, `campaigns`, `leads`, `messages`, `scrape_jobs`.

**Resultado esperado:**
```
INFO  [alembic.autogenerate.compare] Detected added table 'clients'
INFO  [alembic.autogenerate.compare] Detected added table 'campaigns'
INFO  [alembic.autogenerate.compare] Detected added table 'leads'
...
Generating /app/alembic/versions/xxxx_initial_tables.py ... done
```

### 5.2 Aplicar la migración

```bash
docker compose exec api alembic upgrade head
```

**Qué hace:** Ejecuta el script de migración y crea las tablas reales en PostgreSQL.

**Resultado esperado:**
```
INFO  [alembic.runtime.migration] Running upgrade  -> xxxx, initial tables
```

### 5.3 Verificar que las tablas se crearon

```bash
# Conectarse a PostgreSQL dentro del contenedor
docker compose exec db psql -U postgres -d ig_dm_engine -c "\dt"
```

**Resultado esperado:**
```
          List of relations
 Schema |    Name     | Type  |  Owner
--------+-------------+-------+----------
 public | alembic_version | table | postgres
 public | campaigns   | table | postgres
 public | clients     | table | postgres
 public | leads       | table | postgres
 public | messages    | table | postgres
 public | scrape_jobs | table | postgres
```

Si ves las 5 tablas + `alembic_version`, la DB está lista.

### 5.4 Cargar datos de prueba (opcional)

```bash
docker compose exec api python scripts/seed_db.py
```

Esto crea: 1 cliente de prueba, 1 campaña y 3 leads de ejemplo. Útil para verificar que los endpoints funcionan antes de probar con datos reales.

---

## 6. Verificar que la API funciona

### 6.1 Health check

```bash
curl http://localhost:8000/health
```

**Respuesta esperada:**
```json
{"status": "healthy", "version": "0.1.0"}
```

### 6.2 Abrir la documentación interactiva

Abre en tu navegador: **http://localhost:8000/docs**

Verás la interfaz Swagger con todos los endpoints disponibles. Desde aquí puedes probar todo sin necesidad de curl.

### 6.3 Verificar los endpoints principales

```bash
# Listar clientes (debería estar vacío o con el seed)
curl http://localhost:8000/api/v1/clients/

# Listar campañas
curl http://localhost:8000/api/v1/campaigns/
```

---

## 7. Probar cada servicio individualmente

Antes de correr el pipeline completo, prueba cada servicio por separado para identificar problemas.

### 7.1 Probar Claude (Scoring)

Este test verifica que tu API key de Anthropic funciona y que el scoring devuelve JSON válido.

```bash
# Entrar al contenedor de la API
docker compose exec api python3 -c "
from app.services.scoring_service import ScoringService

service = ScoringService()
result = service.score_lead({
    'ig_username': 'mariacoach',
    'ig_full_name': 'María García',
    'ig_bio': 'Coach de negocios | Ayudo emprendedoras a escalar a 6 cifras | +200 alumnas | Programa online',
    'ig_website': 'https://mariacoach.com',
    'ig_category': 'Business',
    'ig_follower_count': 15000,
    'ig_following_count': 800,
    'ig_is_private': False,
})
print(f'Score: {result[\"score\"]}')
print(f'Reason: {result[\"reason\"]}')
print(f'Category: {result[\"category\"]}')
"
```

**Resultado esperado:** Score entre 70-95, categoría "coach", y una razón coherente.

**Si falla:**
- `AuthenticationError` → Tu ANTHROPIC_API_KEY es incorrecta o no tiene créditos
- `APIConnectionError` → Problema de red. ¿Estás detrás de un proxy?
- `json.JSONDecodeError` → Claude devolvió texto en vez de JSON. Puede pasar ocasionalmente, el retry del pipeline lo maneja

### 7.2 Probar Perplexity (Research)

```bash
docker compose exec api python3 -c "
import asyncio
from app.services.research_service import ResearchService

service = ResearchService()
result = asyncio.run(service.research_lead({
    'ig_username': 'garyvee',
    'ig_full_name': 'Gary Vaynerchuk',
    'ig_website': 'https://garyvaynerchuk.com',
    'ig_bio': 'CEO VaynerMedia',
    'lead_category': 'agency',
}))
print(result[:300])
"
```

**Resultado esperado:** Un párrafo con información sobre Gary Vee.

**Si falla:**
- `401 Unauthorized` → Tu PERPLEXITY_API_KEY es incorrecta
- `429 Too Many Requests` → Llegaste al límite de rate. Espera 1 minuto

### 7.3 Probar Apify (Scraping)

Este test es más delicado porque consume créditos de Apify. Usa un target pequeño.

```bash
docker compose exec api python3 -c "
import asyncio
from app.services.apify_service import ApifyService

service = ApifyService()
# Scraping síncrono de UN solo perfil (consume mínimos créditos)
result = asyncio.run(service.scrape_profiles_sync(['garyvee']))
print(f'Perfiles obtenidos: {len(result)}')
if result:
    p = result[0]
    print(f'Username: {p.get(\"username\")}')
    print(f'Followers: {p.get(\"followersCount\")}')
    print(f'Bio: {p.get(\"biography\", \"\")[:100]}')
"
```

**Resultado esperado:** Datos del perfil de @garyvee.

**Si falla:**
- `401` → Tu APIFY_API_TOKEN es incorrecto
- `404` → No has activado el actor en el marketplace de Apify (ver paso 2.3)
- `402 Payment Required` → Se acabaron los créditos gratuitos de Apify

### 7.4 Probar Claude (Copywriting)

```bash
docker compose exec api python3 -c "
from app.services.copywriting_service import CopywritingService

service = CopywritingService()
dm = service.generate_dm(
    lead_data={
        'ig_username': 'mariacoach',
        'ig_full_name': 'María García',
        'ig_bio_clean': 'Coach de negocios. Ayudo emprendedoras a escalar a 6 cifras. Mas de 200 alumnas. Programa online.',
        'lead_category': 'coach',
        'ig_website': 'https://mariacoach.com',
        'research_data': 'María García es una coach de negocios con sede en Miami. Tiene un programa online llamado Escala 6 que ha graduado más de 200 emprendedoras. Recientemente lanzó un podcast sobre emprendimiento femenino.',
    },
    client_config={
        'business_type': 'B2B automation agency',
        'service_description': 'Automatización de generación de leads y DMs para coaches y consultores que quieren escalar sin contratar más equipo.',
    }
)
print('=== DM GENERADO ===')
print(dm)
print()
print(f'Longitud: {len(dm)} caracteres')
print(f'Oraciones: {dm.count(\".\")} aprox')
"
```

**Resultado esperado:** Un DM de 4-5 oraciones, tono natural, sin emojis, sin palabras como "journey" o "game-changer".

---

## 8. Ejecutar el pipeline completo

### 8.1 Crear un cliente

```bash
curl -X POST http://localhost:8000/api/v1/clients/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Mi Agencia Test",
    "business_type": "B2B automation agency",
    "settings": {
      "service_description": "Automatización de generación de leads y DMs para coaches y consultores que quieren escalar sin contratar más equipo."
    }
  }'
```

**Guarda el `id` que te devuelve** — lo necesitas para el siguiente paso. Se ve así:
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "name": "Mi Agencia Test", ...}
```

### 8.2 Crear una campaña

```bash
# Reemplaza CLIENT_ID con el id del paso anterior
curl -X POST http://localhost:8000/api/v1/campaigns/ \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "CLIENT_ID_AQUI",
    "name": "Test - Followers de garyvee",
    "source_type": "followers",
    "source_value": "garyvee"
  }'
```

**Tipos de source_type disponibles:**
| source_type | source_value | Qué hace |
|---|---|---|
| `followers` | Username sin @ | Scrape followers de esa cuenta |
| `comments` | URL del post | Scrape comentarios de ese post |
| `profiles` | Username sin @ | Scrape info de un perfil específico |

**Guarda el `id` de la campaña** para el siguiente paso.

### 8.3 Iniciar el pipeline

```bash
# Reemplaza CAMPAIGN_ID con el id de la campaña
curl -X POST http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID_AQUI/start
```

**Qué sucede ahora (automáticamente):**

```
FASE 1 — SCRAPE (~30-120 seg según cantidad de followers)
├── Apify descarga la lista de followers
├── Filtra cuentas privadas
├── Guarda en DB con deduplicación
└── Resultado: lead_ids[] de todos los leads scrapeados

FASE 2 — SCORE (~2-5 seg por lead)
├── Claude analiza cada lead
├── Asigna score 0-100
├── Clasifica: coach, ecommerce, saas, agency, creator, local_business, other
└── Resultado: scored_lead_ids[] de leads que pasaron el threshold (60+)

FASE 3 — RESEARCH (~3-5 seg por lead)
├── Perplexity investiga cada lead con score >= 60
├── Busca info del negocio, logros recientes, datos personalizables
└── Resultado: researched_lead_ids[]

FASE 4 — WRITE DMs (~3-5 seg por lead)
├── Claude genera DM personalizado (Variante A)
├── Claude genera DM alternativo (Variante B) para A/B testing
└── Resultado: leads con status "dm_ready"
```

### 8.4 Monitorear el progreso

```bash
# Ver los logs del worker en tiempo real
docker compose logs -f worker

# Ver stats de la campaña
curl http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID_AQUI/stats

# Contar leads por status
curl "http://localhost:8000/api/v1/leads/?campaign_id=CAMPAIGN_ID_AQUI"
```

**En los logs del worker verás algo como:**
```
[INFO] Scraping followers for garyvee...
[INFO] Saved 847 leads (12 duplicates skipped)
[INFO] Scored lead @mariacoach: 82
[INFO] Scored lead @randomuser123: 12
[INFO] Researched lead @mariacoach
[INFO] Generated DM for lead @mariacoach
```

### 8.5 Tiempos estimados

| Cantidad de leads | Scrape | Score | Research | DMs | Total |
|---|---|---|---|---|---|
| 50 leads | ~30s | ~2min | ~1min | ~1min | ~5min |
| 200 leads | ~1min | ~7min | ~3min | ~3min | ~15min |
| 800 leads | ~3min | ~25min | ~8min | ~8min | ~45min |

> **Nota:** El scoring y DM generation son las fases más lentas porque cada lead requiere una llamada individual a Claude. El pipeline procesa leads secuencialmente dentro de cada fase.

---

## 9. Exportar resultados

### 9.1 Exportar CSV (para JarveePro)

```bash
# Descargar como archivo CSV
curl http://localhost:8000/api/v1/export/CAMPAIGN_ID_AQUI/csv -o leads_campaign.csv

# Ver las primeras líneas
head -5 leads_campaign.csv
```

**El CSV contiene estas columnas:**
- `ig_username` — Para que JarveePro sepa a quién enviar
- `ig_full_name` — Nombre del lead
- `score` — Score de calificación
- `lead_category` — Categoría del negocio
- `dm_message` — El DM listo para enviar (Variante A)

### 9.2 Exportar JSON (datos completos)

```bash
curl http://localhost:8000/api/v1/export/CAMPAIGN_ID_AQUI/json | python3 -m json.tool
```

**El JSON incluye todo:** DM Variante A, DM Variante B, research completo, score, razón del score, timestamps de cada fase.

### 9.3 Ver leads por categoría

```bash
# Leads listos para enviar DM
curl "http://localhost:8000/api/v1/leads/dm-ready?campaign_id=CAMPAIGN_ID_AQUI"

# Leads con score alto pero sin DM
curl "http://localhost:8000/api/v1/leads/scored?campaign_id=CAMPAIGN_ID_AQUI"
```

---

## 10. Troubleshooting

### "Cannot connect to the Docker daemon"

```bash
# macOS/Windows: Abre Docker Desktop y espera a que esté listo
# Linux:
sudo systemctl start docker
```

### "Port 5432 already in use"

Otro PostgreSQL ya está corriendo en tu máquina.

```bash
# Opción 1: Para el otro PostgreSQL
# macOS: brew services stop postgresql
# Linux: sudo systemctl stop postgresql

# Opción 2: Cambiar el puerto en docker-compose.yml
# Cambia "5432:5432" a "5433:5432"
# Y actualiza DATABASE_URL en .env: ...@localhost:5433/ig_dm_engine
```

### "Port 8000 already in use"

```bash
# Ver qué proceso usa el puerto
lsof -i :8000  # macOS/Linux
# Matarlo o cambiar el puerto en docker-compose.yml
```

### La API responde pero el worker no procesa tasks

```bash
# Verificar que el worker está corriendo
docker compose ps

# Si el worker no aparece o está en "Exit":
docker compose logs worker
# Probablemente es un error de importación o configuración de Redis
```

### "ANTHROPIC_API_KEY no funciona"

```bash
# Verificar que .env tiene el valor correcto
docker compose exec api python3 -c "from app.config import settings; print(settings.ANTHROPIC_API_KEY[:15])"
# Debe mostrar los primeros 15 caracteres de tu key

# Si muestra vacío: el .env no se está cargando
# Verifica que el archivo se llama exactamente .env (no .env.txt ni .env.example)
```

### Alembic da error "Target database is not up to date"

```bash
# Estampar la versión actual
docker compose exec api alembic stamp head

# Volver a generar migración
docker compose exec api alembic revision --autogenerate -m "fix tables"
docker compose exec api alembic upgrade head
```

### Alembic da error "Can't locate revision"

```bash
# Borrar tabla de versiones y empezar limpio
docker compose exec db psql -U postgres -d ig_dm_engine -c "DROP TABLE IF EXISTS alembic_version;"
docker compose exec api alembic upgrade head
```

### El scoring devuelve JSON inválido ocasionalmente

Esto puede pasar con cualquier LLM. El pipeline tiene retry logic (3 intentos con backoff exponencial). Si falla 3 veces seguidas:
1. Verifica que tu key tiene créditos suficientes
2. Revisa los logs: `docker compose logs -f worker | grep ERROR`
3. Claude puede estar teniendo problemas temporales — espera 5 minutos

### Apify scraping es lento o falla

```bash
# Verificar estado de tu cuenta de Apify
curl "https://api.apify.com/v2/users/me" -H "Authorization: Bearer TU_TOKEN"

# Ver créditos restantes — fíjate en el campo "plan" y "usageTotal"
```

Si el scraping tarda más de 5 minutos para <500 followers, puede ser que:
- El target tiene muchos followers (>10K) — Apify pagina los resultados
- La cuenta tiene rate limiting activo — espera o reduce el tamaño del scrape

---

## 11. Desarrollo local sin Docker (alternativa)

Si prefieres no usar Docker para la API (pero sí para PostgreSQL y Redis):

### 11.1 Levantar solo la infraestructura con Docker

```bash
docker compose up db redis -d
```

### 11.2 Crear virtualenv de Python

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# o en Windows: venv\Scripts\activate
```

### 11.3 Instalar dependencias

```bash
pip install -r requirements.txt
```

### 11.4 Configurar .env para local

Cambia los hosts en `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ig_dm_engine
REDIS_URL=redis://localhost:6379/0
```

### 11.5 Ejecutar migraciones

```bash
alembic upgrade head
```

### 11.6 Levantar la API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 11.7 Levantar el Worker Celery (en otra terminal)

```bash
source venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
```

### 11.8 Ejecutar tests

```bash
pytest
pytest --cov=app  # con cobertura
pytest -v          # verbose (ver cada test individual)
```

---

## Resumen de costos para una campaña real

Para una campaña típica de ~800 leads scrapeados:

| Servicio | Leads procesados | Costo |
|---|---|---|
| **Apify** (scraping) | 800 perfiles | ~$1.50 |
| **Claude** (scoring) | 800 leads | ~$2.40 |
| **Perplexity** (research) | ~200 leads (score ≥ 60) | ~$1.00 |
| **Claude** (DMs × 2 variantes) | ~150 leads (score ≥ 70) | ~$1.95 |
| **Total por campaña** | | **~$6.85** |

Con $20 USD puedes procesar ~2,400 leads y tener ~450 DMs personalizados listos.

---

## Checklist rápido

Usa este checklist para verificar que todo está configurado:

- [ ] Docker Desktop instalado y corriendo
- [ ] Repositorio clonado
- [ ] `.env` creado con las 3 API keys reales
- [ ] `docker compose up --build` funciona sin errores
- [ ] `curl localhost:8000/health` responde `{"status": "healthy"}`
- [ ] Migración de Alembic ejecutada (`alembic revision --autogenerate` + `alembic upgrade head`)
- [ ] Tablas creadas en PostgreSQL (6 tablas)
- [ ] Test de scoring con Claude funciona (devuelve JSON con score)
- [ ] Test de research con Perplexity funciona (devuelve texto)
- [ ] Test de scraping con Apify funciona (devuelve perfil)
- [ ] Test de copywriting con Claude funciona (devuelve DM natural)
- [ ] Primer cliente creado via API
- [ ] Primera campaña creada y pipeline iniciado
- [ ] Export CSV/JSON descargado exitosamente

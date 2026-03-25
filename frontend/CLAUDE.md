@AGENTS.md

# Frontend Upgrade — Migration from Old Dashboard to Next.js

## Status

The Next.js frontend (`frontend/`) is replacing the old vanilla JS dashboard (`app/static/dashboard.html`, ~2,760 lines).

### Completed
- [x] **Settings page** — Full interactive controls: sliders, toggles, AI prompts (Scoring, DM, Follow-up), save/refresh buttons, safety banner

### In Progress — Phase-by-Phase Upgrades

Each page needs to match or exceed the old dashboard's functionality.

---

## Phase 1: Pipeline Page (`src/app/(dashboard)/pipeline/page.tsx`)

### What exists now
- Campaign selector + create campaign modal
- Start Pipeline / Send DMs buttons
- 6 stat cards (Scraped, Scored, DM Ready, Sent, Replied, Failed)
- 3 tabs: Stats (basic), Leads (table with username, name, score, category, status), DMs (card grid)
- Progress indicator + polling

### What's MISSING (must add)
1. **8 stat cards** — Add "Avg Score" and "Qualified 70+" to the existing 6
2. **Richer Lead table** — Add columns: Bio, Followers, DM preview (clickable)
3. **Content Analysis tab** — Gemini multimodal analysis panel
   - Input: content URLs (video, image, webpage) + text
   - Button: "Analizar con Gemini"
   - Display: business_summary, value_propositions, target_audience, tone, pain_points, differentiators
   - Save analysis to campaign
4. **A/B Testing tab** — Variant performance comparison
   - Side-by-side stats: sent, replied, reply_rate, positive_replies, conversion_rate
   - Winner indicator + confidence level + recommendation text
5. **Analytics tab** — Funnel visualization + metrics
   - Funnel: scraped → scored → researched → dm_ready → sent → replied (with counts + percentages)
   - Score distribution (5 buckets: 0-20, 21-40, 41-60, 61-80, 81-100)
   - Category breakdown
   - Timeline (sent/replied by date)
   - Response rate, avg score, conversion funnel
6. **Export tab** — Download buttons for CSV, JSON, Excel
   - Endpoints: GET `/api/v1/export/{campaign_id}/csv`, `/json`, `/excel`
7. **Activity Log section** — Historical events at bottom of page

### Backend Endpoints Available
- `GET /api/v1/campaigns/{id}/analytics` → CampaignAnalytics (funnel, score_distribution, category_breakdown, timeline, etc.)
- `GET /api/v1/campaigns/{id}/ab-results` → ABTestResults (variant_a, variant_b stats, winner, confidence, recommendation)
- `GET /api/v1/campaigns/{id}/stats` → CampaignStats (total_leads, scored, researched, dm_ready, sent, failed, avg_score)
- `POST /api/v1/content/analyze` → body: {content_urls, content_text}
- `POST /api/v1/content/analyze-for-campaign` → body: {campaign_id, content_urls, content_text}
- `GET /api/v1/content/campaign/{campaign_id}` → stored analysis
- `GET /api/v1/export/{campaign_id}/csv` → CSV file download
- `GET /api/v1/export/{campaign_id}/json` → JSON file download
- `GET /api/v1/export/{campaign_id}/excel` → XLSX file download

---

## Phase 2: Comments Page (`src/app/(dashboard)/comments/page.tsx`)

### What's MISSING
1. **Search/filter bar** — Search by username, comment content; status filter dropdown (pending/sent/failed)
2. **Comment stats display** — Counts: pending, sent, failed
3. **"Enviar Masivo" button** — Bulk send all pending comments
4. **Variant B display** — Show variant B with toggle/collapsible
5. **Copy buttons** — Copy comment text to clipboard
6. **Info banner** — Explain auto-generation for high-score leads

---

## Phase 3: DMs Page (`src/app/(dashboard)/dms/page.tsx`)

### What's MISSING
1. **Category filter dropdown** — Filter by lead category
2. **"Copy All DMs" button** — Copy all visible DMs to clipboard
3. **Status pills** — Show delivery status (dm_ready, sent, failed, etc.)
4. **Send DM buttons** — Individual send button per lead (if not sent)
5. **DM content search** — Search within DM text, not just username

---

## Phase 4: Clients Page (`src/app/(dashboard)/clients/page.tsx`)

### What's MISSING
1. **Client stats on cards** — Show: campaign count, leads count, last activity date
2. **Max Daily DMs field** — Number input in edit modal for per-client DM limit
   - Backend endpoint: `GET /api/v1/clients/{id}/analytics` → ClientAnalytics

---

## Phase 5: Health Page (`src/app/(dashboard)/health/page.tsx`)

### What's MISSING
1. **Details column in Audit Log** — The `details` field (JSON) exists in the API response but isn't shown in the table

---

## Tech Stack & Patterns

- **Next.js 16.2.1** + React 19 + TypeScript
- **Tailwind CSS v4** for styling
- **lucide-react** for icons
- **clsx + tailwind-merge** via `cn()` helper in `src/lib/cn.ts`
- **API helper** in `src/lib/api.ts` — `api<T>(path, opts)` with JWT auth
- **WebSocket helper** — `wsUrl(path)` for WS connections
- **Auth** in `src/lib/auth.ts` — `getToken()`, `getUser()`, `clearAuth()`
- All pages use `"use client"` directive
- Dashboard layout in `src/app/(dashboard)/layout.tsx` with Sidebar
- Sidebar in `src/components/layout/sidebar.tsx`

## File Downloads Pattern
For export endpoints that return files (CSV, Excel), use direct window.open() or anchor download:
```typescript
const token = localStorage.getItem("access_token");
const url = `${API_BASE}/api/v1/export/${campaignId}/csv`;
// Use fetch with auth header, then create blob download
```

## Important
- Read `node_modules/next/dist/docs/` before using any Next.js API — this version may differ from training data
- All pages are `"use client"` components (no server components in dashboard)
- API base URL from `NEXT_PUBLIC_API_URL` env var, defaults to `http://localhost:1000`

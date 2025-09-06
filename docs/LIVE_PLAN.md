### 2025-09-06T01:05Z
- UI polish per project flow:
  - Category-colored markers; richer popup with distance + age
  - Drawer: badges, distance/age, Open in Maps, Report
  - Create modal: Need/Offer toggle; mobile-friendly layout
  - Status chips showing last-updated for 311, Shelters, Food
  - Basic toasts for error/success

## LIVE IMPLEMENTATION PLAN (auto-updated)

This file is updated continuously as implementation progresses. Each change will append a timestamped entry.

### Status
- Phase: Planning & scaffolding
- City: Houston (designed city-agnostic)

### Environment & Config
- Hosting: Railway (single FastAPI service)
- DB: Neon Postgres
- Env vars: DATABASE_URL, MAPTILER_KEY, GEOCODER_KEY, FLOOD_WMS_URL, ONESIGNAL_APP_ID?, ONESIGNAL_API_KEY?

### Milestone Tracker
1. SRS and Live Plan [SRS done; Live Plan started]
2. DB schema + migrations
3. FastAPI scaffold + static serving
4. Map UI + layers (311, flood proxy, shelters/food cover files)
5. Pins + comments CRUD with polling
6. PWA + icons
7. Optional push
8. Polish + demo seed data

---

### 2025-09-06T00:00Z
- Created `docs/SRS.md` with MVP scope, architecture, endpoints, and acceptance criteria.
- Initialized `docs/LIVE_PLAN.md` and established milestone tracker and env config.

### Next Actions
- Scan workspace for existing code/assets; document gaps.
- Define DB schema SQL and migration plan.
- Scaffold FastAPI app structure and static asset pipeline.

### 2025-09-06T00:02Z
- Workspace scan: Only `docs/` present with `SRS.md`, `LIVE_PLAN.md`, and planning docx. No app code yet.
- Implication: We will create the full repo scaffold (FastAPI + static frontend) from scratch.

### 2025-09-06T00:06Z
- Added project scaffold:
  - `requirements.txt` (FastAPI + Uvicorn)
  - `.gitignore` (includes `mcp.json`)
  - `app/main.py` with FastAPI app, `/healthz`, root serving `web/index.html`, and static mount
  - `web/index.html` with Leaflet + Tailwind + Alpine shell and role toggle
- Next: DB schema and migrations, then API routing.

### 2025-09-06T00:10Z
- Database setup:
  - Added `db/schema.sql` (pins, comments, shelters, food_supply_sites, push_subscriptions)
  - Added `app/db.py` with async init executing schema
  - Wired DB init on app startup; added psycopg to requirements
- Note: Startup continues if DB not yet provisioned (dev-friendly).

### 2025-09-06T00:16Z
- Implemented Pins & Comments API:
  - `app/models.py` Pydantic models
  - `app/routes_pins.py` with list/create pins, list/create comments, report (soft-hide)
  - Mounted router in `app/main.py`
- Next: Shelters & Food endpoints + cover file loading.

### 2025-09-06T00:20Z
- Added Shelters & Food endpoints with cover files:
  - `app/routes_refdata.py` (`/api/shelters`, `/api/food`) reading from `data/`
  - Seed files: `data/shelters.json`, `data/food_supply_sites.json`
  - Router mounted in `app/main.py`
- Next: 311 proxy (cached) and Flood WMS proxy.

### 2025-09-06T00:26Z
- Implemented 311 proxy and Flood WMS proxy:
  - `app/routes_feeds.py` with `/api/311` (120s cache) and `/api/flood/wms` proxy
  - Fallback seed: `data/houston_311_seed.geojson`
  - Added `httpx` to requirements and mounted router in `app/main.py`
- Next: Static frontend map toggles and polling.

### 2025-09-06T00:31Z
- Frontend map layers & polling:
  - Updated `web/index.html` with layer toggles (Needs/Offers/Shelters/Food/311/Flood), radius chips, geolocation, and polling (25–30s)
  - Added simple circle radius overlay and visibility toggles
- Next: Create Pin + Comments UI and wire to API.

### 2025-09-06T00:37Z
- Frontend interactions:
  - Added floating create button and modal for Need/Offer creation with categories, title, body, and location (map tap or geolocate)
  - Wired POST /api/pins; new pins refresh on success
  - Added pin drawer with comments list, input, and 10s polling; wired to /api/pins/{id}/comments
  - Introduced anon handle persisted in localStorage

### 2025-09-06T00:42Z
- PWA & Moderation:
  - Added `web/manifest.json`, `web/sw.js`, routes in FastAPI, and registration in index.html
  - Added simple profanity redaction and per-minute rate limits for creates/comments
  - Updated create/comment endpoints to enforce moderation
- Next: Seed demo data and quick README with run/deploy steps.

### 2025-09-06T00:48Z
- Seeds & Config:
  - Exposed public config via `/config.js` (MapTiler key, 311 URL)
  - Added disclaimer banner in UI
  - Added `scripts/seed.py` for demo data
  - Added `README.md` with local run and Railway deploy steps
- Remaining: optional push notifications.




## HelpingHive

Community crisis mapping for needs and offers in real‑time.

— Minimal UI. Fast map. Server‑side proxies to external data to keep the client light.

### Table of Contents
- Overview
- Screenshots
- Features
- Architecture
- Getting Started
- Configuration (env)
- Data & Seeding
- API
- Deployment
- Troubleshooting
- License

### Overview
HelpingHive is a lightweight web app that connects people who need help with neighbors who can offer help. It highlights official resources (shelters, food/supply) alongside community pins.

### Try it out here: https://helpinghive.up.railway.app/

### Screenshots
<img width="1918" height="865" alt="Map UI" src="https://github.com/user-attachments/assets/f767c170-d4db-474a-bdea-a029f15037a0" />
<img width="375" height="337" alt="HelpingHive AI Agent" src="https://github.com/user-attachments/assets/3cfc394d-5dfa-45a0-8b89-64da770627f1" />
<img width="528" height="561" alt="Pin Posting" src="https://github.com/user-attachments/assets/ed3d8be7-002b-4a25-b25f-52661e8aa748" />
<img width="609" height="380" alt="Pin Comments" src="https://github.com/user-attachments/assets/387a0ebc-791e-44e7-927a-d6310af4baa4" />



### Features
- Modern, minimal map UI with a bottom pill bar (Layers · + Add · Tools · Chat)
- Pins
  - Need = teardrop; urgency (Low/Med/High) in yellow/orange/red
  - Offer = hexagon; green
  - Category initial rendered on the marker face for fast scanning
- Legend (top‑right) with a compact urgency key plus Shelter and Food icons
- Overlays: Flood (ArcGIS/WMS), Metro bus routes, Food deserts
- Reference layers: Shelters (ArcGIS + local fallback), Food/Supply (ArcGIS + CSV + local)
- HelpHive chat window (server‑assisted): clickable results that focus and highlight on map

### Architecture
- Frontend: static `web/` (Alpine.js + Leaflet + Tailwind CDN)
- Backend: FastAPI (Python 3.11), server‑side proxies for ArcGIS/WMS
- DB: Postgres (psycopg3) for community pins/comments
- Hosting: Railway (Nixpacks), configured via `Procfile` and `railway.toml`

### Getting Started
1) Requirements
   - Python 3.11
   - A Postgres database (e.g., Neon)
2) Create `.env` in the repo root:
```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DB
MAPTILER_KEY=your_maptiler_key

# Optional external feeds / overlays
HOUSTON_311_URL=...
FLOOD_WMS_URL=...
FLOOD_WMS_LAYERS=0
FLOOD_ARCGIS_URL=...
FLOOD_ARCGIS_LAYERS=0

# Shelters (ArcGIS)
# Either point to a layer URL …/FeatureServer/1  OR a direct …/FeatureServer/1/query URL
SHELTERS_URL=...
# If using base …/FeatureServer, set the layer index here
# SHELTERS_LAYER=1

# Food sites (ArcGIS table or GeoJSON)
FOOD_SITES_URL=...
```
3) Install dependencies
```bash
pip install -r requirements.txt
```
4) Run locally
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
5) Open `http://localhost:8000`

### Configuration (env)
| Name | Required | Example | Notes |
|------|----------|---------|-------|
| DATABASE_URL | Yes | postgresql://… | psycopg3 DSN |
| MAPTILER_KEY | Yes | abc123 | Map tiles for Leaflet |
| SHELTERS_URL | No | …/FeatureServer/1 or …/FeatureServer/1/query | Robust parsing for both | 
| SHELTERS_LAYER | No | 1 | Used only if `SHELTERS_URL` ends at `/FeatureServer` |
| FOOD_SITES_URL | No | ArcGIS/GeoJSON | Food/Supply reference |
| FLOOD_WMS_URL | No | WMS endpoint | Flood overlay fallback |
| FLOOD_WMS_LAYERS | No | 0 | Comma‑separated WMS layer ids |
| FLOOD_ARCGIS_URL | No | ArcGIS MapServer | Preferred flood overlay |
| FLOOD_ARCGIS_LAYERS | No | 0,1,6,7 | Visible sublayers |
| HOUSTON_311_URL | No | JSON/GeoJSON | Live 311 feed |

### Data & Seeding
Seed demo pins into Postgres:
```bash
python scripts/seed.py
```
Windows users: the script automatically switches to a compatible event loop policy.

Remove seeded data later:
```sql
delete from pins where author_anon_id like 'seed-%';
```

Shelters (ArcGIS)
- Supports both layer URLs and direct `/query` URLs.
- Server‑side conversion to WGS84 lat/lng; cached for 300s.
- Bypass cache for testing: `GET /api/shelters?nocache=true`.

### API
- `GET /api/pins` — list community pins
- `POST /api/pins` — create pin
- `GET /api/shelters` — official/community shelters (ArcGIS + local)
- `GET /api/food` — food/supply sites (ArcGIS + local + CSV)
- `GET /api/311` — optional 311 feed (proxy)
- `POST /api/assist/qna` — HelpHive assistant

### Deployment (Railway)
- Connect the repository and deploy (Nixpacks).
- Set env vars (`DATABASE_URL`, `MAPTILER_KEY`, optional overlays and feeds).
- Start command:
```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Troubleshooting
- Shelters not loading?
  - Verify `SHELTERS_URL` returns features in a browser.
  - Test server: `/api/shelters?nocache=true`.
  - If using base `…/FeatureServer`, add `SHELTERS_LAYER`.
- Stale assets/icons?
  - Hard refresh (Ctrl+F5). If using a service worker, enable “Bypass for network” in DevTools.

### License
The HelpingHive Team

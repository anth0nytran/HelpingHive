## HelpingHive — MVP

### Quick start (local)
1. Python 3.11
2. Create `.env` (or export env vars):
   - `DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DB`
   - `MAPTILER_KEY=...`
   - Optional overlays and feeds:
     - `HOUSTON_311_URL` (JSON table or GeoJSON)
     - `FLOOD_WMS_URL`, `FLOOD_WMS_LAYERS`
     - `FLOOD_ARCGIS_URL`, `FLOOD_ARCGIS_LAYERS`
     - `SHELTERS_URL` (ArcGIS layer URL or direct /query URL)
       - Examples:
         - Layer URL: `.../FeatureServer/1`
         - Direct query: `.../FeatureServer/1/query?...&f=json`
       - If you set base `.../FeatureServer`, you can add `SHELTERS_LAYER=1` to select the layer.
     - `FOOD_SITES_URL` (ArcGIS table or GeoJSON)
3. Install deps:
```bash
pip install -r requirements.txt
```
4. Run API:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
5. Visit `http://localhost:8000`

### Features
- Minimal map UI with bottom pill bar: Layers, center “+” add button, Tools, and HelpHive chat.
- Needs vs Offers markers:
  - Need = teardrop; urgency colors: Low (yellow), Med (orange), High (red)
  - Offer = hexagon; green
  - Category initial rendered on the marker face
- Overlays: Flood (ArcGIS/WMS), Metro bus, Food deserts
- Reference layers: Shelters (ArcGIS + local fallback), Food/Supply (ArcGIS + CSV + local)
- Legend (top‑right): condensed need urgency key, offer, shelter, food icons
- HelpHive chat window: asks `/api/assist/qna`, returns clickable items that focus/highlight on the map

### Seed demo data
```bash
python scripts/seed.py
```
- On Windows the seeder auto-switches to a compatible event loop policy.
- Clear seeded rows later:
```sql
delete from pins where author_anon_id like 'seed-%';
```

### Shelters (ArcGIS) configuration
- Works with both layer URLs and direct `/query` URLs.
- Server-side fetch converts results to lat/lng; caches for 300s.
- Force refresh: `GET /api/shelters?nocache=true`.

### Favicon / Branding
- `/favicon.ico` is served from (first match wins):
  1) `data/helpier icon.svg`
  2) `data/helpie.png`
  3) `web/static/helpie.png`
  4) fallback `web/static/icons/icon.svg`

### Deploy (Railway)
- Connect GitHub repo and deploy. Builder: Nixpacks.
- This repo includes `Procfile` and `railway.toml`.
- Env vars: `DATABASE_URL`, `MAPTILER_KEY`, optional `HOUSTON_311_URL`, `FLOOD_*`, `SHELTERS_URL`, `SHELTERS_LAYER`, `FOOD_SITES_URL`.
- Start command (already set):
```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Docs
- `docs/SRS.md` — requirements
- `docs/LIVE_PLAN.md` — implementation log
- `docs/project.md` — overview/notes
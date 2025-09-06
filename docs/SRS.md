## Software Requirements Specification (SRS)

### 1. Overview
ReliefLink is a mobile-first, map-centric web app that connects people in disasters who need help with those who can help. MVP targets a 48-hour build for a compelling demo: fast, clean UI; Houston-only, designed to be city-agnostic.

### 2. Goals and Non-Goals
- **Goals**:
  - Map-first interface showing Needs, Offers, 311 incidents, Flood zones, Shelters, Food/Supply.
  - Anonymous participation (no auth). Create Needs/Offers and comment threads.
  - Polling-based near-real-time updates; optional push notifications for helpers.
  - Shelters tab (official + community) and Food/Supply layer.
  - PWA basics for Add-to-Home-Screen.
- **Non-Goals**:
  - Full moderation workflow, user accounts, complex RBAC.
  - Offline maps, full i18n, advanced analytics.

### 3. Users and Roles
- **Seeker**: I need help.
- **Helper**: I want to help.
- Role is toggled and stored locally.

### 4. Acceptance Criteria (Demo)
1) From fresh phone: select role, set location; map loads < 3s.
2) Toggle Flood Zones and 311; overlays/pins show with Last updated.
3) Create a Need (Food). On second phone, appears ≤ 30s.
4) Add a comment; both phones see it ≤ 15s.
5) Shelters tab shows official + community entries.
6) Food/Supply layer shows free-food/drop-off spots.
7) (Optional) Push for helpers when a Need within radius is posted.

### 5. UX Flows
- **Landing**: Two full-screen buttons: Need help / Want to help. Persist role.
- **Location**: Try geolocation; fallback map tap or search. Default to Houston center (29.7604, -95.3698), zoom 12.
- **Map Screen**: Toggle chips: Needs, Offers, 311, Flood zones, Shelters, Food/Supply. Radius chips 5/10/20 mi draw circle filter. Color-coding: Needs=warm, Offers=cool.
- **Create Pin**: At current/tapped location: category + note (240 chars). Title optional.
- **Pin Drawer**: Distance, categories, age, description, anon comments (200 chars), Report.
- **Shelters Tab**: List + map, official/community badge, capacity/notes, last updated, Open in Maps.
- **Food/Supply**: Map pins; official/community; fields per data model.

### 6. Data Model
- **pins**: id (uuid), kind ('need'|'offer'), categories (text[]), title (text), body (text), lat (double), lng (double), author_anon_id (text), created_at (timestamptz), expires_at (timestamptz)
- **comments**: id (uuid), pin_id (uuid fk), body (text), author_anon_id (text), created_at (timestamptz)
- **shelters**: id (uuid), name (text), type ('official'|'community'), lat (double), lng (double), capacity (text), notes (text), last_updated (timestamptz)
- **food_supply_sites**: id (uuid), name (text), kind ('free_food'|'drop_off'), lat (double), lng (double), status (text), needs (text), last_updated (timestamptz), source ('official'|'community')
- **push_subscriptions (optional)**: anon_id (text), onesignal_id (text), geohash (text), radius_mi (int), role (text), categories (text[]), last_notified_at (timestamptz)

### 7. Canonical Categories and Mapping
- **Needs**: Food, Shelter, Medical Aid, Transport, Supplies.
- **Offers**: Meals, Beds, Medical, Transport, Supplies.
- Mapping examples: Need:Food ↔ Offer:Meals; Need:Shelter ↔ Offer:Beds; Need:Medical Aid ↔ Offer:Medical.

### 8. System Architecture
- **Frontend**: Static HTML + Tailwind + Alpine.js + Leaflet, served by FastAPI.
- **Backend**: FastAPI (Python 3.11) on Railway.
- **DB**: Neon Postgres (serverless). SQLAlchemy + async.
- **Tiles**: MapTiler base tiles.
- **Data sources**: Houston 311 (proxied, cached 120s), Flood zones (FEMA/ArcGIS WMS via proxy), cover files for official shelters/food/supply; community adds stored in DB.
- **Realtime**: Polling: map 20–30s, comments 10s.
- **Notifications (optional)**: OneSignal with geohash targeting + 20-minute cooldown.

### 9. API Endpoints (MVP)
- GET /api/pins?bbox=&radius=&center=&kinds=&categories=&since=
- POST /api/pins { kind, categories, title?, body, lat, lng }
- GET /api/pins/{id}
- GET /api/pins/{id}/comments
- POST /api/pins/{id}/comments { body }
- POST /api/pins/{id}/report
- GET /api/shelters (list official+community)
- POST /api/shelters (community only)
- GET /api/food (official+community)
- POST /api/food (community only)
- GET /api/311 (server-proxied, cached)
- GET /api/flood/wms?bbox= (proxy)
- POST /api/subscribe (optional OneSignal)

### 10. Non-Functional Requirements
- Performance: initial load < 3s on mid-range Android; 311 limited to last 100 incidents.
- Availability: single-region; acceptable brief downtime.
- Security: no auth; rate limits and profanity redaction; report soft-hide.
- Privacy: anon IDs in localStorage; minimal logging.
- Accessibility: high contrast, large tap targets, semantic HTML.

### 11. Rate Limits and Moderation
- Create: 3/min, 30/day per IP.
- Comment: 6/min, 100/day per IP.
- Report: 10/day per IP.
- Profanity: wordlist redaction.

### 12. PWA and Telemetry
- Manifest + icons; install prompt; no offline map.
- Analytics and error tracking skipped for MVP; keep env toggles for future.

### 13. Risks and Mitigations
- 311 delay: show Last updated; cap items; seed demo data.
- iOS push limits: polling ensures freshness.
- Spam: rate limits + redact + Report soft-hide.
- Geolocation failure: map tap + search fallback.

### 14. Deployment and Config
- Railway service hosting (HTTPS). Single service serves API + static.
- Env vars: DATABASE_URL, MAPTILER_KEY, GEOCODER_KEY, FLOOD_WMS_URL, ONESIGNAL_APP_ID?, ONESIGNAL_API_KEY? (optional).

### 15. Milestones
1) SRS and Live Plan
2) DB schema + migrations
3) FastAPI scaffold + static serving
4) Map UI + layers (311, flood proxy, shelters/food cover files)
5) Pins + comments CRUD with polling
6) PWA + icons
7) Optional push
8) Polish + demo seed data



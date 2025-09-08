from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import asyncio

from .db import init_db
from . import config  # noqa: F401  # ensure .env is loaded early
from .routes_pins import router as pins_router
from .routes_refdata import router as refdata_router
from .routes_feeds import router as feeds_router
from .routes_ai import router as ai_router


BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
INDEX_FILE = WEB_DIR / "index.html"


app = FastAPI(title="ReliefLink API", version="0.1.0")
app.include_router(pins_router)
app.include_router(refdata_router)
app.include_router(feeds_router)
app.include_router(ai_router)


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_FILE)


@app.get("/manifest.json")
def manifest() -> FileResponse:
    return FileResponse(WEB_DIR / "manifest.json")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(WEB_DIR / "sw.js")


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    # Prefer custom SVG/PNG in data/, then web/static, else default SVG
    data_svg = BASE_DIR / "data" / "helpier icon.svg"
    if data_svg.exists():
        return FileResponse(data_svg, media_type="image/svg+xml")
    data_png = BASE_DIR / "data" / "helpie.png"
    if data_png.exists():
        return FileResponse(data_png, media_type="image/png")
    static_png = WEB_DIR / "static" / "helpie.png"
    if static_png.exists():
        return FileResponse(static_png, media_type="image/png")
    return FileResponse(WEB_DIR / "static" / "icons" / "icon.svg", media_type="image/svg+xml")


@app.get("/config.js")
def config_js() -> Response:
    import os
    cfg = {
        "MAPTILER_KEY": os.getenv("MAPTILER_KEY", ""),
        "HOUSTON_311_URL": os.getenv("HOUSTON_311_URL", ""),
        "FLOOD_WMS_URL": os.getenv("FLOOD_WMS_URL", ""),
        "FLOOD_WMS_LAYERS": os.getenv("FLOOD_WMS_LAYERS", "0"),
        "FLOOD_ARCGIS_URL": os.getenv("FLOOD_ARCGIS_URL", ""),
        "FLOOD_ARCGIS_LAYERS": os.getenv("FLOOD_ARCGIS_LAYERS", "0,1,6,7,8,9,10"),
    }
    body = "window.__CONFIG__ = " + __import__("json").dumps(cfg) + ";"
    return Response(content=body, media_type="application/javascript")


# Mount static directory for future assets (icons, manifest, etc.)
static_dir = WEB_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
async def on_startup() -> None:
    # Initialize database schema
    try:
        await init_db()
    except Exception as exc:
        # Don't crash on local dev without DB; just log
        print("[startup] DB init skipped/error:", exc)



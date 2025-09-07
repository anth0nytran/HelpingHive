import os
import time
from pathlib import Path
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse


router = APIRouter(prefix="/api", tags=["feeds"])

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FALLBACK_311 = DATA_DIR / "houston_311_seed.geojson"

_cache: Dict[str, Any] = {"data": None, "ts": 0}
_ttl = 120  # seconds


def _now() -> int:
    return int(time.time())


def _arcgis_table_to_geojson(data: Dict[str, Any]) -> Dict[str, Any]:
    # Convert ArcGIS FeatureSet (table, no geometry) to GeoJSON using Latitude/Longitude or Y/X
    features = []
    for f in (data.get("features") or []):
        attrs = f.get("attributes") or {}
        lat = attrs.get("Latitude") or attrs.get("Y")
        lng = attrs.get("Longitude") or attrs.get("X")
        if lat is None or lng is None:
            continue
        props = {
            "category": attrs.get("CaseType") or attrs.get("Title") or attrs.get("Status") or "311",
            "updated": attrs.get("CreatedDate") or attrs.get("ClosedDate"),
            "raw": attrs,
        }
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Point", "coordinates": [float(lng), float(lat)]},
        })
    return {"type": "FeatureCollection", "features": features}


@router.get("/311")
async def houston_311():
    # Replace with actual endpoint if available; use generic placeholder
    url = os.getenv("HOUSTON_311_URL")
    if _cache["data"] and _now() - _cache["ts"] < _ttl:
        return JSONResponse(_cache["data"]) 
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            # If ArcGIS table/json, convert to GeoJSON
            if isinstance(data, dict) and data.get("type") != "FeatureCollection" and "features" in data:
                data = _arcgis_table_to_geojson(data)
            # Cap features count for performance
            if isinstance(data, dict) and "features" in data:
                data["features"] = data["features"][:100]
            _cache["data"], _cache["ts"] = data, _now()
            return JSONResponse(data)
    except Exception:
        if FALLBACK_311.exists():
            import json as _json
            data = _json.loads(FALLBACK_311.read_text(encoding="utf-8"))
            return JSONResponse(content=data)
        raise HTTPException(status_code=502, detail="311 feed unavailable")


@router.get("/flood/wms")
async def flood_wms_proxy(request: Request):
    """
    Streaming proxy for WMS tiles. Forwards the incoming querystring to the configured
    upstream WMS server to avoid CORS and allow tiled requests from the browser.
    """
    base = os.getenv("FLOOD_WMS_URL")
    if not base:
        raise HTTPException(status_code=400, detail="FLOOD_WMS_URL not configured")
    qs = str(request.url.query)
    upstream = f"{base}?{qs}" if qs else base
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(upstream)
            media = resp.headers.get("content-type", "image/png")
            return StreamingResponse(resp.aiter_bytes(), media_type=media, status_code=resp.status_code)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"WMS proxy error: {exc}")



# ---------- ArcGIS FeatureServer overlays (GeoJSON with optional bbox) ----------
async def _arcgis_query_geojson(url: str, bbox: str | None = None, geometry_sr: str = "4326") -> Dict[str, Any]:
    params = {
        "f": "geojson",
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
    }
    if bbox:
        # bbox = minLng,minLat,maxLng,maxLat in WGS84
        params.update({
            "geometry": bbox,
            "geometryType": "esriGeometryEnvelope",
            "inSR": geometry_sr,
            "spatialRel": "esriSpatialRelIntersects",
        })
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url.rstrip("/") + "/query", params=params)
        r.raise_for_status()
        data = r.json()
        # Cap features for safety
        if isinstance(data, dict) and "features" in data:
            data["features"] = data["features"][:2000]
        return data


@router.get("/overlay/metro_bus")
async def overlay_metro_bus(bbox: str | None = Query(None, description="minLng,minLat,maxLng,maxLat")):
    url = os.getenv("METRO_BUS_FEATURE_URL", "https://services.arcgis.com/NummVBqZSIJKUeVR/arcgis/rest/services/METRO_Frequent_Bus_Routes/FeatureServer/0")
    try:
        data = await _arcgis_query_geojson(url, bbox=bbox)
        return JSONResponse(data)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"metro_bus overlay error: {exc}")


@router.get("/overlay/food_deserts")
async def overlay_food_deserts(bbox: str | None = Query(None, description="minLng,minLat,maxLng,maxLat")):
    url = os.getenv("FOOD_DESERTS_FEATURE_URL", "https://services.arcgis.com/NummVBqZSIJKUeVR/arcgis/rest/services/Food_Deserts/FeatureServer/0")
    try:
        data = await _arcgis_query_geojson(url, bbox=bbox)
        return JSONResponse(data)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"food_deserts overlay error: {exc}")


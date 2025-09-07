import json
import os
import time
from pathlib import Path
import csv
from typing import List, Any, Dict

import httpx
from fastapi import APIRouter, HTTPException


router = APIRouter(prefix="/api", tags=["refdata"])

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SHELTERS_FILE = DATA_DIR / "shelters.json"
FOOD_FILE = DATA_DIR / "food_supply_sites.json"
DOCS_DIR = BASE_DIR / "docs"
PANTRIES_CSV = DOCS_DIR / "Hou_Pantries.csv"


def _read_json(path: Path):
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Missing data file: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))

_cache: Dict[str, Any] = {"s": None, "s_ts": 0, "f": None, "f_ts": 0}

async def _fetch_json(url: str) -> Any:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()

def _arcgis_to_points(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    points: List[Dict[str, Any]] = []
    sr = (data.get("spatialReference") or {}).get("wkid") or None
    for feat in (data.get("features") or []):
        attrs = feat.get("attributes") or {}
        geom = feat.get("geometry") or {}
        lat = attrs.get("Latitude") or attrs.get("Y") or geom.get("y")
        lng = attrs.get("Longitude") or attrs.get("X") or geom.get("x")
        if lat is None or lng is None:
            continue
        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except Exception:
            continue
        # Auto-convert Web Mercator (meters) to WGS84 if values out of lat/lng range
        if abs(lat_f) > 90 or abs(lng_f) > 180 or (sr in (102100, 3857)):
            try:
                # EPSG:3857 → EPSG:4326
                R = 6378137.0
                x = lng_f
                y = lat_f
                lng_f = (x / R) * 180.0 / 3.141592653589793
                lat_f = (2 * ( (y / R) ))
                lat_f = (180.0 / 3.141592653589793) * (0.5 * (3.141592653589793 + ( (lambda t: (2*__import__('math').atan(__import__('math').exp(t)) - 3.141592653589793))(lat_f) )))
            except Exception:
                # Fallback: skip invalid point
                continue
        points.append({"lat": lat_f, "lng": lng_f, "attrs": attrs})
    return points


async def _arcgis_query_features(url: str) -> List[Dict[str, Any]]:
    """Query an ArcGIS FeatureServer layer robustly and return list of features (dicts).
    Tries f=geojson first; if not supported returns f=json and converts to GeoJSON-like dicts.
    """
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
    }
    qurl = url.rstrip("/") + "/query"
    # Try GeoJSON response
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            p = {**params, "f": "geojson"}
            r = await client.get(qurl, params=p)
            r.raise_for_status()
            gj = r.json()
            feats = gj.get("features") or []
            if feats:
                return feats
    except Exception:
        pass
    # Fallback to JSON and convert
    async with httpx.AsyncClient(timeout=20) as client:
        p = {**params, "f": "json"}
        r = await client.get(qurl, params=p)
        r.raise_for_status()
        data = r.json()
        feats = []
        for f in (data.get("features") or []):
            attrs = f.get("attributes") or {}
            geom = f.get("geometry") or {}
            lat = None
            lng = None
            # Point geometry
            if "y" in geom and "x" in geom:
                lat = geom.get("y")
                lng = geom.get("x")
            # Polygon centroid (simple average of ring vertices)
            elif "rings" in geom:
                try:
                    xs = []
                    ys = []
                    for ring in geom.get("rings") or []:
                        for pt in ring:
                            xs.append(pt[0])
                            ys.append(pt[1])
                    if xs and ys:
                        lng = sum(xs) / len(xs)
                        lat = sum(ys) / len(ys)
                except Exception:
                    lat, lng = None, None
            if lat is None or lng is None:
                continue
            feats.append({"geometry": {"type": "Point", "coordinates": [lng, lat]}, "properties": attrs})
        return feats

def _std_shelter(item: Dict[str, Any]) -> Dict[str, Any]:
    attrs = item.get("attrs", {})
    t = attrs.get("Type") or attrs.get("Source") or "official"
    if isinstance(t, str):
        t = t.lower()
    return {
        "id": attrs.get("ObjectID") or attrs.get("id") or None,
        "name": attrs.get("Name") or attrs.get("FacilityName") or attrs.get("Title") or "Shelter",
        "type": t if isinstance(t, str) else "community",
        "lat": item["lat"],
        "lng": item["lng"],
        "capacity": attrs.get("Capacity") or attrs.get("Beds") or None,
        "notes": attrs.get("Notes") or attrs.get("Status_1") or attrs.get("Status") or None,
        "last_updated": attrs.get("Updated") or attrs.get("LastUpdate") or None,
    }

def _std_food(item: Dict[str, Any]) -> Dict[str, Any]:
    attrs = item.get("attrs", {})
    kind = (attrs.get("Kind") or attrs.get("Type") or attrs.get("Category") or "free_food").lower() if isinstance(attrs.get("Kind") or attrs.get("Type") or attrs.get("Category"), str) else "free_food"
    if kind in ("dropoff", "drop_off", "donation"):
        kind = "drop_off"
    elif kind not in ("free_food", "drop_off"):
        kind = "free_food"
    return {
        "id": attrs.get("ObjectID") or attrs.get("id") or None,
        "name": attrs.get("Name") or attrs.get("SiteName") or attrs.get("Title") or "Food/Supply",
        "kind": kind,
        "lat": item["lat"],
        "lng": item["lng"],
        "status": attrs.get("Status") or attrs.get("Open") or None,
        "needs": attrs.get("Needs") or attrs.get("Notes") or None,
        "source": (attrs.get("Source") or "official").lower() if isinstance(attrs.get("Source"), str) else "official",
        "last_updated": attrs.get("Updated") or attrs.get("LastUpdate") or None,
    }


def _read_pantries_csv() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not PANTRIES_CSV.exists():
        return results
    try:
        with PANTRIES_CSV.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 3:
                    continue
                # Heuristic: last two numeric fields are lat,lng
                lat = None
                lng = None
                for i in range(len(row) - 1, -1, -1):
                    try:
                        val = float(row[i])
                        if lng is None:
                            lng = val
                        elif lat is None:
                            lat = val
                            break
                    except Exception:
                        continue
                if lat is None or lng is None:
                    continue
                name = row[0].strip()
                address = row[1].strip() if len(row) > 1 else ""
                website = row[2].strip() if len(row) > 2 else ""
                results.append({
                    "id": None,
                    "name": name,
                    "kind": "free_food",
                    "lat": float(lat),
                    "lng": float(lng),
                    "status": None,
                    "needs": address,
                    "website": website,
                    "source": "official",
                    "last_updated": None,
                })
    except Exception:
        return results
    return results


@router.get("/shelters")
async def list_shelters():
    remote_url = os.getenv("SHELTERS_URL")
    results: List[Dict[str, Any]] = []
    now = int(time.time())
    if remote_url:
        if not _cache["s"] or now - _cache["s_ts"] > 300:
            try:
                # Prefer ArcGIS FeatureServer query with outSR=4326 to ensure WGS84
                if ("arcgis/rest/services" in remote_url) and ("FeatureServer" in remote_url):
                    feats = await _arcgis_query_features(remote_url)
                    pts: List[Dict[str, Any]] = []
                    for feat in feats:
                        try:
                            geom = feat.get("geometry") or {}
                            props = feat.get("properties") or {}
                            if geom.get("type") == "Point":
                                lng, lat = geom.get("coordinates") or [None, None]
                                if lat is None or lng is None:
                                    continue
                                pts.append({"lat": float(lat), "lng": float(lng), "attrs": props})
                        except Exception:
                            continue
                    _cache["s"] = [_std_shelter(p) for p in pts]
                    _cache["s_ts"] = now
                else:
                    data = await _fetch_json(remote_url)
                    points = _arcgis_to_points(data)
                    _cache["s"] = [_std_shelter(p) for p in points]
                    _cache["s_ts"] = now
            except Exception:
                _cache["s"] = []
        results.extend(_cache["s"])  
    try:
        results.extend(_read_json(SHELTERS_FILE))
    except HTTPException:
        pass
    return results


@router.get("/food")
async def list_food_sites():
    remote_url = os.getenv("FOOD_SITES_URL")
    results: List[Dict[str, Any]] = []
    now = int(time.time())
    if remote_url:
        if not _cache["f"] or now - _cache["f_ts"] > 300:
            try:
                data = await _fetch_json(remote_url)
                points = _arcgis_to_points(data)
                _cache["f"] = [_std_food(p) for p in points]
                _cache["f_ts"] = now
            except Exception:
                _cache["f"] = []
        results.extend(_cache["f"])  
    # Local JSON
    try:
        results.extend(_read_json(FOOD_FILE))
    except HTTPException:
        pass
    # CSV pantries
    results.extend(_read_pantries_csv())
    return results



import os
import json
import time
from typing import Any, Dict, List, Optional
import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import sys
try:
    import google.generativeai as genai
    _k = (os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'")
    if _k:
        genai.configure(api_key=_k)
except Exception:
    genai = None

def _ensure_sdk_loaded() -> bool:
    global genai
    if genai is not None:
        return True
    try:
        import importlib  # noqa: F401
        import google.generativeai as _genai  # type: ignore
        _k = (os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'")
        if _k:
            _genai.configure(api_key=_k)
        genai = _genai
        return True
    except Exception as e:
        print("[assist] ensure_sdk error:", e)
        return False


router = APIRouter(prefix="/api/assist", tags=["assist"])


class QAReq(BaseModel):
    question: str
    center: Optional[List[float]] = None  # [lat,lng]
    radius_mi: Optional[float] = 5.0


_cache: Dict[str, Any] = {}
_ttl = int(os.getenv("ASSIST_CACHE_TTL", "900"))  # seconds
_rl: Dict[str, float] = {}
_rl_window = 8.0  # seconds between requests per client
_llm_cooldown_until: float = 0.0
_llm_cooldown_sec = float(os.getenv("ASSIST_LLM_COOLDOWN_SEC", "1800"))
_disable_llm = (os.getenv("ASSIST_DISABLE_LLM", "false").lower() in ("1","true","yes"))

_MODEL = (os.getenv("GEMINI_MODEL") or "gemini-1.5-flash").strip()


def _resp_to_json(resp) -> Dict[str, Any]:
    """Best-effort conversion of Gemini response to JSON dict."""
    # Try direct .text → JSON
    try:
        txt = getattr(resp, "text", None)
        if isinstance(txt, str) and txt.strip():
            try:
                return json.loads(txt)
            except Exception:
                # Not JSON; wrap as answer
                return {"answer": txt}
    except Exception:
        pass
    # Try candidates content
    try:
        cands = getattr(resp, "candidates", None) or []
        if cands:
            first = cands[0]
            content = getattr(first, "content", None)
            parts = getattr(content, "parts", None) or []
            if parts and hasattr(parts[0], "text"):
                raw = parts[0].text
                try:
                    return json.loads(raw)
                except Exception:
                    return {"answer": raw}
    except Exception:
        pass
    # Last resort
    return {"answer": ""}


def _cache_get(key: str):
    v = _cache.get(key)
    if not v:
        return None
    if time.time() - v[0] > _ttl:
        _cache.pop(key, None)
        return None
    return v[1]


def _cache_set(key: str, val: Any):
    _cache[key] = (time.time(), val)


def _sha(s: str) -> str:
    import hashlib
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _classifier_model():
    if not genai:
        raise HTTPException(500, "LLM not configured")
    return genai.GenerativeModel(
        _MODEL,
        generation_config={
            "temperature": 0.1,
            "top_p": 0.1,
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "enum": ["pins","shelters","food","flood","feed311","summary","other"]},
                    "needs_clarification": {"type": "boolean"},
                    "followup_question": {"type": "string"},
                    "filters": {
                        "type": "object",
                        "properties": {
                            "center": {"type": "array", "items": {"type": "number"}},
                            "radius_mi": {"type": "number"},
                            "kind": {"type": "string", "enum": ["need","offer"]},
                            "categories": {"type": "array", "items": {"type": "string"}},
                            "time_window_hours": {"type": "number"},
                        },
                    },
                },
                "required": ["intent", "needs_clarification", "followup_question", "filters"],
            },
        },
    )


def _answerer_model():
    if not genai:
        raise HTTPException(500, "LLM not configured")
    return genai.GenerativeModel(
        _MODEL,
        generation_config={
            "temperature": 0.1,
            "top_p": 0.2,
            # use plain text to avoid strict schema errors; we wrap into JSON
            "response_mime_type": "text/plain",
        },
    )


async def _fetch_basic_context() -> Dict[str, Any]:
    base = os.getenv("SELF_BASE_URL", "http://127.0.0.1:8000")
    async with httpx.AsyncClient(base_url=base, timeout=10) as c:
        r1 = await c.get("/api/pins")
        r2 = await c.get("/api/shelters")
        r3 = await c.get("/api/food")
        r4 = await c.get("/api/311")
    return {"pins": r1.json(), "shelters": r2.json(), "food": r3.json(), "feed311": r4.json()}


def _clip_by_radius(items: List[Dict[str, Any]], center: Optional[List[float]], radius_mi: Optional[float], lat_key="lat", lng_key="lng") -> List[Dict[str, Any]]:
    if not center or not radius_mi:
        return items
    from math import radians, sin, cos, atan2, sqrt
    R = 3958.8
    clat, clng = center
    def dist(a, b):
        dphi = radians(a - clat)
        dl = radians(b - clng)
        p1, p2 = radians(clat), radians(a)
        x = sin(dphi/2)**2 + cos(p1) * cos(p2) * sin(dl/2)**2
        return 2 * R * atan2(sqrt(x), sqrt(1-x))
    return [it for it in items if dist(it.get(lat_key), it.get(lng_key)) <= radius_mi]


def _reduce_context(
    data: Dict[str, Any],
    intent: str,
    center: Optional[List[float]],
    radius_mi: Optional[float],
    kind: Optional[str] = None,
    categories: Optional[List[str]] = None,
    time_window_hours: Optional[float] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"intent": intent, "center": center, "radius_mi": radius_mi}
    if kind:
        out["kind"] = kind
    if categories:
        out["categories"] = categories
    if time_window_hours:
        out["time_window_hours"] = time_window_hours
    if intent in ("pins", "summary"):
        pins = data.get("pins") or []
        pins = pins[:200]
        pins = _clip_by_radius(pins, center, radius_mi)
        if kind in ("need","offer"):
            pins = [p for p in pins if (p.get("kind") == kind)]
        if categories:
            cats_lower = {c.lower() for c in categories}
            def has_cat(p):
                pc = [*(p.get("categories") or [])]
                return any((str(x).lower() in cats_lower) for x in pc)
            pins = [p for p in pins if has_cat(p)]
        out["pins"] = [{"id":p.get("id"),"kind":p.get("kind"),"categories":p.get("categories"),"lat":p.get("lat"),"lng":p.get("lng"),"created_at":p.get("created_at") } for p in pins]
    if intent in ("shelters", "summary"):
        sh = data.get("shelters") or []
        sh = sh[:200]
        sh = _clip_by_radius(sh, center, radius_mi)
        out["shelters"] = [{"name":s.get("name"),"lat":s.get("lat"),"lng":s.get("lng"),"capacity":s.get("capacity"),"type":s.get("type") } for s in sh]
    if intent in ("food", "summary"):
        fd = data.get("food") or []
        fd = fd[:200]
        fd = _clip_by_radius(fd, center, radius_mi)
        out["food"] = [{"name":f.get("name"),"lat":f.get("lat"),"lng":f.get("lng"),"kind":f.get("kind"),"status":f.get("status") } for f in fd]
    if intent in ("feed311", "summary"):
        geo = data.get("feed311") or {}
        feats = (geo.get("features") or [])[:150]
        simple = []
        for f in feats:
            g = f.get("geometry") or {}
            props = f.get("properties") or {}
            if (g.get("type") == "Point"):
                lng, lat = g.get("coordinates") or [None, None]
                simple.append({"lat": lat, "lng": lng, "category": props.get("category"), "updated": props.get("updated")})
        simple = _clip_by_radius(simple, center, radius_mi)
        if time_window_hours:
            try:
                horizon_ms = time_window_hours * 3600 * 1000
                now_ms = int(time.time() * 1000)
                def within(p):
                    try:
                        ts = int(p.get("updated") or 0)
                        return (now_ms - ts) <= horizon_ms
                    except Exception:
                        return True
                simple = [p for p in simple if within(p)]
            except Exception:
                pass
        out["feed311"] = simple
    return out


@router.post("/qna")
async def qna(req: QAReq, request: Request):
    # simple per-client rate limit
    try:
        k = request.client.host if request and request.client else "global"
        now = time.time()
        last = _rl.get(k, 0)
        if now - last < _rl_window:
            return await _fallback(f"client rate-limited {int(_rl_window - (now - last))}s")
        _rl[k] = now
    except Exception:
        pass
    async def _fallback(reason: str = "") -> Dict[str, Any]:
        try:
            data = await _fetch_basic_context()
            ctx = _reduce_context(data, "summary", req.center, req.radius_mi)
            pins = len(ctx.get("pins") or [])
            shelters = len(ctx.get("shelters") or [])
            food = len(ctx.get("food") or [])
            feed = len(ctx.get("feed311") or [])
            ans = f"In view: {pins} pins, {shelters} shelters, {food} food sites, {feed} 311 points."
            res = {"mode": "fallback", "answer": ans, "support": {"counts": {"pins": pins, "shelters": shelters, "food": food, "feed311": feed}}}
            if reason:
                res["reason"] = reason
            return res
        except Exception as e:
            print("[assist] fallback error:", e)
            raise HTTPException(502, f"fallback error: {e}")

    # LLM availability (we can still continue with a local classifier if not available)
    now_ts = time.time()
    llm_ok = (not _disable_llm) and (now_ts >= _llm_cooldown_until) and bool((os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'")) and _ensure_sdk_loaded()

    # Normalize cache key to improve hit rate across near-identical requests
    def _round_or_none(x, n=2):
        try:
            return round(float(x), n)
        except Exception:
            return None
    qnorm = re.sub(r"\s+", " ", (req.question or "").strip().lower())
    c_round = [
        _round_or_none((req.center or [None, None])[0], 2),
        _round_or_none((req.center or [None, None])[1], 2),
    ] if req.center else None
    r_round = _round_or_none(req.radius_mi or 5, 1)
    key = _sha(json.dumps({"q": qnorm, "c": c_round, "r": r_round}))
    cached = _cache_get(key)
    if cached:
        return cached

    # Step 1: classify (LLM if available; otherwise local heuristic)
    def _local_classify(q: str) -> Dict[str, Any]:
        text = (q or "").lower().strip()
        # radius parsing: "within 2 miles/mi"
        rmatch = re.search(r"within\s+(\d+(?:\.\d+)?)\s*(?:miles|mi)", text)
        radius = float(rmatch.group(1)) if rmatch else (req.radius_mi or 5)
        # time window: "last 2 hours", "past 24h"
        tmatch = re.search(r"(?:last|past)\s+(\d+)\s*(minutes|min|hours|hrs|days|d)\b", text)
        twh = None
        if tmatch:
            n = int(tmatch.group(1))
            unit = tmatch.group(2)
            if unit.startswith("min"):
                twh = max(1, round(n / 60))
            elif unit.startswith("hour") or unit.startswith("hr"):
                twh = n
            else:
                twh = n * 24
        # categories mapping
        cat_map = {
            "meals": "Meals", "food": "Food", "pantry": "Food", "beds": "Beds", "shelter": "Shelter",
            "medical": "Medical", "medicine": "Medical", "transport": "Transport", "ride": "Transport",
            "supplies": "Supplies", "water": "Supplies"
        }
        cats = []
        for key, val in cat_map.items():
            if key in text and val not in cats:
                cats.append(val)
        # intent
        intent = "summary"
        kind = None
        if any(k in text for k in ["311", "service request", "non-emergency"]):
            intent = "feed311"
        elif any(k in text for k in ["shelter", "shelters"]):
            intent = "shelters"
        elif any(k in text for k in ["food", "pantry", "meal", "meals"]):
            intent = "food"
        elif any(k in text for k in ["flood", "floodplain", "fema", "dfirm"]):
            intent = "flood"
        elif any(k in text for k in ["offer", "offering help", "who is offering", "who offers"]):
            intent = "pins"; kind = "offer"
        elif any(k in text for k in ["need", "needs help", "who needs"]):
            intent = "pins"; kind = "need"
        elif "pin" in text:
            intent = "pins"
        needs_clar = intent == "summary"
        follow = "What would you like to know: shelters, food, flood zones, 311, or community pins?" if needs_clar else ""
        filters = {"center": req.center, "radius_mi": radius}
        if kind:
            filters["kind"] = kind
        if cats:
            filters["categories"] = cats
        if twh:
            filters["time_window_hours"] = twh
        return {"intent": intent, "needs_clarification": needs_clar, "followup_question": follow, "filters": filters}

    # Try classifier cache first (based on normalized inputs)
    clf_cache_key = _sha(json.dumps({"clf": True, "q": qnorm, "c": c_round, "r": r_round}))
    clf_out = _cache_get(clf_cache_key)
    if llm_ok and not clf_out:
        try:
            clf = _classifier_model()
            instructions = (
                "You are an intent router for a disaster‑help map. OUTPUT JSON ONLY.\n"
                "Allowed intents: pins, shelters, food, flood, feed311, summary, other.\n"
                "Routing rules:\n"
                "- If the question is a greeting/small talk or too vague (no clear topic), set needs_clarification=true and followup_question like: \"What would you like to know: shelters, food, flood zones, 311, or community pins?\"\n"
                "- Otherwise set needs_clarification=false and choose ONE primary intent.\n"
                "- Map synonyms: flood zone/floodplain/FEMA/DFIRM → flood; food bank/meal distribution → food.\n"
                "- Phrases like 'who is offering help' → intent=pins, filters.kind='offer'. 'who needs help' → intent=pins, filters.kind='need'.\n"
                "- Build filters. If center/radius are missing, use the provided Defaults. If user says \"near me\", keep Defaults.\n"
                "- time_window_hours only when user asks about recency (e.g., last 24h).\n"
                "- categories only when the user specifies them (e.g., meals, beds).\n"
                "Do not answer the question. JSON only."
            )
            clf_raw = clf.generate_content(f"{instructions}\nUser: {req.question}\nDefaults: center={req.center}, radius_mi={req.radius_mi}")
            clf_out = _resp_to_json(clf_raw)
            _cache_set(clf_cache_key, clf_out)
        except Exception as e:
            # If rate-limited, set cooldown to stop calling LLM for a while
            msg = str(e)
            if "429" in msg or "quota" in msg.lower():
                globals()["_llm_cooldown_until"] = time.time() + _llm_cooldown_sec
            print("[assist] classifier error, falling back to local:", e)
            clf_out = _local_classify(req.question)
    elif not clf_out:
        clf_out = _local_classify(req.question)

    if clf_out.get("needs_clarification"):
        res = {"ask": clf_out.get("followup_question") or "What resource are you asking about?"}
        _cache_set(key, res)
        return res

    intent = clf_out.get("intent") or "summary"
    filters = clf_out.get("filters") or {}
    center = filters.get("center") or req.center
    radius = filters.get("radius_mi") or req.radius_mi
    filter_kind = (filters.get("kind") or "").strip().lower() or None
    filter_categories = filters.get("categories") or None
    time_window_hours = filters.get("time_window_hours") or None

    # Step 2: fetch + reduce context
    try:
        data = await _fetch_basic_context()
    except Exception as e:
        print("[assist] fetch context error:", e)
        return await _fallback(f"context error: {e}")
    context = _reduce_context(data, intent, center, radius, filter_kind, filter_categories, time_window_hours)

    # Deterministic answers for known intents to avoid bland/fallback results
    def haversine_mi(a,b,c,d):
        from math import radians, sin, cos, atan2, sqrt
        R=3958.8
        p1=radians(a); p2=radians(c)
        dphi=radians(c-a); dl=radians(d-b)
        x=sin(dphi/2)**2+cos(p1)*cos(p2)*sin(dl/2)**2
        return 2*R*atan2(sqrt(x),sqrt(1-x))

    def nearest(items, maxn=3, lat_key="lat", lng_key="lng"):
        if not (center and isinstance(center, list) and len(center)==2):
            return items[:maxn]
        lat0,lng0=center
        for it in items:
            try:
                it["_d"] = round(haversine_mi(lat0,lng0,float(it.get(lat_key)),float(it.get(lng_key))),2)
            except Exception:
                it["_d"] = None
        items.sort(key=lambda x: (x.get("_d") is None, x.get("_d") or 1e9))
        return items[:maxn]

    def compose(context: Dict[str,Any]) -> Dict[str, Any]:
        it = context.get("intent")
        rad = context.get("radius_mi")
        suggestion = " Try zooming in or increasing the radius for more results."
        if it == "pins":
            items = context.get("pins") or []
            k = context.get("kind")
            if k:
                items = [p for p in items if p.get("kind")==k]
            if not items:
                ans = f"No {'offers' if k=='offer' else 'needs' if k=='need' else 'pins'} found in this view." + suggestion
                return {"title": "No results", "subtitle": ans, "items": [], "answer": ans}
            top = nearest(items)
            bullets = []
            for p in top:
                cats = ", ".join((p.get("categories") or [])[:2]) or (p.get("kind") or "")
                bullets.append({
                    "label": f"{p.get('kind').title()}: {cats}",
                    "distance_mi": p.get("_d"),
                    "id": p.get("id"),
                    "lat": p.get("lat"),
                    "lng": p.get("lng"),
                    "kind": p.get("kind"),
                    "type": "pin"
                })
            title = f"{('Offers' if k=='offer' else 'Needs' if k=='need' else 'Pins')} nearby: {len(items)}"
            subtitle = f"Within ~{rad} mi"
            ans = title + "\n" + "\n".join([f"- {b['label']} · {b['distance_mi']} mi" if b.get('distance_mi') is not None else f"- {b['label']}" for b in bullets])
            return {"title": title, "subtitle": subtitle, "items": bullets, "answer": ans}
        if it == "shelters":
            items = context.get("shelters") or []
            if not items:
                ans = "No shelters found in this view." + suggestion
                return {"title": "No results", "subtitle": ans, "items": [], "answer": ans}
            top = nearest(items)
            bullets = [{"label": s.get('name') or 'Shelter', "distance_mi": s.get('_d'), "lat": s.get('lat'), "lng": s.get('lng'), "type": "shelter"} for s in top]
            title = f"Shelters nearby: {len(items)}"
            subtitle = f"Within ~{rad} mi"
            ans = title + "\n" + "\n".join([f"- {b['label']} · {b['distance_mi']} mi" if b.get('distance_mi') is not None else f"- {b['label']}" for b in bullets])
            return {"title": title, "subtitle": subtitle, "items": bullets, "answer": ans}
        if it == "food":
            items = context.get("food") or []
            if not items:
                ans = "No food/supply sites found in this view." + suggestion
                return {"title": "No results", "subtitle": ans, "items": [], "answer": ans}
            top = nearest(items)
            bullets = [{"label": f.get('name') or 'Food site', "distance_mi": f.get('_d'), "lat": f.get('lat'), "lng": f.get('lng'), "type": "food"} for f in top]
            title = f"Food/supply nearby: {len(items)}"
            subtitle = f"Within ~{rad} mi"
            ans = title + "\n" + "\n".join([f"- {b['label']} · {b['distance_mi']} mi" if b.get('distance_mi') is not None else f"- {b['label']}" for b in bullets])
            return {"title": title, "subtitle": subtitle, "items": bullets, "answer": ans}
        if it == "feed311":
            items = context.get("feed311") or []
            if not items:
                ans = "No 311 reports in this view." + suggestion
                return {"title": "No results", "subtitle": ans, "items": [], "answer": ans}
            cats = {}
            for x in items:
                cats[x.get('category') or 'Other'] = cats.get(x.get('category') or 'Other',0)+1
            topcats = ", ".join(f"{k}:{v}" for k,v in list(sorted(cats.items(), key=lambda kv:-kv[1]))[:3])
            top = nearest(items)
            bullets = [{"label": x.get('category') or '311 report', "distance_mi": x.get('_d'), "lat": x.get('lat'), "lng": x.get('lng'), "type": "311"} for x in top]
            title = f"311 nearby: {len(items)} reports"
            subtitle = f"Top: {topcats}" if topcats else "Within view"
            ans = f"311 points: {len(items)} (top: {topcats}).\n" + "\n".join([f"- {b['label']} · {b['distance_mi']} mi" if b.get('distance_mi') is not None else f"- {b['label']}" for b in bullets])
            return {"title": title, "subtitle": subtitle, "items": bullets, "answer": ans}
        # summary or other
        pins = len(context.get("pins") or [])
        sh = len(context.get("shelters") or [])
        fd = len(context.get("food") or [])
        f3 = len(context.get("feed311") or [])
        ans = f"In view: {pins} pins, {sh} shelters, {fd} food sites, {f3} 311 points."
        return {"title": "Summary", "subtitle": "Visible resources", "items": [
            {"label": f"Pins: {pins}"}, {"label": f"Shelters: {sh}"}, {"label": f"Food sites: {fd}"}, {"label": f"311: {f3}"}
        ], "answer": ans}

    ui = compose(context)
    answer_text = ui.get("answer") or ""
    res = {"mode": "deterministic", "answer": answer_text[:700], "ui": {"title": ui.get("title"), "subtitle": ui.get("subtitle"), "items": ui.get("items", [])}}
    _cache_set(key, res)
    return res

@router.get("/status")
async def status() -> Dict[str, Any]:
    has_key = bool((os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'"))
    sdk_loaded = _ensure_sdk_loaded()
    try:
        import importlib.util
        spec = importlib.util.find_spec("google.generativeai")
        mod_found = spec is not None
    except Exception:
        mod_found = False
    return {
        "has_key": has_key,
        "sdk_loaded": sdk_loaded,
        "self_base_url": os.getenv("SELF_BASE_URL", "http://127.0.0.1:8000"),
        "python": sys.executable,
        "module_found": mod_found,
    }



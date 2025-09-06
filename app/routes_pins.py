from datetime import datetime, timedelta, timezone
from typing import List, Optional

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .models import PinCreate, PinOut, CommentCreate, CommentOut
from .db import get_db_url
from .moderation import rate_limit, redact_profanity


router = APIRouter(prefix="/api", tags=["pins"])


async def get_conn():
    conn = await psycopg.AsyncConnection.connect(get_db_url())
    try:
        yield conn
    finally:
        await conn.close()


@router.get("/pins", response_model=List[PinOut])
async def list_pins(
    kinds: Optional[str] = Query(None, description="Comma list: need,offer"),
    categories: Optional[str] = None,
    since: Optional[datetime] = None,
    center: Optional[str] = Query(None, description="lat,lng for distance calc"),
    radius: Optional[float] = Query(None, description="miles; if provided with center, filter within"),
    conn: psycopg.AsyncConnection = Depends(get_conn),
):
    kind_list = kinds.split(",") if kinds else ["need", "offer"]
    cat_list = categories.split(",") if categories else None

    base_sql = """
        select id::text, kind, categories, title, body, lat, lng, urgency, author_anon_id, created_at, expires_at
        from pins
        where is_hidden = false
          and expires_at > now()
          and kind = any(%s)
    """
    params: List = [kind_list]
    if cat_list:
        base_sql += " and categories && %s"
        params.append(cat_list)
    if since:
        base_sql += " and created_at > %s"
        params.append(since)
    base_sql += " order by created_at desc limit 500"

    async with conn.cursor() as cur:
        await cur.execute(base_sql, params)
        rows = await cur.fetchall()

    results: List[PinOut] = []
    center_lat, center_lng = (None, None)
    if center:
        try:
            center_lat, center_lng = [float(x) for x in center.split(",")]
        except Exception:
            pass
    for r in rows:
        item = PinOut(
            id=r[0], kind=r[1], categories=r[2], title=r[3], body=r[4], lat=r[5], lng=r[6], urgency=r[7], author_anon_id=r[8], created_at=r[9], expires_at=r[10]
        )
        results.append(item)

    # Optional radius filtering in app if center provided (simple Haversine-ish approximation)
    if center and radius:
        import math

        def dist_mi(lat1, lon1, lat2, lon2):
            R = 3958.8
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)
            a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
            return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        filtered: List[PinOut] = []
        for p in results:
            d = dist_mi(center_lat, center_lng, p.lat, p.lng)
            if d <= radius:
                p.distance_mi = round(d, 2)
                filtered.append(p)
        results = filtered

    return results


@router.post("/pins", response_model=PinOut)
async def create_pin(payload: PinCreate, request: Request, conn: psycopg.AsyncConnection = Depends(get_conn)):
    # Rate limit create
    rate_limit(request, key="create_pin", max_per_minute=3)
    # Redact profanity
    payload.body = redact_profanity(payload.body)
    expires = datetime.now(timezone.utc) + timedelta(hours=48)
    sql = """
        insert into pins (kind, categories, title, body, lat, lng, author_anon_id, urgency, expires_at)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        returning id::text, kind, categories, title, body, lat, lng, urgency, author_anon_id, created_at, expires_at
    """
    async with conn.cursor() as cur:
        await cur.execute(
            sql,
            [payload.kind, payload.categories, payload.title, payload.body, payload.lat, payload.lng, payload.author_anon_id, payload.urgency, expires],
        )
        row = await cur.fetchone()
        await conn.commit()
    return PinOut(
        id=row[0], kind=row[1], categories=row[2], title=row[3], body=row[4], lat=row[5], lng=row[6], urgency=row[7], author_anon_id=row[8], created_at=row[9], expires_at=row[10]
    )


@router.get("/pins/{pin_id}/comments", response_model=List[CommentOut])
async def list_comments(pin_id: str, conn: psycopg.AsyncConnection = Depends(get_conn)):
    sql = """
        select id::text, pin_id::text, body, created_at
        from comments
        where pin_id = %s and is_hidden = false
        order by created_at asc
        limit 500
    """
    async with conn.cursor() as cur:
        await cur.execute(sql, [pin_id])
        rows = await cur.fetchall()
    return [CommentOut(id=r[0], pin_id=r[1], body=r[2], created_at=r[3]) for r in rows]


@router.post("/pins/{pin_id}/comments", response_model=CommentOut)
async def create_comment(pin_id: str, payload: CommentCreate, request: Request, conn: psycopg.AsyncConnection = Depends(get_conn)):
    # Rate limit comments
    rate_limit(request, key="create_comment", max_per_minute=6)
    payload.body = redact_profanity(payload.body)
    # ensure pin exists and visible
    async with conn.cursor() as cur:
        await cur.execute("select 1 from pins where id=%s and is_hidden=false", [pin_id])
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Pin not found")
    sql = """
        insert into comments (pin_id, body, author_anon_id)
        values (%s,%s,%s)
        returning id::text, pin_id::text, body, created_at
    """
    async with conn.cursor() as cur:
        await cur.execute(sql, [pin_id, payload.body, payload.author_anon_id])
        row = await cur.fetchone()
        await conn.commit()
    return CommentOut(id=row[0], pin_id=row[1], body=row[2], created_at=row[3])


@router.post("/pins/{pin_id}/report")
async def report_pin(pin_id: str, conn: psycopg.AsyncConnection = Depends(get_conn)):
    async with conn.cursor() as cur:
        await cur.execute("update pins set is_hidden=true where id=%s", [pin_id])
        await conn.commit()
    return {"ok": True}


@router.post("/pins/{pin_id}/dismiss")
async def dismiss_pin(pin_id: str, author_anon_id: str, conn: psycopg.AsyncConnection = Depends(get_conn)):
    async with conn.cursor() as cur:
        await cur.execute("update pins set is_hidden=true where id=%s and author_anon_id=%s", [pin_id, author_anon_id])
        count = cur.rowcount
        await conn.commit()
    if count == 0:
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"ok": True}



import re
import time
from typing import Dict
from fastapi import HTTPException, Request


_bad_words = {"fuck","shit","bitch","asshole","bastard"}
_regex = re.compile(r"(" + r"|".join(re.escape(w) for w in _bad_words) + r")", re.IGNORECASE)


def redact_profanity(text: str) -> str:
    return _regex.sub(lambda m: m.group(0)[0] + "***", text)


_buckets: Dict[str, Dict[str, float]] = {}


def rate_limit(request: Request, key: str, max_per_minute: int) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket_key = f"{ip}:{key}"
    window = 60.0
    bucket = _buckets.get(bucket_key)
    if not bucket:
        _buckets[bucket_key] = {"count": 1, "ts": now}
        return
    if now - bucket["ts"] > window:
        _buckets[bucket_key] = {"count": 1, "ts": now}
        return
    if bucket["count"] >= max_per_minute:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket["count"] += 1



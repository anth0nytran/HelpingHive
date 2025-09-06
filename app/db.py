import os
from pathlib import Path

import psycopg


BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"


def get_db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


async def init_db() -> None:
    db_url = get_db_url()
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        async with conn.cursor() as cur:
            await cur.execute(schema_sql)
        await conn.commit()



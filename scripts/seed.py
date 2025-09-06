import asyncio
import os
from datetime import datetime, timedelta, timezone
import random
import json
from dotenv import load_dotenv

import psycopg


NEEDS = [
    ("need", ["Food"], "Food needed", "Looking for meals and water", 29.75, -95.36),
    ("need", ["Shelter"], "Shelter needed", "Family of 3 needs shelter", 29.77, -95.38),
]

OFFERS = [
    ("offer", ["Meals"], "Free meals", "Offering hot meals", 29.73, -95.37),
    ("offer", ["Transport"], "Rides available", "Can transport to shelters", 29.78, -95.39),
]


async def main():
    # load .env so DATABASE_URL is available when not set in shell
    load_dotenv()
    db_url = os.environ["DATABASE_URL"]
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        async with conn.cursor() as cur:
            # load mock pins if available
            try:
                root = os.path.dirname(os.path.dirname(__file__))
                mock_path = os.path.join(root, 'data', 'pins_mock.json')
                if os.path.exists(mock_path):
                    mock = json.load(open(mock_path, 'r', encoding='utf-8'))
                    for m in mock:
                        expires = datetime.now(timezone.utc) + timedelta(hours=48)
                        await cur.execute(
                            """
                            insert into pins (kind, categories, title, body, lat, lng, author_anon_id, expires_at)
                            values (%s,%s,%s,%s,%s,%s,%s,%s)
                            on conflict do nothing
                            """,
                            [m['kind'], m['categories'], m.get('title'), m['body'], m['lat'], m['lng'], f"seed-{random.randint(100,999)}", expires],
                        )
            except Exception:
                pass
            for kind, cats, title, body, lat, lng in NEEDS + OFFERS:
                expires = datetime.now(timezone.utc) + timedelta(hours=48)
                await cur.execute(
                    """
                    insert into pins (kind, categories, title, body, lat, lng, author_anon_id, expires_at)
                    values (%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict do nothing
                    """,
                    [kind, cats, title, body, lat, lng, f"seed-{random.randint(100,999)}", expires],
                )
        await conn.commit()
    print("Seeded pins.")


if __name__ == "__main__":
    asyncio.run(main())



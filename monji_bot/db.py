# monji_bot/db.py

import asyncpg
from typing import Optional
from .config import DB_USER, DB_PASS, DB_NAME, DB_HOST, DB_PORT, DB_ENABLE_SSL

_pool: Optional[asyncpg.Pool] = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool

    if not DB_PASS or not DB_NAME:
        raise ValueError("DB_PASS or DB_NAME missing in environment")

    _pool = await asyncpg.create_pool(
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        host=DB_HOST,
        port=DB_PORT,
        ssl=DB_ENABLE_SSL,
    )
    print("✅ Database pool created")
    return _pool


async def init_schema() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS questions (
                id SERIAL PRIMARY KEY,
                source TEXT,
                external_id TEXT,
                category TEXT,
                difficulty TEXT,
                question TEXT NOT NULL,
                correct_answers JSON,
                incorrect_answers JSON,
                approved BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
        )
        print("✅ Schema created / already existed")

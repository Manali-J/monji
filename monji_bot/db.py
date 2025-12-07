# monji_bot/db.py
import asyncio

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
        # Existing questions table
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
                created_at TIMESTAMP DEFAULT NOW(),
                times_asked INTEGER DEFAULT 0
            );
            """
        )

        # ⭐ New: leaderboard storage
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_scores (
                guild_id     BIGINT      NOT NULL,
                user_id      BIGINT      NOT NULL,
                display_name TEXT,
                score_total  INTEGER     NOT NULL DEFAULT 0,
                last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_user_scores_guild_score_desc
                ON user_scores (guild_id, score_total DESC, last_updated ASC);
            """
        )

        print("✅ Schema created / already existed")


# ⭐ New: award points to a user
async def award_points(
    guild_id: int,
    user_id: int,
    display_name: str,
    points: int,
) -> None:
    """Add `points` to this user's score in this guild."""
    if points <= 0:
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_scores (guild_id, user_id, display_name, score_total, last_updated)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (guild_id, user_id)
            DO UPDATE SET
                score_total  = user_scores.score_total + EXCLUDED.score_total,
                display_name = EXCLUDED.display_name,
                last_updated = NOW();
            """,
            guild_id,
            user_id,
            display_name,
            points,
        )


# ⭐ New: get top N for a guild
async def get_leaderboard(guild_id: int, limit: int = 10):
    """Return top `limit` users for this guild, ordered by score."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT user_id, display_name, score_total
            FROM user_scores
            WHERE guild_id = $1
            ORDER BY score_total DESC, last_updated ASC
            LIMIT $2;
            """,
            guild_id,
            limit,
        )
    return rows


# ⭐ New: get rank + score for one user
async def get_user_rank(guild_id: int, user_id: int):
    """
    Return (rank, score_total) for this user in this guild,
    or None if they have no score yet.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT rank, score_total
            FROM (
                SELECT
                    user_id,
                    score_total,
                    RANK() OVER (ORDER BY score_total DESC, last_updated ASC) AS rank
                FROM user_scores
                WHERE guild_id = $1
            ) AS ranked
            WHERE user_id = $2;
            """,
            guild_id,
            user_id,
        )

    if row is None:
        return None

    return row["rank"], row["score_total"]

#run init_schema only
if __name__ == "__main__":
    init_schema()

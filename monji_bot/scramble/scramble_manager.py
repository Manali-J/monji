"""
Scramble word selector (single-session).

Behavior:
- Prefer approved words with times_asked = 0 and not used in this session
- Fallback to times_asked = 0 (any)
- Then fallback to least times_asked, avoiding session repeats
- Finally fallback to least times_asked (any)
- Increment times_asked immediately (inside same transaction)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional, Set

from ..db import get_pool

logger = logging.getLogger(__name__)

ScrambleWord = Dict[str, object]

# Track words used in the current scramble session
_used_in_session: Set[int] = set()

# Serialize DB access
_scramble_lock = asyncio.Lock()


def reset_scramble_session() -> None:
    """Call this when a new /scramble game starts."""
    _used_in_session.clear()
    logger.info("Scramble session reset")


# -----------------------------
# SQL (Postgres)
# -----------------------------

_SQL_ZERO_NOT_USED = """
SELECT id, word
FROM scramble_words
WHERE approved = TRUE
  AND times_asked = 0
  AND id <> ALL($1::int[])
ORDER BY RANDOM()
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

_SQL_ZERO_ANY = """
SELECT id, word
FROM scramble_words
WHERE approved = TRUE
  AND times_asked = 0
ORDER BY RANDOM()
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

_SQL_LEAST_NOT_USED = """
SELECT id, word
FROM scramble_words
WHERE approved = TRUE
  AND id <> ALL($1::int[])
ORDER BY times_asked ASC, RANDOM()
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

_SQL_LEAST_ANY = """
SELECT id, word
FROM scramble_words
WHERE approved = TRUE
ORDER BY times_asked ASC, RANDOM()
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

_SQL_INCREMENT = """
UPDATE scramble_words
SET times_asked = times_asked + 1
WHERE id = $1
"""


async def _fetchrow(conn, sql: str, params=None):
    """Helper to call fetchrow with or without params."""
    if params is not None:
        return await conn.fetchrow(sql, params)
    return await conn.fetchrow(sql)


async def get_random_scramble_word() -> Optional[ScrambleWord]:
    """
    Fetch a scramble word according to rotation rules.

    Returns:
        { "id": int, "word": str } or None if no approved rows exist
    """
    async with _scramble_lock:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                used_list = list(_used_in_session)

                attempts = []

                if used_list:
                    attempts.append((_SQL_ZERO_NOT_USED, used_list))
                attempts.append((_SQL_ZERO_ANY, None))

                if used_list:
                    attempts.append((_SQL_LEAST_NOT_USED, used_list))
                attempts.append((_SQL_LEAST_ANY, None))

                row = None
                for sql, params in attempts:
                    try:
                        row = await _fetchrow(conn, sql, params)
                    except Exception:
                        logger.exception(
                            "Scramble selection query failed; continuing. SQL head: %s",
                            sql.splitlines()[0].strip(),
                        )
                        row = None

                    if row:
                        break

                if not row:
                    logger.debug("No approved scramble words found.")
                    return None

                word_id = row["id"]
                word = row["word"]

                # Mark used in session
                _used_in_session.add(word_id)

                # Increment times_asked immediately
                await conn.execute(_SQL_INCREMENT, word_id)

    logger.debug(
        "Selected scramble word id=%s word=%s",
        word_id,
        word,
    )

    return {
        "id": word_id,
        "word": word,
    }

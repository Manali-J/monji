"""
Scramble word selector (single-session, guild-aware).

Behavior:
- Prefer words never used in THIS guild
- Auto-relax to least-used per guild
- Break ties using global times_asked
- Avoid repeats within the same session
- Selection + increments are atomic
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
    _used_in_session.clear()
    logger.info("Scramble session reset")


# -----------------------------
# SQL
# -----------------------------

_SQL_PICK = """
SELECT w.id, w.word
FROM scramble_words w
WHERE w.approved = TRUE
  AND ( $2::int[] IS NULL OR w.id <> ALL($2::int[]) )
ORDER BY
  (
    SELECT COALESCE(u.times_asked, 0)
    FROM scramble_usage u
    WHERE u.word_id = w.id
      AND u.guild_id = $1
  ) ASC,
  w.times_asked ASC,
  RANDOM()
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

_SQL_INCREMENT_GLOBAL = """
UPDATE scramble_words
SET times_asked = times_asked + 1
WHERE id = $1
"""

_SQL_INCREMENT_GUILD = """
INSERT INTO scramble_usage (guild_id, word_id, times_asked, last_asked_at)
VALUES ($1, $2, 1, NOW())
ON CONFLICT (guild_id, word_id)
DO UPDATE SET
  times_asked = scramble_usage.times_asked + 1,
  last_asked_at = NOW()
"""


# -----------------------------
# Public API
# -----------------------------

async def get_random_scramble_word(guild_id: int) -> Optional[ScrambleWord]:
    """
    Fetch a scramble word for a guild.

    Returns:
        { "id": int, "word": str } or None
    """
    async with _scramble_lock:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():

                used_list = list(_used_in_session) if _used_in_session else None

                row = await conn.fetchrow(
                    _SQL_PICK,
                    guild_id,
                    used_list,
                )

                if not row:
                    logger.debug("No approved scramble words found.")
                    return None

                word_id = row["id"]
                word = row["word"]

                _used_in_session.add(word_id)

                # global increment
                await conn.execute(_SQL_INCREMENT_GLOBAL, word_id)

                # per-guild increment
                await conn.execute(
                    _SQL_INCREMENT_GUILD,
                    guild_id,
                    word_id,
                )

    logger.debug("Selected scramble word id=%s word=%s", word_id, word)

    return {
        "id": word_id,
        "word": word,
    }

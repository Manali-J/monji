"""
Scramble word selector (guild-aware, DB-safe).

Behavior:
- Prefer words never used in THIS guild
- Auto-relax to least-used per guild
- Break ties using global times_asked
- Avoid repeats via DB cooldown window
- Selection + increments are atomic
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from ..db import get_pool

logger = logging.getLogger(__name__)

ScrambleWord = Dict[str, object]

# Serialize DB access (per process)
_scramble_lock = asyncio.Lock()

# -----------------------------
# SQL
# -----------------------------

_SQL_PICK = """
SELECT w.id, w.word
FROM scramble_words w
WHERE w.approved = TRUE

  -- Avoid recently-used words in this guild
  AND NOT EXISTS (
    SELECT 1
    FROM scramble_usage u
    WHERE u.guild_id = $1
      AND u.word_id = w.id
      AND u.last_asked_at > NOW() - INTERVAL '30 minutes'
  )

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

                row = await conn.fetchrow(
                    _SQL_PICK,
                    guild_id,
                )

                if not row:
                    logger.debug(
                        "No eligible scramble words found for guild %s",
                        guild_id,
                    )
                    return None

                word_id = row["id"]
                word = row["word"]

                # global increment
                await conn.execute(
                    _SQL_INCREMENT_GLOBAL,
                    word_id,
                )

                # per-guild increment
                await conn.execute(
                    _SQL_INCREMENT_GUILD,
                    guild_id,
                    word_id,
                )

    logger.debug(
        "Selected scramble word id=%s word=%s guild=%s",
        word_id,
        word,
        guild_id,
    )

    return {
        "id": word_id,
        "word": word,
    }

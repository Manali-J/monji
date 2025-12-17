"""
Scramble word selector (session-aware, guild-safe).

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
import uuid
from typing import Dict, Optional

from ..db import get_pool

logger = logging.getLogger(__name__)

ScrambleWord = Dict[str, object]

_scramble_lock = asyncio.Lock()

# -----------------------------
# Session state (SAFE)
# -----------------------------

_current_session_id: Optional[str] = None


def reset_scramble_session() -> None:
    """
    Start a new scramble session.
    """
    global _current_session_id
    _current_session_id = str(uuid.uuid4())
    logger.info("New scramble session started: %s", _current_session_id)


# -----------------------------
# SQL
# -----------------------------

_SQL_PICK = """
SELECT w.id, w.word
FROM scramble_words w
WHERE w.approved = TRUE
  AND NOT EXISTS (
    SELECT 1
    FROM scramble_session_words s
    WHERE s.guild_id = $1
      AND s.session_id = $2
      AND s.word_id = w.id
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

_SQL_MARK_SESSION = """
INSERT INTO scramble_session_words (guild_id, session_id, word_id)
VALUES ($1, $2, $3)
ON CONFLICT DO NOTHING
"""

# -----------------------------
# Public API
# -----------------------------

async def get_random_scramble_word(guild_id: int) -> Optional[ScrambleWord]:
    global _current_session_id

    if _current_session_id is None:
        reset_scramble_session()

    async with _scramble_lock:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():

                row = await conn.fetchrow(
                    _SQL_PICK,
                    guild_id,
                    _current_session_id,
                )

                if not row:
                    logger.debug("No eligible scramble words for guild %s", guild_id)
                    return None

                word_id = row["id"]
                word = row["word"]

                await conn.execute(_SQL_INCREMENT_GLOBAL, word_id)
                await conn.execute(_SQL_INCREMENT_GUILD, guild_id, word_id)
                await conn.execute(
                    _SQL_MARK_SESSION,
                    guild_id,
                    _current_session_id,
                    word_id,
                )

    logger.debug(
        "Selected scramble word id=%s guild=%s session=%s",
        word_id,
        guild_id,
        _current_session_id,
    )

    return {"id": word_id, "word": word}

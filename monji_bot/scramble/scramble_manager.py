from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional, Set

from ..db import get_pool

logger = logging.getLogger(__name__)

ScrambleWord = Dict[str, object]

# Track words used per guild in the current session
_used_in_session: Dict[int, Set[int]] = {}

_scramble_lock = asyncio.Lock()


def reset_scramble_session(guild_id: Optional[int] = None) -> None:
    if guild_id is None:
        _used_in_session.clear()
    else:
        _used_in_session.pop(guild_id, None)


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


async def get_random_scramble_word(guild_id: int) -> Optional[ScrambleWord]:
    async with _scramble_lock:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():

                used = _used_in_session.setdefault(guild_id, set())
                used_list = list(used) if len(used) > 0 else None

                row = await conn.fetchrow(
                    _SQL_PICK,
                    guild_id,
                    used_list,
                )

                if not row:
                    return None

                word_id = row["id"]
                used.add(word_id)

                await conn.execute(_SQL_INCREMENT_GLOBAL, word_id)
                await conn.execute(_SQL_INCREMENT_GUILD, guild_id, word_id)

    return {
        "id": word_id,
        "word": row["word"],
    }

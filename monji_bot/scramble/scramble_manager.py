from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from ..db import get_pool

logger = logging.getLogger(__name__)

ScrambleWord = Dict[str, object]

_scramble_lock = asyncio.Lock()

# -----------------------------
# SQL
# -----------------------------

# 1️⃣ Pick an UNUSED word for this guild
_SQL_PICK_UNUSED = """
SELECT w.id, w.word
FROM scramble_words w
WHERE w.approved = TRUE
  AND NOT EXISTS (
    SELECT 1
    FROM scramble_usage u
    WHERE u.guild_id = $1
      AND u.word_id = w.id
  )
ORDER BY RANDOM()
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

# 2️⃣ Fallback: pick ANY word
_SQL_PICK_ANY = """
SELECT w.id, w.word
FROM scramble_words w
WHERE w.approved = TRUE
ORDER BY RANDOM()
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
# Compatibility (kept)
# -----------------------------

def reset_scramble_session(*args, **kwargs) -> None:
    # No session state anymore — kept to avoid breaking imports
    return

# -----------------------------
# Public API
# -----------------------------

async def get_random_scramble_word(guild_id: int) -> Optional[ScrambleWord]:
    async with _scramble_lock:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():

                # Step 1: try unused word
                row = await conn.fetchrow(
                    _SQL_PICK_UNUSED,
                    guild_id,
                )

                # Step 2: fallback to any word
                if not row:
                    row = await conn.fetchrow(_SQL_PICK_ANY)

                if not row:
                    return None

                word_id = row["id"]
                word = row["word"]

                await conn.execute(_SQL_INCREMENT_GLOBAL, word_id)
                await conn.execute(
                    _SQL_INCREMENT_GUILD,
                    guild_id,
                    word_id,
                )

    return {
        "id": word_id,
        "word": word,
    }

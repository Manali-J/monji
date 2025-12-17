"""
Trivia manager (single-session, guild-aware).

Behavior:
- Prefer questions least used in THIS guild.
- Break ties using global times_asked.
- Avoid repeats within the same session.
- Selection + increments are atomic.
- Uses FOR UPDATE SKIP LOCKED (Postgres-safe).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set

from ..db import get_pool

logger = logging.getLogger(__name__)

Question = Dict[str, Any]

# Tracks questions used in the current trivia session (per channel/session)
_used_in_session: Set[int] = set()

# Serialize DB access
_question_lock = asyncio.Lock()


def reset_session_questions() -> None:
    _used_in_session.clear()
    logger.info("Trivia session reset")


def stats_summary() -> Dict[str, int]:
    return {"used_count": len(_used_in_session)}


# -----------------------------
# SQL
# -----------------------------

_SQL_PICK = """
SELECT q.id, q.question, q.correct_answers
FROM questions q
WHERE q.approved = TRUE
  AND ( $2::int[] IS NULL OR q.id <> ALL($2::int[]) )
ORDER BY
  (
    SELECT COALESCE(u.times_asked, 0)
    FROM question_usage u
    WHERE u.question_id = q.id
      AND u.guild_id = $1
  ) ASC,
  q.times_asked ASC,
  RANDOM()
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

_SQL_INCREMENT_GLOBAL = """
UPDATE questions
SET times_asked = times_asked + 1
WHERE id = $1
"""

_SQL_INCREMENT_GUILD = """
INSERT INTO question_usage (guild_id, question_id, times_asked, last_asked_at)
VALUES ($1, $2, 1, NOW())
ON CONFLICT (guild_id, question_id)
DO UPDATE SET
  times_asked = question_usage.times_asked + 1,
  last_asked_at = NOW()
"""


# -----------------------------
# Helpers
# -----------------------------

def _parse_answers(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
            return [str(parsed)]
        except json.JSONDecodeError:
            return [raw]
    return [str(raw)]


# -----------------------------
# Public API
# -----------------------------

async def get_random_question(guild_id: int) -> Optional[Question]:
    """
    Pick a question for a guild.
    Fresh per-guild first, then global freshness.
    """
    async with _question_lock:
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
                    logger.debug("No question found")
                    return None

                qid = row["id"]
                _used_in_session.add(qid)

                # increment global
                await conn.execute(_SQL_INCREMENT_GLOBAL, qid)

                # increment per-guild
                await conn.execute(
                    _SQL_INCREMENT_GUILD,
                    guild_id,
                    qid,
                )

    answers = _parse_answers(row["correct_answers"])
    logger.debug("Selected question id=%s", qid)

    return {
        "id": qid,
        "question": row["question"],
        "answers": answers,
    }

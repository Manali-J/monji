from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set

from ..db import get_pool

logger = logging.getLogger(__name__)

Question = Dict[str, Any]

# Track questions per guild in the current session
_used_in_session: Dict[int, Set[int]] = {}

_question_lock = asyncio.Lock()


def reset_session_questions(guild_id: Optional[int] = None) -> None:
    if guild_id is None:
        _used_in_session.clear()
    else:
        _used_in_session.pop(guild_id, None)


def stats_summary() -> Dict[str, int]:
    return {"guilds_active": len(_used_in_session)}


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


async def get_random_question(guild_id: int) -> Optional[Question]:
    async with _question_lock:
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

                qid = row["id"]
                used.add(qid)

                await conn.execute(_SQL_INCREMENT_GLOBAL, qid)
                await conn.execute(_SQL_INCREMENT_GUILD, guild_id, qid)

    return {
        "id": qid,
        "question": row["question"],
        "answers": _parse_answers(row["correct_answers"]),
    }

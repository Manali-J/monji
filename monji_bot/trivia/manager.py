from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from ..db import get_pool

logger = logging.getLogger(__name__)

Question = Dict[str, Any]

_question_lock = asyncio.Lock()

# -----------------------------
# SQL
# -----------------------------

# 1️⃣ Pick an UNUSED question for this guild
_SQL_PICK_UNUSED = """
SELECT q.id, q.question, q.correct_answers
FROM questions q
WHERE q.approved = TRUE
  AND NOT EXISTS (
    SELECT 1
    FROM question_usage u
    WHERE u.guild_id = $1
      AND u.question_id = q.id
  )
ORDER BY RANDOM()
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

# 2️⃣ Fallback: pick ANY question
_SQL_PICK_ANY = """
SELECT q.id, q.question, q.correct_answers
FROM questions q
WHERE q.approved = TRUE
ORDER BY RANDOM()
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
# Compatibility (kept)
# -----------------------------

def reset_session_questions(*args, **kwargs) -> None:
    # No session state anymore — kept to avoid breaking imports
    return


def stats_summary() -> Dict[str, int]:
    return {}

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
    async with _question_lock:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():

                # Step 1: try unused question
                row = await conn.fetchrow(
                    _SQL_PICK_UNUSED,
                    guild_id,
                )

                # Step 2: fallback to any question
                if not row:
                    row = await conn.fetchrow(_SQL_PICK_ANY)

                if not row:
                    return None

                qid = row["id"]

                await conn.execute(_SQL_INCREMENT_GLOBAL, qid)
                await conn.execute(
                    _SQL_INCREMENT_GUILD,
                    guild_id,
                    qid,
                )

    return {
        "id": qid,
        "question": row["question"],
        "answers": _parse_answers(row["correct_answers"]),
    }

"""
Trivia manager (session-aware, guild-safe).

Behavior:
- Prefer questions least used in THIS guild
- Break ties using global times_asked
- Avoid repeats within the same session
- Selection + increments are atomic
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from ..db import get_pool

logger = logging.getLogger(__name__)

Question = Dict[str, Any]

_question_lock = asyncio.Lock()

# -----------------------------
# Session state (SAFE)
# -----------------------------

_current_session_id: Optional[str] = None


def reset_session_questions() -> None:
    """
    Start a new trivia session.
    """
    global _current_session_id
    _current_session_id = str(uuid.uuid4())
    logger.info("New trivia session started: %s", _current_session_id)


def stats_summary() -> Dict[str, int]:
    return {"session_active": int(_current_session_id is not None)}

# -----------------------------
# SQL
# -----------------------------

_SQL_PICK = """
SELECT q.id, q.question, q.correct_answers
FROM questions q
WHERE q.approved = TRUE
  AND NOT EXISTS (
    SELECT 1
    FROM trivia_session_questions s
    WHERE s.guild_id = $1
      AND s.session_id = $2
      AND s.question_id = q.id
  )
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

_SQL_MARK_SESSION = """
INSERT INTO trivia_session_questions (guild_id, session_id, question_id)
VALUES ($1, $2, $3)
ON CONFLICT DO NOTHING
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
    global _current_session_id

    if _current_session_id is None:
        reset_session_questions()

    async with _question_lock:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():

                row = await conn.fetchrow(
                    _SQL_PICK,
                    guild_id,
                    _current_session_id,
                )

                if not row:
                    logger.debug("No eligible trivia questions for guild %s", guild_id)
                    return None

                qid = row["id"]

                await conn.execute(_SQL_INCREMENT_GLOBAL, qid)
                await conn.execute(_SQL_INCREMENT_GUILD, guild_id, qid)
                await conn.execute(
                    _SQL_MARK_SESSION,
                    guild_id,
                    _current_session_id,
                    qid,
                )

    return {
        "id": qid,
        "question": row["question"],
        "answers": _parse_answers(row["correct_answers"]),
    }

# manager.py
"""
Refactored trivia manager (single-session).

Behavior:
- Always try to pick questions with times_asked = 0 first (unused globally).
- If none, pick any times_asked = 0 (session filter might have excluded them).
- If still none, fall back to least-times_asked ordering.
- Avoid passing an empty list to `ALL(...)` by branching when the used set is empty.
- Selection + times_asked increment happen inside a single DB transaction.
- Uses FOR UPDATE SKIP LOCKED (Postgres) to avoid blocking other workers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set

from ..db import get_pool

logger = logging.getLogger(__name__)

Question = Dict[str, Any]

# Tracks questions used in the current trivia session (single-channel)
_used_in_session: Set[int] = set()

# Serialize DB access (keeps logic simple)
_question_lock = asyncio.Lock()


def reset_session_questions() -> None:
    """Call this when a new trivia game/session starts."""
    _used_in_session.clear()
    logger.info("Trivia session reset: cleared used question set")


def stats_summary() -> Dict[str, int]:
    """Minimal in-memory diagnostics (used_count)."""
    return {"used_count": len(_used_in_session)}


# SQL templates (Postgres; SKIP LOCKED prevents blocking)
_SQL_ZERO_NOT_USED = """
SELECT id, question, correct_answers
FROM questions
WHERE approved = TRUE
  AND times_asked = 0
  AND id <> ALL($1::int[])
ORDER BY RANDOM()
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

_SQL_ZERO_ANY = """
SELECT id, question, correct_answers
FROM questions
WHERE approved = TRUE
  AND times_asked = 0
ORDER BY RANDOM()
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

_SQL_LEAST_NOT_USED = """
SELECT id, question, correct_answers
FROM questions
WHERE approved = TRUE
  AND id <> ALL($1::int[])
ORDER BY times_asked ASC, RANDOM()
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

_SQL_LEAST_ANY = """
SELECT id, question, correct_answers
FROM questions
WHERE approved = TRUE
ORDER BY times_asked ASC, RANDOM()
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

_SQL_INCREMENT = """
UPDATE questions
SET times_asked = times_asked + 1
WHERE id = $1
"""


def _parse_answers(raw: Any) -> List[str]:
    """Normalize stored correct_answers into a list of strings."""
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


async def _fetchrow(conn, sql: str, params: Optional[List] = None):
    """Helper to call fetchrow with or without params."""
    if params:
        # asyncpg accepts the Python list to map to an int[]
        return await conn.fetchrow(sql, params)
    return await conn.fetchrow(sql)


async def get_random_question() -> Optional[Question]:
    """
    Fetch a random question, prioritizing zero-times_asked items.

    Priority:
      1) times_asked = 0 and NOT used in session
      2) times_asked = 0 (any)
      3) lowest times_asked and NOT used in session
      4) lowest times_asked (any)

    Selection and times_asked increment executed inside a single transaction.
    """
    async with _question_lock:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                used_list: List[int] = list(_used_in_session)

                # build ordered attempts
                attempts: List[tuple[str, Optional[List[int]]]] = []
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
                        # Log and continue to next attempt rather than blow up
                        logger.exception("Question selection query failed; continuing. SQL head: %s", sql.splitlines()[0].strip())
                        row = None

                    if row:
                        break

                if not row:
                    # no approved questions or DB empty
                    logger.debug("No question found in DB (approved rows may be empty).")
                    return None

                qid = row["id"]

                # mark used in session
                _used_in_session.add(qid)

                # increment times_asked within same transaction
                await conn.execute(_SQL_INCREMENT, qid)

    # parse answers outside the transaction
    answers_list = _parse_answers(row["correct_answers"])
    logger.debug("Selected question id=%s (question prefix=%s)", qid, (row["question"] or "")[:80])
    return {"id": qid, "question": row["question"], "answers": answers_list}

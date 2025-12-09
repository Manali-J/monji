# monji_bot/trivia/manager.py

import asyncio
import json
from typing import Any, Dict, Optional, List

from ..db import get_pool

Question = Dict[str, Any]

# Tracks questions used in the current trivia session
_used_in_session: set[int] = set()

# Serialize DB access
_question_lock = asyncio.Lock()


def reset_session_questions():
    """Call this when a new trivia game/session starts."""
    _used_in_session.clear()


async def get_random_question() -> Optional[Question]:
    """
    Fetch a random question that has NOT been used in the current session.
    Updates times_asked, returns question dict.
    """
    async with _question_lock:
        pool = await get_pool()

        async with pool.acquire() as conn:
            async with conn.transaction():

                used_list: List[int] = list(_used_in_session)

                # Try selecting a question NOT used in the session
                row = await conn.fetchrow(
                    f"""
                    SELECT id, question, correct_answers
                    FROM questions
                    WHERE approved = TRUE
                    AND id NOT IN (SELECT UNNEST($1::int[]))
                    ORDER BY times_asked ASC, RANDOM()
                    LIMIT 1
                    FOR UPDATE
                    """,
                    used_list,
                )

                # If ALL questions already used, you can either:
                # A) Reset session (optional)
                if not row:
                    # No more fresh questions – reset session
                    _used_in_session.clear()
                    used_list = []

                    # Retry without restriction
                    row = await conn.fetchrow(
                        """
                        SELECT id, question, correct_answers
                        FROM questions
                        WHERE approved = TRUE
                        ORDER BY times_asked ASC, RANDOM()
                        LIMIT 1
                        FOR UPDATE
                        """
                    )

                    if not row:
                        return None

                # Mark used in session
                _used_in_session.add(row["id"])

                # Update global ask counter
                await conn.execute(
                    """
                    UPDATE questions
                    SET times_asked = times_asked + 1
                    WHERE id = $1
                    """,
                    row["id"],
                )

        # Decode answers
        answers_raw = row["correct_answers"]

        if isinstance(answers_raw, str):
            try:
                answers_list = json.loads(answers_raw)
            except json.JSONDecodeError:
                answers_list = [answers_raw]
        elif isinstance(answers_raw, list):
            answers_list = [str(a) for a in answers_raw]
        else:
            answers_list = [str(answers_raw)]

        return {
            "id": row["id"],
            "question": row["question"],
            "answers": answers_list,
        }

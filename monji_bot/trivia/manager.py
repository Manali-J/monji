# monji_bot/trivia/manager.py

import json
from typing import Any, Dict, Optional

from ..db import get_pool

Question = Dict[str, Any]


async def get_random_question() -> Optional[Question]:
    """
    Fetch a single random approved question from the DB,
    increment its times_asked counter, and return it.

    Returns a dict:
        {
          "id": int,
          "question": str,
          "answers": [str, ...]
        }
    """
    pool = await get_pool()

    async with pool.acquire() as conn:

        # 1. Pick a question, prefer ones asked less often
        row = await conn.fetchrow(
            """
            SELECT id, question, correct_answers
            FROM questions
            WHERE approved = TRUE
            ORDER BY times_asked ASC, RANDOM()
            LIMIT 1
            """
        )

        if not row:
            return None

        # 2. Increment times_asked for this question
        await conn.execute(
            """
            UPDATE questions
            SET times_asked = times_asked + 1
            WHERE id = $1
            """,
            row["id"],
        )

    # 3. Decode answers
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

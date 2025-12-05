# monji_bot/trivia/manager.py

import json
from typing import Any, Dict, Optional

from ..db import get_pool

Question = Dict[str, Any]


async def get_random_question() -> Optional[Question]:
    """
    Fetch a single random question from the database.

    Expects table:
        questions(
            id SERIAL PRIMARY KEY,
            question TEXT NOT NULL,
            correct_answers JSONB NOT NULL,  -- list
            ...
        )

    Returns a dict:
        {
          "id": int,
          "question": str,
          "answers": [str, ...]
        }
    or None if there are no questions.
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, question, correct_answers
            FROM questions
            WHERE approved = TRUE
            ORDER BY RANDOM()
            LIMIT 1
            """
        )

    if not row:
        return None

    answers_raw = row["correct_answers"]

    # correct_answers is stored as JSONB, but we encoded it via json.dumps
    # so asyncpg will likely give us a string -> need json.loads.
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

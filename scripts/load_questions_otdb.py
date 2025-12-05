# scripts/load_questions_otdb.py

import asyncio
import json
import html
from typing import List, Dict, Any

import aiohttp

from monji_bot.db import get_pool, init_schema


API_URL = "https://opentdb.com/api.php?amount=50&difficulty=easy"


async def fetch_otdb_batch() -> List[Dict[str, Any]]:
    """
    Fetch one batch (up to 50) easy questions from Open Trivia DB.
    Returns a list of normalized question dicts ready for DB insert.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL) as resp:
            data = await resp.json()

    if data.get("response_code") != 0:
        print(f"⚠ OTDB returned response_code={data.get('response_code')}")
        return []

    results = data.get("results", [])
    cleaned: List[Dict[str, Any]] = []

    for q in results:
        cleaned.append(
            {
                "source": "opentdb_easy",
                "external_id": None,  # OTDB doesn't give a stable ID in this API
                "category": html.unescape(q.get("category", "")),
                "difficulty": q.get("difficulty", "easy"),
                "question": html.unescape(q.get("question", "")),
                "correct_answers": [html.unescape(q.get("correct_answer", ""))],
                "incorrect_answers": [
                    html.unescape(x) for x in q.get("incorrect_answers", [])
                ],
            }
        )

    return cleaned


async def insert_questions(questions: List[Dict[str, Any]]) -> None:
    """
    Insert the given questions into the questions table.
    """
    if not questions:
        print("⚠ No questions to insert.")
        return

    pool = await get_pool()

    async with pool.acquire() as conn:
        # You can use executemany-style loop
        for q in questions:
            await conn.execute(
                """
                INSERT INTO questions (source,
                                       external_id,
                                       category,
                                       difficulty,
                                       question,
                                       correct_answers,
                                       incorrect_answers)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                q["source"],
                q["external_id"],
                q["category"],
                q["difficulty"],
                q["question"],
                json.dumps(q["correct_answers"]),  # list
                json.dumps(q["incorrect_answers"]),  # list
            )

    print(f"✅ Inserted {len(questions)} questions into DB.")


async def main():
    # Make sure table exists
    await init_schema()

    print("📥 Fetching questions from Open Trivia DB...")
    questions = await fetch_otdb_batch()
    print(f"Fetched {len(questions)} questions.")

    await insert_questions(questions)


if __name__ == "__main__":
    asyncio.run(main())

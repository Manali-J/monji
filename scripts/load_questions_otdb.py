# scripts/load_otdb_category22.py

import asyncio
import json
import html
from typing import List, Dict, Any
import aiohttp

from monji_bot.db import get_pool, init_schema

API_URL = (
    "https://opentdb.com/api.php?amount=50&category=10&type=multiple"
)

MAX_EMPTY_INSERTS = 5  # stop after 5 batches with no new unique items


async def fetch_batch() -> List[Dict[str, Any]]:
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
                "source": "opentdb",   # <----- FIXED
                "external_id": None,
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


async def insert_questions(questions: List[Dict[str, Any]]) -> int:
    """
    Insert questions and return the count of newly inserted rows.
    """
    if not questions:
        return 0

    pool = await get_pool()
    new_count = 0

    async with pool.acquire() as conn:
        async with conn.transaction():
            for q in questions:
                result = await conn.execute(
                    """
                    INSERT INTO questions (
                        source, external_id, category, difficulty,
                        question, correct_answers, incorrect_answers
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (source, question) DO NOTHING
                    """,
                    q["source"],
                    q["external_id"],
                    q["category"],
                    q["difficulty"],
                    q["question"],
                    json.dumps(q["correct_answers"]),
                    json.dumps(q["incorrect_answers"]),
                )
                # "INSERT 0 1" = inserted | "INSERT 0 0" = conflict
                if result.endswith("1"):
                    new_count += 1

    return new_count


async def main():
    await init_schema()

    empty_inserts = 0
    total_new = 0
    batch_number = 1

    while empty_inserts < MAX_EMPTY_INSERTS:
        print(f"\n📥 Fetching batch #{batch_number}...")
        batch = await fetch_batch()

        if not batch:
            print("⚠ No data returned. Stopping.")
            break

        inserted = await insert_questions(batch)

        if inserted == 0:
            empty_inserts += 1
            print(f"⚠ No new questions ({empty_inserts}/{MAX_EMPTY_INSERTS})")
        else:
            empty_inserts = 0
            total_new += inserted
            print(f"✅ Added {inserted} new questions (total: {total_new})")

        batch_number += 1
        await asyncio.sleep(1.0)  # avoid hitting OTDB too fast

    print(f"\n🎉 Done! Total unique questions added: {total_new}")


if __name__ == "__main__":
    asyncio.run(main())

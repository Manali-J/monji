# monji_bot/snark_llm.py

import random
import asyncio
from openai import AsyncOpenAI
from .config import OPENAI_API_KEY

# Async OpenAI client
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ---
#  CATEGORY PROMPTS
# ---
CATEGORY_PROMPTS = {
    "correct_answer": "User answered a trivia question correctly.",
    "nobody_got_it": "Nobody in the channel got the trivia question right.",
    "game_already_running": "A trivia game is already running and they tried to start another one.",
    "single_already_running": "A single trivia question is already running and they tried to start another one.",
    "nothing_to_stop": "They tried to stop trivia but nothing is running.",
    "hint_1": "Players are struggling and the bot is giving Hint 1.",
    "hint_2": "Players are still struggling and the bot is giving Hint 2.",
    "hint_3": "Players need a final Hint 3 to answer the question.",
}

# ---
# Personalities
# ---
PERSONALITIES = [
    "snarky but playful",
    "sarcastic but lighthearted",
    "dry and deadpan",
    "quick-witted and teasing",
    "roasty but friendly",
]

# ---
# Style modifiers
# ---
STYLE_MODIFIERS = [
    "keep it short",
    "make it sharp and witty",
    "make it dry and sarcastic",
    "sound amused",
    "sound mildly disappointed",
    "make it a clean roast",
    "be dramatically unimpressed",
]


async def get_snark(category: str) -> str:
    """
    Generate a short, unique, one-line snark message using the OpenAI API.
    Always <= 120 characters, PG-13, no emojis.
    """

    seed = CATEGORY_PROMPTS.get(category, "General trivia sarcasm.")
    personality = random.choice(PERSONALITIES)
    style_modifier = random.choice(STYLE_MODIFIERS)

    system_prompt = (
        "You are Monji, a sarcastic but playful Discord trivia bot. "
        "You generate extremely short one-line roasts or sarcastic remarks. "
        "Tone: teasing, fun, PG-13, never hateful, no slurs, no emojis. "
        "Output MUST be under 120 characters. Only return the snark line, no quotes."
    )

    user_prompt = (
        f"{seed}\n"
        f"Write ONE original sarcastic one-liner.\n"
        f"Style: {personality}. Also {style_modifier}.\n"
        f"Do not repeat previous examples. No emojis."
    )

    try:
        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=40,
            temperature=0.95,
        )

        text = response.choices[0].message.content.strip()
        return text[:120]

    except Exception as e:
        print("LLM SNARK ERROR:", repr(e))
        fallback = [
            "My snark generator crashed. Honestly, fitting.",
            "No LLM today. Consider this a mercy.",
            "Technical issues. Pretend I roasted you.",
        ]
        return random.choice(fallback)


# ---------------
# TEST HARNESS
# ---------------
async def main():
    print("🔧 Testing snark generator...\n")

    tests = [
        "correct_answer",
        "nobody_got_it",
        "hint_1",
        "hint_2",
        "hint_3",
        "game_already_running",
        "single_already_running",
        "nothing_to_stop",
    ]

    for t in tests:
        print(f"▶ {t}:")
        snark = await get_snark(t)
        print(f"  {snark}\n")

    print("Done.\n")


if __name__ == "__main__":
    asyncio.run(main())

# monji_bot/trivia/hints.py

import asyncio
import discord

from monji_bot.llm_bot import generate_reply
from monji_bot.trivia.constants import (
    HINT_DELAY_SECONDS,
    HINT_INTERVAL_SECONDS,
    FINAL_WAIT_SECONDS,
    WINNER_RESOLUTION_DELAY,
    EVENT_HINT_3,
    EVENT_NO_ANSWER,
    KEY_HINT,
)
from monji_bot.trivia.state import GameState


def build_hint(answer: str, level: int) -> str:
    """
    Build a starting-letters style hint.
    level 1-3: progressively reveal more of each word.
    """
    words = answer.split()
    hints = []

    for w in words:
        length = len(w)
        if length == 0:
            hints.append("")
            continue

        if level == 1:
            show = max(1, length // 4)
        elif level == 2:
            show = max(1, length // 2)
        else:
            show = max(1, (3 * length) // 4)

        visible = w[:show]
        hidden = "•" * (length - show)
        hints.append(visible + hidden)

    return " ".join(hints)


# -----------------------------
# HINT / TIMEOUT HANDLER
# -----------------------------
async def handle_game_question_timeout(
    channel: discord.TextChannel,
    state: GameState,
):
    """
    Run the hint cycle + timeout for the current game question in this channel.
    Exits early if someone answers, the game stops, or the round changes.
    """
    this_round = state.round
    q = state.current_question

    if not q:
        return

    correct_answers = q.get("answers") or []
    if not correct_answers:
        return

    main_answer = correct_answers[0]

    # Disable hints if ANY correct answer is a single character
    single_char_answer = any(len(a.strip()) == 1 for a in correct_answers)

    # Initial wait before first hint
    await asyncio.sleep(HINT_DELAY_SECONDS)

    # Hints 1–3
    for level in range(1, 4):
        if (
            not state.in_progress
            or state.winner_id is not None
            or state.round != this_round
        ):
            return

        if not single_char_answer:
            hint_text = build_hint(main_answer, level)

            if level < 3:
                await channel.send(
                    f"💡 **Hint {level}/3:** `{hint_text}`"
                )
            else:
                data = {
                    KEY_HINT: hint_text,
                    "answer": main_answer,
                    "round": this_round,
                    "max_rounds": state.max_rounds,
                    "question": q.get("question"),
                }

                sarcasm = await asyncio.to_thread(
                    generate_reply,
                    EVENT_HINT_3,
                    data,
                )

                if sarcasm:
                    if main_answer.lower() in sarcasm.lower():
                        sarcasm = "Wow, third hint already? Rough one."
                    if len(sarcasm) > 200:
                        sarcasm = sarcasm[:200]

                    await channel.send(
                        f"💡 **Hint 3/3:** `{hint_text}`\n> {sarcasm}"
                    )
                else:
                    await channel.send(
                        f"💡 **Hint 3/3:** `{hint_text}`"
                    )
        else:
            hint_text = "No hints! Answer is a single character."
            await channel.send(
                f"💡 **Hint {level}/3:** `{hint_text}`"
            )

        if level < 3:
            await asyncio.sleep(HINT_INTERVAL_SECONDS)

    # Final wait before giving up
    await asyncio.sleep(FINAL_WAIT_SECONDS)

    # If winner resolution is ongoing, wait briefly
    if state.resolving:
        await asyncio.sleep(WINNER_RESOLUTION_DELAY + 0.1)

    if (
        not state.in_progress
        or state.winner_id is not None
        or state.round != this_round
    ):
        return

    # 🔒 Lock this round: time's up
    state.winner_id = -1
    state.correct_candidates.clear()

    data = {
        "answer": main_answer,
        "round": this_round,
        "max_rounds": state.max_rounds,
        "question": q.get("question"),
    }

    sarcasm = await asyncio.to_thread(
        generate_reply,
        EVENT_NO_ANSWER,
        data,
    )

    if sarcasm:
        if len(sarcasm) > 200:
            sarcasm = sarcasm[:200]
        msg = (
            "⏰ Time's up. No one got it.\n"
            f"The correct answer was: **{main_answer}**.\n"
            f"> {sarcasm}"
        )
    else:
        msg = (
            "⏰ Time's up. No one got it.\n"
            f"The correct answer was: **{main_answer}**."
        )

    await channel.send(msg)

    # Move on
    return "timeout"

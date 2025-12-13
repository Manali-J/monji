import asyncio
import discord

from monji_bot.common.state import GameState

# -----------------------------
# TIMING CONSTANTS (seconds)
# -----------------------------
HINT_1_DELAY = 20
HINT_2_DELAY = 20
FINAL_WAIT = 20


def _build_hint_2(word: str) -> str:
    """
    Reveal first letter + one more letter in correct position.
    Example: C _ _ _ _ E _
    """
    length = len(word)
    reveal_indexes = {0}

    # Pick a second index safely (not 0)
    if length > 2:
        reveal_indexes.add(length - 2)
    else:
        reveal_indexes.add(1)

    chars = []
    for i, ch in enumerate(word):
        if i in reveal_indexes:
            chars.append(ch.upper())
        else:
            chars.append("_")

    return " ".join(chars)


async def handle_scramble_timeout(
    channel: discord.TextChannel,
    state: GameState,
):
    """
    Handles hint timing for a single scramble round.

    Returns:
        "timeout" if nobody solved it,
        None otherwise (winner, game stopped, round changed)
    """
    this_round = state.round
    question = state.current_question

    if not question:
        return None

    word = question["word"]

    # -----------------------------
    # Hint 1 (20s)
    # -----------------------------
    await asyncio.sleep(HINT_1_DELAY)

    if (
        not state.in_progress
        or state.winner_id is not None
        or state.round != this_round
    ):
        return None

    await channel.send(
        f"💡 **Hint 1:** Starts with **{word[0].upper()}** "
        f"({len(word)} letters)"
    )

    # -----------------------------
    # Hint 2 (40s)
    # -----------------------------
    await asyncio.sleep(HINT_2_DELAY)

    if (
        not state.in_progress
        or state.winner_id is not None
        or state.round != this_round
    ):
        return None

    hint_2 = _build_hint_2(word)

    await channel.send(
        f"💡 **Hint 2:** `{hint_2}`"
    )

    # -----------------------------
    # Final wait (60s)
    # -----------------------------
    await asyncio.sleep(FINAL_WAIT)

    if (
        not state.in_progress
        or state.winner_id is not None
        or state.round != this_round
    ):
        return None

    # Lock the round: no winner
    state.winner_id = -1
    state.correct_candidates.clear()

    await channel.send(
        f"⏰ Time’s up! The correct word was **{word.upper()}**."
    )

    return "timeout"

import asyncio
import discord

from monji_bot.scramble.scramble_hints import handle_scramble_timeout
from monji_bot.scramble.scramble_manager import get_random_scramble_word
from monji_bot.llm.commentary import handle_midgame_quip
from monji_bot.common.state import GameState


async def ask_next_scramble_round(channel: discord.TextChannel, state: GameState):
    """Ask the next scramble word."""
    row = await get_random_scramble_word()
    if row is None:
        await channel.send("I ran out of scramble words. This is awkward.")
        state.in_progress = False
        state.current_question = None
        return

    state.round += 1
    state.reset_round()

    word = row["word"]
    scrambled = state.scramble(word)

    state.current_question = {
        "word": word,
        "scrambled": scrambled,
    }

    await channel.send(
        f"🔀 **Scramble {state.round} of {state.max_rounds}**\n\n"
        f"**{scrambled.upper()}**\n\n"
        f"⏱️ You have **60 seconds**. Go."
    )

    async def run_timeout_flow():
        result = await handle_scramble_timeout(channel, state)

        if result == "timeout" and state.in_progress:
            if state.round >= state.max_rounds:
                await end_scramble_game(channel, state)
            else:
                await ask_next_scramble_round(channel, state)

    asyncio.create_task(run_timeout_flow())


async def end_scramble_game(channel: discord.TextChannel, state: GameState):
    """End scramble game and show scoreboard."""
    state.in_progress = False
    state.current_question = None
    state.correct_candidates.clear()
    state.resolving = False

    scores = state.scores
    if not scores:
        await channel.send(
            "🔀 **Scramble over.** Nobody solved anything. Incredible."
        )
        return

    sorted_scores = sorted(
        scores.items(),
        key=lambda kv: kv[1],
        reverse=True,
    )

    lines = []
    guild = channel.guild

    for i, (user_id, score) in enumerate(sorted_scores, start=1):
        member = guild.get_member(user_id) if guild else None
        name = member.display_name if member else f"User {user_id}"
        lines.append(f"**{i}. {name}** — {score} point(s)")

    await channel.send(
        "🔀 **Scramble over.** Final scores:\n" + "\n".join(lines)
    )

    await handle_midgame_quip(channel, state)

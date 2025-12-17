# -----------------------------
# MULTI-ROUND HELPERS
# -----------------------------
import asyncio
import discord

from monji_bot.llm.commentary import handle_midgame_quip
from monji_bot.trivia.hints import handle_game_question_timeout
from monji_bot.trivia.manager import get_random_question
from monji_bot.common.state import GameState


async def ask_next_round(channel: discord.TextChannel, state: GameState):
    """Ask the next question in a multi-round game."""
    q = await get_random_question(channel.guild.id)
    if q is None:
        await channel.send(
            "I ran out of questions. Blame whoever configured me."
        )
        state.in_progress = False
        state.current_question = None
        return

    state.round += 1
    state.current_question = q
    state.reset_round()

    await channel.send(
        f"❓ **Question {state.round} of {state.max_rounds}**\n"
        f"{q['question']}\n\n"
    )

    async def run_timeout_flow():
        """
        Run hint/timeout logic and decide what happens next.
        This avoids circular imports by keeping flow control here.
        """
        result = await handle_game_question_timeout(channel, state)

        # If the round ended because of timeout (no winner)
        if result == "timeout":
            if not state.in_progress:
                return

            if state.round >= state.max_rounds:
                await end_game(channel, state)
            else:
                await ask_next_round(channel, state)

    # Start the hint / timeout cycle for this round
    asyncio.create_task(run_timeout_flow())


async def end_game(channel: discord.TextChannel, state: GameState):
    """End the multi-round game and show the scoreboard."""
    state.in_progress = False
    state.current_question = None
    state.correct_candidates.clear()
    state.resolving = False

    scores = state.scores

    if not scores:
        await channel.send(
            "🎮 **Game over.** Nobody scored anything. Impressive, in a tragic way."
        )
        return

    # Sort by score descending
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

    msg = "🎮 **Game over.** Here’s the damage:\n" + "\n".join(lines)
    await channel.send(msg)

    # Extra LLM commentary based on final scores
    await handle_midgame_quip(channel, state)

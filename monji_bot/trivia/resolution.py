# monji_bot/trivia/resolution.py

import asyncio
import discord

from monji_bot.scramble.scramble_lifecycle import ask_next_scramble_round, end_scramble_game
from monji_bot.trivia.constants import WINNER_RESOLUTION_DELAY, ROUND_TRANSITION_DELAY, MODE_TRIVIA
from monji_bot.trivia.lifecycle import ask_next_round, end_game
from monji_bot.llm.commentary import handle_midgame_quip
from monji_bot.common.state import GameState
from monji_bot.db import award_points


async def resolve_round_winner(
    channel: discord.TextChannel,
    state: GameState,
    round_number: int,
):
    """
    After a short delay, pick the earliest correct answer (by message.created_at)
    among all correct answers received for this round, then award the point
    and move to the next round / end the game.
    """
    await asyncio.sleep(WINNER_RESOLUTION_DELAY)

    # Bail if game ended, round changed, or already resolved
    if (
        not state.in_progress
        or state.current_question is None
        or state.winner_id is not None
        or state.round != round_number
    ):
        state.resolving = False
        return

    candidates = state.correct_candidates

    # No correct answers after all
    if not candidates:
        state.resolving = False
        return

    # Pick earliest correct answer
    winner_entry = min(
        candidates,
        key=lambda c: c.message.created_at.timestamp(),
    )

    winner_msg: discord.Message = winner_entry.message
    winner_user = winner_msg.author
    winner_id = winner_user.id

    # Mark resolved
    state.winner_id = winner_id

    # Update in-memory score
    state.scores[winner_id] = state.scores.get(winner_id, 0) + 1

    # Persist leaderboard score
    if winner_msg.guild is not None:
        await award_points(
            guild_id=winner_msg.guild.id,
            user_id=winner_id,
            display_name=winner_user.display_name,
            points=1,
            mode=state.mode
        )

    if state.mode == MODE_TRIVIA:
        correct_answer = state.current_question["answers"][0]
    else:  # scramble
        correct_answer = state.current_question["word"]
    await channel.send(
        f"✅ {winner_user.mention} got it right. "
        f"Correct answer: **{correct_answer}**."
    )

    # --- Mid-game quip trigger ---
    midpoint = state.max_rounds // 2

    if (
        state.max_rounds >= 15
        and state.round == midpoint
        and not state.midgame_quip_done
    ):
        state.midgame_quip_done = True
        asyncio.create_task(handle_midgame_quip(channel, state))
    # --- end mid-game quip trigger ---

    # Clear round state
    state.correct_candidates.clear()
    state.resolving = False

    await asyncio.sleep(ROUND_TRANSITION_DELAY)

    if state.round >= state.max_rounds:
        if state.mode == MODE_TRIVIA:
            await end_game(channel, state)
        else:  # scramble
            await end_scramble_game(channel, state)
    else:
        if state.mode == MODE_TRIVIA:
            await ask_next_round(channel, state)
        else:  # scramble
            await ask_next_scramble_round(channel, state)


import asyncio
import discord

from monji_bot.llm_bot import generate_reply
from monji_bot.trivia.constants import EVENT_MID_ROUND_QUIP
from monji_bot.trivia.state import GameState


async def handle_midgame_quip(channel: discord.TextChannel, state: GameState):
    guild = channel.guild
    if guild is None:
        return

    # Skip commentary entirely for short games
    if state.max_rounds < 15:
        return

    # Build list of (member, score) for players in this game
    players: list[tuple[discord.Member, int]] = []
    for user_id, score in state.scores.items():
        member = guild.get_member(user_id)
        if member is not None and not member.bot:
            players.append((member, score))

    if not players:
        return

    data = {
        "round": state.round,
        "max_rounds": state.max_rounds,
        "scores": [
            {"display_name": member.display_name, "score": score}
            for member, score in players
        ],
    }

    # LLM call (sync function in a thread)
    text = await asyncio.to_thread(
        generate_reply,
        EVENT_MID_ROUND_QUIP,
        data,
    )

    if not text:
        return

    # Replace ALL @display_name occurrences with real Discord mentions
    for member, _ in players:
        placeholder = f"@{member.display_name}"
        if placeholder in text:
            text = text.replace(placeholder, member.mention)

    # Optional: clamp length
    if len(text) > 200:
        text = text[:200]

    await channel.send(text)

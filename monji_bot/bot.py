# monji_bot/bot.py

import asyncio
import discord
from discord.ext import commands

from .config import BOT_TOKEN
from .trivia.manager import load_questions, get_random_question
from .utils.fuzzy import is_fuzzy_match

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # for later when we add leaderboards

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

# One-shot question state for !trivia:
# channel_id -> { "question": str, "answers": [str], "winner_id": int | None }
ACTIVE_QUESTIONS: dict[int, dict] = {}

# Multi-round game state for !trivia_start:
# channel_id -> {
#   "round": int,
#   "max_rounds": int,
#   "current_question": { "question": str, "answers": [str] } | None,
#   "winner_id": int | None,
#   "scores": dict[user_id, int],
#   "in_progress": bool
# }
GAMES: dict[int, dict] = {}


@bot.event
async def on_ready():
    # Load questions from questions.json when Monji starts
    load_questions()
    print(f"Monji is online as {bot.user}")


@bot.command()
async def ping(ctx: commands.Context):
    """Simple test command."""
    await ctx.send("Pong! Monji is awake... unfortunately.")


# -----------------------------
# SINGLE QUESTION: !trivia
# -----------------------------
@bot.command(name="trivia")
async def trivia_command(ctx: commands.Context):
    """
    Start a single trivia question in this channel.
    Monji will ask a question, and the first correct typed answer wins.
    """
    channel = ctx.channel

    # If there's already an active multi-round game, don’t allow single-question mode.
    game_state = GAMES.get(channel.id)
    if game_state and game_state.get("in_progress"):
        await ctx.send(
            "There’s already a trivia game running here. Finish that first, overachiever."
        )
        return

    # If there's already an active single question with no winner, don't start another
    state = ACTIVE_QUESTIONS.get(channel.id)
    if state and state.get("winner_id") is None:
        await ctx.send(
            "There’s already a question running here. Try answering that one first."
        )
        return

    # Get a random question
    q = get_random_question()
    if q is None:
        await ctx.send(
            "I have no questions loaded. Someone forgot to feed me `questions.json`."
        )
        return

    # Store active question state for this channel
    ACTIVE_QUESTIONS[channel.id] = {
        "question": q["question"],
        "answers": q["answers"],
        "winner_id": None,
    }

    # Ask the question
    await ctx.send(
        f"🧠 **Trivia Time!**\n"
        f"{q['question']}\n\n"
        f"Type your answer in chat. First correct one wins. No pressure."
    )


# -----------------------------
# MULTI-ROUND GAME: !trivia_start
# -----------------------------
@bot.command(name="trivia_start")
async def trivia_start(ctx: commands.Context, rounds: int):
    """
    Start a multi-round trivia game in this channel.
    Usage: !trivia_start 10  (between 5 and 100 rounds)
    """
    channel = ctx.channel

    if rounds < 5 or rounds > 100:
        await ctx.send(
            "Pick a number between **5 and 100** rounds. I refuse to work outside those limits."
        )
        return

    # Prevent starting a game if one is already running
    state = GAMES.get(channel.id)
    if state and state.get("in_progress"):
        await ctx.send(
            "There’s already a trivia game running in this channel. Calm down."
        )
        return

    # Also prevent if a single-question round is in progress
    single_state = ACTIVE_QUESTIONS.get(channel.id)
    if single_state and single_state.get("winner_id") is None:
        await ctx.send(
            "There’s a single-question trivia running here. Finish that first."
        )
        return

    # Create new game state
    state = {
        "round": 0,
        "max_rounds": rounds,
        "current_question": None,
        "winner_id": None,
        "scores": {},  # user_id -> int
        "in_progress": True,
    }
    GAMES[channel.id] = state

    await ctx.send(
        f"Starting a trivia game with **{rounds} rounds.**\n"
        f"Fastest correct answer wins each round. Try not to embarrass yourselves."
    )

    await ask_next_round(channel, state)


async def ask_next_round(channel: discord.TextChannel, state: dict):
    """Ask the next question in a multi-round game."""
    q = get_random_question()
    if q is None:
        await channel.send(
            "I ran out of questions. Blame whoever configured me."
        )
        state["in_progress"] = False
        state["current_question"] = None
        return

    state["round"] += 1
    state["current_question"] = q
    state["winner_id"] = None

    await channel.send(
        f"🧠 **Round {state['round']} of {state['max_rounds']}**\n"
        f"{q['question']}\n\n"
        f"Type your answer. First correct one wins. No pressure."
    )


async def end_game(channel: discord.TextChannel, state: dict):
    """End the multi-round game and show the scoreboard."""
    state["in_progress"] = False
    state["current_question"] = None

    scores = state.get("scores", {})

    if not scores:
        await channel.send(
            "🎮 **Game over.** Nobody scored anything. Impressive, in a tragic way."
        )
        return

    # Sort by score descending
    sorted_scores = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    lines = []
    for i, (user_id, score) in enumerate(sorted_scores, start=1):
        # Try to resolve the member name
        guild = channel.guild
        member = guild.get_member(user_id) if guild else None
        name = member.display_name if member else f"User {user_id}"
        lines.append(f"**{i}. {name}** — {score} point(s)")

    msg = "🎮 **Game over.** Here’s the damage:\n" + "\n".join(lines)
    await channel.send(msg)


# -----------------------------
# MESSAGE LISTENER (CHECK ANSWERS)
# -----------------------------
@bot.event
async def on_message(message: discord.Message):
    """
    Listen to all messages so we can check if they answer:
    - an active multi-round game question, or
    - a single !trivia question.
    """
    # Ignore messages from bots (including Monji)
    if message.author.bot:
        return

    channel = message.channel

    # 1) Check if there is an active multi-round game in this channel
    game_state = GAMES.get(channel.id)
    if (
        game_state
        and game_state.get("in_progress")
        and game_state.get("current_question")
        and game_state.get("winner_id") is None
    ):
        user_answer = message.content
        correct_answers = game_state["current_question"]["answers"]

        for correct in correct_answers:
            if is_fuzzy_match(user_answer, correct):
                # Mark winner
                game_state["winner_id"] = message.author.id

                # Update score
                scores = game_state["scores"]
                scores[message.author.id] = scores.get(message.author.id, 0) + 1

                await channel.send(
                    "✅ {mention} got it right. I’ll pretend I’m not impressed.\n"
                    "Correct answer: **{answer}**.".format(
                        mention=message.author.mention,
                        answer=correct,
                    )
                )

                # Next round or end game
                if game_state["round"] >= game_state["max_rounds"]:
                    await asyncio.sleep(2)
                    await end_game(channel, game_state)
                else:
                    await asyncio.sleep(2)
                    await ask_next_round(channel, game_state)

                break  # stop checking more answers

        # Important: still process commands even during a game
        await bot.process_commands(message)
        return

    # 2) If no multi-round game answer, fall back to single-question mode
    state = ACTIVE_QUESTIONS.get(channel.id)
    if state and state.get("winner_id") is None:
        user_answer = message.content
        correct_answers = state["answers"]

        for correct in correct_answers:
            if is_fuzzy_match(user_answer, correct):
                # Mark winner
                state["winner_id"] = message.author.id

                await channel.send(
                    "✅ {mention} got it right. I’ll pretend I’m not impressed.\n"
                    "Correct answer: **{answer}**.".format(
                        mention=message.author.mention,
                        answer=correct,
                    )
                )

                # Clear active question so another !trivia can be started
                ACTIVE_QUESTIONS.pop(channel.id, None)
                break

    # Allow commands (!ping, !trivia, !trivia_start, etc.)
    await bot.process_commands(message)


def main():
    """Entry point when running `python -m monji_bot.bot`."""
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    main()

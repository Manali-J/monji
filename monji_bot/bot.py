# monji_bot/bot.py

import asyncio
import discord
from discord.ext import commands

from .config import BOT_TOKEN
from .trivia.manager import get_random_question
from .db import init_schema
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

# -----------------------------
# HINT / TIMEOUT CONFIG
# -----------------------------
HINT_DELAY_SECONDS = 30       # time before first hint
HINT_INTERVAL_SECONDS = 24    # time between hints
FINAL_WAIT_SECONDS = 20       # time after last hint before giving up

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

        # how much of the word to reveal per level
        # level 1 -> ~1/4, level 2 -> ~1/2, level 3 -> ~3/4
        if level == 1:
            show = max(1, length // 4)
        elif level == 2:
            show = max(1, length // 2)
        else:  # level 3
            show = max(1, (3 * length) // 4)

        visible = w[:show]
        hidden = "•" * (length - show)
        hints.append(visible + hidden)

    return " ".join(hints)


@bot.event
async def on_ready():
    # Ensure DB table exists (idempotent)
    await init_schema()
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
    q = await get_random_question()
    if q is None:
        await ctx.send(
            "I have no questions loaded. Someone forgot to feed me the database."
        )
        return

    # Store active question state for this channel
    state = {
        "question": q["question"],
        "answers": q["answers"],
        "winner_id": None,
    }
    ACTIVE_QUESTIONS[channel.id] = state

    # Ask the question
    await ctx.send(
        f"❓ **Trivia Time!**\n"
        f"{q['question']}\n\n"
        f"Type your answer in chat. First correct one wins. No pressure."
    )

    # Start the hint / timeout cycle
    asyncio.create_task(
        handle_single_question_timeout(channel, state, channel.id)
    )


# -----------------------------
# MULTI-ROUND GAME: !trivia_start
# -----------------------------
@bot.command(name="trivia_start")
async def trivia_start(ctx: commands.Context, rounds: int):
    """
    Start a multi-round trivia game in this channel.
    Usage: !trivia_start 10  (between 5 and 1000 rounds)
    """
    channel = ctx.channel

    if rounds < 5 or rounds > 1000:
        await ctx.send(
            "Pick a number between **5 and 1000** rounds. I refuse to work outside those limits."
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
    q = await get_random_question()
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
        f"❓ **Round {state['round']} of {state['max_rounds']}**\n"
        f"{q['question']}\n\n"
        f"Type your answer. First correct one wins. No pressure."
    )

    # Start the hint / timeout cycle for this round
    asyncio.create_task(handle_game_question_timeout(channel, state))


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
# HINT / TIMEOUT HANDLERS
# -----------------------------
async def handle_game_question_timeout(channel: discord.TextChannel, state: dict):
    """
    Run the hint cycle + timeout for the current game question in this channel.
    Exits early if someone answers, the game stops, or the round changes.
    """
    this_round = state.get("round")

    q = state.get("current_question")
    if not q:
        return

    correct_answers = q.get("answers") or []
    if not correct_answers:
        return

    main_answer = correct_answers[0]

    # Initial wait before first hint
    await asyncio.sleep(HINT_DELAY_SECONDS)

    # Hints 1–3
    for level in range(1, 4):
        if (
            not state.get("in_progress")
            or state.get("winner_id") is not None
            or state.get("round") != this_round
        ):
            return

        hint_text = build_hint(main_answer, level)
        await channel.send(
            f"💡 **Hint {level}/3:** `{hint_text}`"
        )

        if level < 3:
            await asyncio.sleep(HINT_INTERVAL_SECONDS)

    # Final wait before giving up
    await asyncio.sleep(FINAL_WAIT_SECONDS)

    if (
        not state.get("in_progress")
        or state.get("winner_id") is not None
        or state.get("round") != this_round
    ):
        return

    await channel.send(
        "⏰ Time's up. No one got it.\n"
        f"The correct answer was: **{main_answer}**."
    )

    # Move on to next round or end game
    if state["round"] >= state["max_rounds"]:
        await asyncio.sleep(2)
        await end_game(channel, state)
    else:
        await asyncio.sleep(2)
        await ask_next_round(channel, state)


async def handle_single_question_timeout(
    channel: discord.TextChannel,
    state: dict,
    channel_id: int,
):
    """
    Hint cycle + timeout for a single-question !trivia.
    Exits early if someone answers or the question is cleared.
    """
    original_state = state

    correct_answers = state.get("answers") or []
    if not correct_answers:
        return

    main_answer = correct_answers[0]

    await asyncio.sleep(HINT_DELAY_SECONDS)

    for level in range(1, 4):
        current = ACTIVE_QUESTIONS.get(channel_id)
        if (
            current is None
            or current is not original_state
            or current.get("winner_id") is not None
        ):
            return

        hint_text = build_hint(main_answer, level)
        await channel.send(
            f"💡 **Hint {level}/3:** `{hint_text}`"
        )

        if level < 3:
            await asyncio.sleep(HINT_INTERVAL_SECONDS)

    await asyncio.sleep(FINAL_WAIT_SECONDS)

    current = ACTIVE_QUESTIONS.get(channel_id)
    if (
        current is None
        or current is not original_state
        or current.get("winner_id") is not None
    ):
        return

    await channel.send(
        "⏰ Time's up. No one got it.\n"
        f"The correct answer was: **{main_answer}**."
    )

    # Clear the active question so another !trivia can be started
    ACTIVE_QUESTIONS.pop(channel_id, None)


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

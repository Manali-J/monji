# monji_bot/bot.py

import asyncio
import discord
from discord.ext import commands

from .config import BOT_TOKEN
from .trivia.manager import get_random_question
from .db import init_schema, award_points, get_leaderboard, get_user_rank
from .utils.fuzzy import is_fuzzy_match

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # needed for resolving display names

bot = commands.Bot(
    command_prefix="!",  # prefix is unused now, but harmless to keep
    intents=intents,
    help_command=None,
)

# Multi-round game state for /trivia:
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
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    # Make sure DB schema (questions + user_scores) exists
    await init_schema()

    # Sync slash commands with Discord
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} app commands.")
    except Exception as e:
        print(f"❌ Error syncing app commands: {e}")


# -----------------------------
# SIMPLE PING COMMAND
# -----------------------------
@bot.tree.command(
    name="ping",
    description="Simple test command.",
)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Pong! Monji is awake... unfortunately.",
        ephemeral=True,
    )


# -----------------------------
# MULTI-ROUND GAME: /trivia
# -----------------------------
@bot.tree.command(
    name="trivia",
    description="Start a multi-round trivia game in this channel.",
)
async def trivia(interaction: discord.Interaction, rounds: int):
    """
    Start a multi-round trivia game in this channel.
    Usage: /trivia rounds:10  (between 5 and 100 rounds)
    """
    if interaction.channel is None:
        await interaction.response.send_message(
            "I can only run trivia in a text channel.",
            ephemeral=True,
        )
        return

    channel = interaction.channel

    # Validate rounds
    if rounds < 5 or rounds > 100:
        await interaction.response.send_message(
            "Pick a number between **5 and 100** rounds. I refuse to work outside those limits.",
            ephemeral=True,
        )
        return

    # Prevent starting a game if one is already running
    state = GAMES.get(channel.id)
    if state and state.get("in_progress"):
        await interaction.response.send_message(
            "There’s already a trivia game running in this channel. Calm down.",
            ephemeral=True,
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

    # Respond to the interaction so Discord stops showing "thinking"
    await interaction.response.send_message(
        f"Starting a trivia game with **{rounds} questions.**\n"
        f"Fastest correct answer wins each round. Try not to embarrass yourselves.\n\n"
    )

    # Ask the first question as normal channel messages
    await ask_next_round(channel, state)


@bot.tree.command(
    name="trivia_stop",
    description="Force-stop any ongoing trivia in this channel.",
)
async def trivia_stop(interaction: discord.Interaction):
    """
    Force-stop any ongoing trivia in this channel.
    Shows scores if stopping a multi-round game.
    """
    if interaction.channel is None:
        await interaction.response.send_message(
            "I can only stop trivia in a text channel.",
            ephemeral=True,
        )
        return

    channel = interaction.channel
    channel_id = channel.id

    # 1) Stop multi-round game if active
    game_state = GAMES.get(channel_id)
    if game_state and game_state.get("in_progress"):
        game_state["in_progress"] = False
        game_state["current_question"] = None
        game_state["winner_id"] = None

        scores = game_state.get("scores", {})

        if scores:
            # respond to the slash command
            await interaction.response.send_message(
                "⛔ **Trivia game stopped early. Here's your scoreboard:**"
            )
            # scoreboard goes as a normal channel message
            await end_game(channel, game_state)
        else:
            await interaction.response.send_message(
                "⛔ **Trivia game stopped.** No scores to show."
            )

        return

    # 2) Nothing running
    await interaction.response.send_message("There's no trivia running here.")


# -----------------------------
# LEADERBOARD COMMANDS
# -----------------------------
@bot.tree.command(
    name="leaderboard",
    description="Show the top trivia players in this server.",
)
async def leaderboard(interaction: discord.Interaction):
    # Only works in servers
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=False)

    guild_id = interaction.guild.id
    rows = await get_leaderboard(guild_id, limit=10)

    if not rows:
        await interaction.followup.send(
            "No one is on the leaderboard yet. Answer a question to claim the top spot!"
        )
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        user_id = row["user_id"]
        display_name = row["display_name"] or f"<@{user_id}>"
        score_total = row["score_total"]

        # Try to resolve current nickname/display name
        member = interaction.guild.get_member(user_id)
        if member is not None:
            display_name = member.display_name

        lines.append(f"**#{idx}** — {display_name} — {score_total} pts")

    embed = discord.Embed(
        title="🏆 Monji Leaderboard",
        description="\n".join(lines),
    )
    embed.set_footer(text=f"Server: {interaction.guild.name}")

    await interaction.followup.send(embed=embed)


@bot.tree.command(
    name="leaderboard_me",
    description="Show your rank and score in this server.",
)
async def leaderboard_me(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    guild_id = interaction.guild.id
    user_id = interaction.user.id

    result = await get_user_rank(guild_id, user_id)
    if result is None:
        await interaction.followup.send(
            "You're not on the leaderboard yet. Answer a question to earn your first points!"
        )
        return

    rank, score_total = result
    display_name = interaction.user.display_name

    embed = discord.Embed(
        title="📊 Your Monji Rank",
        description=(
            f"{display_name}, you are **#{rank}** in this server "
            f"with **{score_total}** points."
        ),
    )
    embed.set_footer(text=f"Server: {interaction.guild.name}")

    await interaction.followup.send(embed=embed)


# -----------------------------
# MULTI-ROUND HELPERS
# -----------------------------
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
        f"❓ **Question {state['round']} of {state['max_rounds']}**\n"
        f"{q['question']}\n\n"
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
        guild = channel.guild
        member = guild.get_member(user_id) if guild else None
        name = member.display_name if member else f"User {user_id}"
        lines.append(f"**{i}. {name}** — {score} point(s)")

    msg = "🎮 **Game over.** Here’s the damage:\n" + "\n".join(lines)
    await channel.send(msg)


# -----------------------------
# HINT / TIMEOUT HANDLER
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


# -----------------------------
# MESSAGE LISTENER (CHECK ANSWERS)
# -----------------------------
@bot.event
async def on_message(message: discord.Message):
    """
    Listen to all messages so we can check if they answer
    an active multi-round game question.
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

                # Update in-memory game score
                scores = game_state["scores"]
                scores[message.author.id] = scores.get(message.author.id, 0) + 1

                # Award 1 leaderboard point (multi-round)
                if message.guild is not None:
                    guild_id = message.guild.id
                    user_id = message.author.id
                    display_name = message.author.display_name

                    points = 1
                    await award_points(guild_id, user_id, display_name, points)

                await channel.send(
                    "✅ {mention} got it right. Correct answer: **{answer}**.".format(
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

    # Allow commands (/ping, /trivia, /trivia_stop, etc.) to still work
    await bot.process_commands(message)


def main():
    """Entry point when running `python -m monji_bot.bot`."""
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    main()

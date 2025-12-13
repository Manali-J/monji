# monji_bot/bot.py

import asyncio

import discord
from discord.ext import commands

from monji_bot.llm.commentary import generate_reply
from monji_bot.scramble.scramble_lifecycle import ask_next_scramble_round, end_scramble_game
from monji_bot.scramble.scramble_manager import reset_scramble_session
from monji_bot.trivia.constants import GAMES, EVENT_MENTION, KEY_TEXT, MODE_TRIVIA, MODE_SCRAMBLE
from monji_bot.trivia.lifecycle import end_game, ask_next_round
from monji_bot.trivia.resolution import resolve_round_winner
from monji_bot.common.state import GameState, CorrectCandidate
from .config import BOT_TOKEN
from .db import init_schema, get_leaderboard, get_user_rank
from .trivia.manager import reset_session_questions
from .utils.fuzzy import is_correct_answer

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # needed for resolving display names

bot = commands.Bot(
    command_prefix="!",  # prefix is unused now, but harmless to keep
    intents=intents,
    help_command=None,
)

async def start_game(
    *,
    interaction: discord.Interaction,
    rounds: int,
    mode: str,
    reset_session,
    ask_next_round,
    start_message: str,
):
    reset_session()

    if interaction.channel is None:
        await interaction.response.send_message(
            "I can only run games in a text channel.",
            ephemeral=True,
        )
        return

    channel = interaction.channel

    if rounds < 5 or rounds > 100:
        await interaction.response.send_message(
            "Pick a number between **5 and 100** rounds.",
            ephemeral=True,
        )
        return

    existing = GAMES.get(channel.id)
    if existing and existing.in_progress:
        await interaction.response.send_message(
            "There’s already a game running in this channel.",
            ephemeral=True,
        )
        return

    state = GameState.new(rounds)
    state.mode = mode  # lightweight, explicit
    GAMES[channel.id] = state

    await interaction.response.send_message(start_message)
    await ask_next_round(channel, state)


async def stop_game(
    *,
    interaction: discord.Interaction,
    mode: str,
    end_game,
):
    if interaction.channel is None:
        await interaction.response.send_message(
            "I can only stop games in a text channel.",
            ephemeral=True,
        )
        return

    channel = interaction.channel
    state = GAMES.get(channel.id)

    if not state or not state.in_progress or getattr(state, "mode", None) != mode:
        await interaction.response.send_message(
            f"There’s no {mode} game running here.",
            ephemeral=True,
        )
        return

    state.in_progress = False

    await interaction.response.send_message(
        f"⛔ **{mode.capitalize()} game stopped.**"
    )

    await end_game(channel, state)


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

@bot.tree.command(
    name="trivia",
    description="Start a multi-round trivia game in this channel.",
)
async def trivia(interaction: discord.Interaction, rounds: int):
    await start_game(
        interaction=interaction,
        rounds=rounds,
        mode="trivia",
        reset_session=reset_session_questions,
        ask_next_round=ask_next_round,
        start_message=(
            f"Starting a trivia game with **{rounds} questions.**\n"
            f"Fastest correct answer wins each round. Try not to embarrass yourselves.\n\n"
        ),
    )

@bot.tree.command(
    name="trivia_stop",
    description="Force-stop any ongoing trivia in this channel.",
)
async def trivia_stop(interaction: discord.Interaction):
    await stop_game(
        interaction=interaction,
        mode="trivia",
        end_game=end_game,
    )

@bot.tree.command(
    name="scramble",
    description="Start a multi-round word scramble game in this channel.",
)
async def scramble(interaction: discord.Interaction, rounds: int):
    await start_game(
        interaction=interaction,
        rounds=rounds,
        mode="scramble",
        reset_session=reset_scramble_session,
        ask_next_round=ask_next_scramble_round,
        start_message=(
            f"🔀 Starting a **{rounds}-round scramble game**.\n"
            f"Unscramble the word. Fastest answer wins.\n\n"
        ),
    )

@bot.tree.command(
    name="scramble_stop",
    description="Force-stop any ongoing scramble game in this channel.",
)
async def scramble_stop(interaction: discord.Interaction):
    await stop_game(
        interaction=interaction,
        mode="scramble",
        end_game=end_scramble_game,
    )

# -----------------------------
# MESSAGE LISTENER (CHECK ANSWERS)
# -----------------------------
@bot.event
async def on_message(message: discord.Message):
    """
    Listen to all messages so we can check if they answer
    an active multi-round game question, and also make Monji
    respond when mentioned.
    """
    # Ignore messages from bots (including Monji)
    if message.author.bot:
        return

    channel = message.channel

    # 1) Check if there is an active multi-round game in this channel
    game_state = GAMES.get(channel.id)
    if (
            game_state
            and game_state.in_progress
            and game_state.current_question
    ):
        user_answer = message.content.strip()

        is_correct = False

        if game_state.mode == MODE_TRIVIA:
            correct_answers = game_state.current_question["answers"]
            is_correct = is_correct_answer(user_answer, correct_answers)

        elif game_state.mode == MODE_SCRAMBLE:
            correct_word = game_state.current_question["word"]
            is_correct = user_answer.lower() == correct_word.lower()

        # Shared resolution logic
        if is_correct:
            game_state.correct_candidates.append(
                CorrectCandidate(message=message)
            )

            if len(game_state.correct_candidates) == 1 and game_state.winner_id is None:
                this_round = game_state.round
                game_state.resolving = True
                asyncio.create_task(
                    resolve_round_winner(channel, game_state, this_round)
                )

        # Important: still process commands even during a game
        await bot.process_commands(message)
        return

    # 2) If Monji is mentioned, trigger the LLM reply
    #    (this runs only when there's NO active question waiting)
    if bot.user and bot.user.mentioned_in(message):
        # Remove the bot mention from the message content
        content = message.content
        for mention in message.mentions:
            if mention == bot.user:
                content = content.replace(mention.mention, "").strip()

        # If they only pinged Monji with no text, give LLM some context
        if not content:
            content = "User mentioned you without saying anything. Respond sarcastically."

        # generate_reply is sync, so run it in a thread to not block the event loop
        reply = await asyncio.to_thread(generate_reply, EVENT_MENTION, {KEY_TEXT: content})
        if reply:
            await channel.send(reply)
        return

    # 3) Allow commands (/ping, /trivia, /trivia_stop, etc.) to still work
    await bot.process_commands(message)


def main():
    """Entry point when running `python -m monji_bot.bot`."""
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    main()

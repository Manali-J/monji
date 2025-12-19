import asyncio

import discord
from discord.ext import commands
from discord import app_commands

from monji_bot.llm.commentary import generate_reply
from monji_bot.scramble.scramble_lifecycle import ask_next_scramble_round, end_scramble_game
from monji_bot.scramble.scramble_manager import reset_scramble_session
from monji_bot.trivia.constants import GAMES, EVENT_MENTION, KEY_TEXT, MODE_TRIVIA, MODE_SCRAMBLE, AUTO_RECORD_VC_ID, \
    CRAIG_COMMAND_CHANNEL_ID
from monji_bot.trivia.lifecycle import end_game, ask_next_round
from monji_bot.trivia.resolution import resolve_round_winner
from monji_bot.common.state import GameState, CorrectCandidate
from .config import BOT_TOKEN
from .db import init_schema, get_leaderboard, get_user_rank
from .trivia.manager import reset_session_questions
from .utils.fuzzy import is_correct_answer

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
)

# -----------------------------
# GAME START / STOP HELPERS
# -----------------------------
async def start_game(
    *,
    interaction: discord.Interaction,
    rounds: int,
    mode: str,
    reset_session,
    ask_next_round,
    start_message: str,
):
    if interaction.guild is None or interaction.channel is None:
        await interaction.response.send_message(
            "I can only run games inside a server text channel.",
            ephemeral=True,
        )
        return

    channel = interaction.channel
    guild_id = interaction.guild.id
    key = (guild_id, channel.id)

    if rounds < 5 or rounds > 100:
        await interaction.response.send_message(
            "Pick a number between **5 and 100** rounds.",
            ephemeral=True,
        )
        return

    existing = GAMES.get(key)
    if existing and existing.in_progress:
        await interaction.response.send_message(
            "There’s already a game running in this channel.",
            ephemeral=True,
        )
        return

    # IMPORTANT: reset session per guild
    reset_session(guild_id)

    state = GameState.new(rounds)
    state.mode = mode
    state.guild_id = guild_id

    GAMES[key] = state

    await interaction.response.send_message(start_message)
    await ask_next_round(channel, state)


async def stop_game(
    *,
    interaction: discord.Interaction,
    mode: str,
    end_game,
):
    if interaction.guild is None or interaction.channel is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    channel = interaction.channel
    key = (interaction.guild.id, channel.id)

    state = GAMES.get(key)

    if not state or not state.in_progress or state.mode != mode:
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

# -----------------------------
# BOT EVENTS
# -----------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    await init_schema()

    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} app commands.")
    except Exception as e:
        print(f"❌ Error syncing app commands: {e}")

# -----------------------------
# COMMANDS
# -----------------------------
@bot.tree.command(name="ping", description="Simple test command.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Pong! Monji is awake... unfortunately.",
        ephemeral=True,
    )

@bot.tree.command(name="leaderboard", description="Show leaderboard.")
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Trivia", value=MODE_TRIVIA),
        app_commands.Choice(name="Scramble", value=MODE_SCRAMBLE),
    ]
)
async def leaderboard(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    await interaction.response.defer()

    rows = await get_leaderboard(
        guild_id=interaction.guild.id,
        mode=mode.value,
        limit=10,
    )

    if not rows:
        await interaction.followup.send(
            f"No one is on the **{mode.value}** leaderboard yet."
        )
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        member = interaction.guild.get_member(row["user_id"])
        name = member.display_name if member else row["display_name"] or f"<@{row['user_id']}>"
        lines.append(f"**#{idx}** — {name} — {row['score_total']} pts")

    await interaction.followup.send(
        embed=discord.Embed(
            title=f"🏆 {mode.value.capitalize()} Leaderboard",
            description="\n".join(lines),
        )
    )

@bot.tree.command(name="trivia", description="Start trivia.")
async def trivia(interaction: discord.Interaction, rounds: int):
    await start_game(
        interaction=interaction,
        rounds=rounds,
        mode=MODE_TRIVIA,
        reset_session=reset_session_questions,
        ask_next_round=ask_next_round,
        start_message=f"🧠 Starting trivia with **{rounds} questions**.\n",
    )

@bot.tree.command(name="trivia_stop", description="Stop trivia.")
async def trivia_stop(interaction: discord.Interaction):
    await stop_game(
        interaction=interaction,
        mode=MODE_TRIVIA,
        end_game=end_game,
    )

@bot.tree.command(name="scramble", description="Start scramble.")
async def scramble(interaction: discord.Interaction, rounds: int):
    await start_game(
        interaction=interaction,
        rounds=rounds,
        mode=MODE_SCRAMBLE,
        reset_session=reset_scramble_session,
        ask_next_round=ask_next_scramble_round,
        start_message=f"🔀 Starting scramble with **{rounds} rounds**.\n",
    )

@bot.tree.command(name="scramble_stop", description="Stop scramble.")
async def scramble_stop(interaction: discord.Interaction):
    await stop_game(
        interaction=interaction,
        mode=MODE_SCRAMBLE,
        end_game=end_scramble_game,
    )

# -----------------------------
# MESSAGE LISTENER
# -----------------------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    channel = message.channel
    key = (message.guild.id, channel.id)
    game_state = GAMES.get(key)

    if game_state and game_state.in_progress and game_state.current_question:
        user_answer = message.content.strip()
        is_correct = False

        if game_state.mode == MODE_TRIVIA:
            is_correct = is_correct_answer(
                user_answer,
                game_state.current_question["answers"],
            )
        elif game_state.mode == MODE_SCRAMBLE:
            is_correct = user_answer.lower() == game_state.current_question["word"].lower()

        if is_correct:
            game_state.correct_candidates.append(CorrectCandidate(message=message))

            if len(game_state.correct_candidates) == 1 and game_state.winner_id is None:
                game_state.resolving = True
                asyncio.create_task(
                    resolve_round_winner(channel, game_state, game_state.round)
                )

        await bot.process_commands(message)
        return

    if bot.user and bot.user.mentioned_in(message):
        content = message.content.replace(bot.user.mention, "").strip() or \
                  "User mentioned you without saying anything. Respond sarcastically."

        reply = await asyncio.to_thread(
            generate_reply,
            EVENT_MENTION,
            {KEY_TEXT: content},
        )
        if reply:
            await channel.send(reply)
        return

    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    # Ignore bots (Craig, Monji, etc.)
    if member.bot:
        return

    guild = member.guild
    if guild is None:
        return

    text_channel = guild.get_channel(CRAIG_COMMAND_CHANNEL_ID)
    if text_channel is None:
        return

    # ---------- USER JOINED VC ----------
    if after.channel and after.channel.id == AUTO_RECORD_VC_ID:
        humans = [m for m in after.channel.members if not m.bot]

        # First human joins → start recording
        if len(humans) == 1:
            await text_channel.send(
                f"/join channel #snowy-voices"
            )

    # ---------- USER LEFT VC ----------
    if before.channel and before.channel.id == AUTO_RECORD_VC_ID:
        humans = [m for m in before.channel.members if not m.bot]

        # Last human leaves → stop recording
        if len(humans) == 0:
            await text_channel.send("/stop")

# -----------------------------
# ENTRY POINT
# -----------------------------
def main():
    bot.run(BOT_TOKEN)

if __name__ == "__main__":
    main()

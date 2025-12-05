# monji_bot/bot.py

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

# Per-channel active question state:
# channel_id -> { "question": str, "answers": [str], "winner_id": int | None }
ACTIVE_QUESTIONS: dict[int, dict] = {}


@bot.event
async def on_ready():
    # Load questions from questions.json when Monji starts
    load_questions()
    print(f"Monji is online as {bot.user}")


@bot.command()
async def ping(ctx: commands.Context):
    """Simple test command."""
    await ctx.send("Pong! Monji is awake... unfortunately.")


@bot.command(name="trivia")
async def trivia_command(ctx: commands.Context):
    """
    Start a single trivia question in this channel.
    Monji will ask a question, and the first correct typed answer wins.
    """
    channel = ctx.channel

    # If there's already an active question with no winner, don't start another
    state = ACTIVE_QUESTIONS.get(channel.id)
    if state and state.get("winner_id") is None:
        await ctx.send(
            "There’s already a question running here. Try answering that one first, overachiever."
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


@bot.event
async def on_message(message: discord.Message):
    """
    Listen to all messages so we can check if they answer the active trivia question.
    """
    # Ignore messages from bots (including Monji)
    if message.author.bot:
        return

    channel = message.channel

    # If this channel has an active question, check the answer
    state = ACTIVE_QUESTIONS.get(channel.id)
    if state and state.get("winner_id") is None:
        user_answer = message.content
        correct_answers = state["answers"]

        for correct in correct_answers:
            if is_fuzzy_match(user_answer, correct):
                # Mark winner
                state["winner_id"] = message.author.id

                # Sarcastic win message
                await channel.send(
                    "✅ {mention} got it right. I’ll pretend I’m not impressed.\n"
                    "Correct answer: **{answer}**.".format(
                        mention=message.author.mention,
                        answer=correct
                    )
                )

                # Clear the active question (so you can start a new one with !trivia)
                # If you want to keep history, you could instead keep it but leave winner_id set.
                # Here we just remove it.
                ACTIVE_QUESTIONS.pop(channel.id, None)
                break

    # Important: still allow commands (!ping, !trivia, etc.)
    await bot.process_commands(message)


def main():
    """Entry point when running `python -m monji_bot.bot`."""
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    main()

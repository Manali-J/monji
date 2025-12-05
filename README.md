# Monji - Discord Trivia Bot

Monji is a humorous & sarcastic trivia bot designed for Discord.
This version uses PostgreSQL for storing trivia questions.

## Features
- Slash commands
- Trivia game (coming soon)
- PostgreSQL backend
- Fully async

## Running locally

1. Create `.env` file:
BOT_TOKEN=your_token_here
DATABASE_URL=postgresql://user:pass@localhost:5432/monji

2. Install dependencies: pip install -r requirements.txt

3. Start the bot: python -m monji_bot.bot
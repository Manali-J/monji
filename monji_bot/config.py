# monji_bot/config.py

import os
from dotenv import load_dotenv

# Load .env file if present (local development)
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing. Add it to .env or environment variables.")

# DATABASE_URL can be optional initially (if DB not used yet)

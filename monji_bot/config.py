# monji_bot/config.py

import os
from dotenv import load_dotenv

# Load .env file if present (local development)
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_ENABLE_SSL =os.getenv("DB_ENABLE_SSL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing. Add it to .env or environment variables.")


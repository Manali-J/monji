# scripts/test_connection.py

import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv()

async def test():
    print("Testing direct connection...")
    try:
        conn = await asyncpg.connect(
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),  # or put it directly
            database=os.getenv("DB_NAME"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            ssl=os.getenv("DB_ENABLE_SSL"),
        )
        print("CONNECTED OK!")
        await conn.close()
    except Exception as e:
        print("ERROR:", repr(e))

if __name__ == "__main__":
    asyncio.run(test())

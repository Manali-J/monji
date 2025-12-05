# scripts/init_db.py

import asyncio
from monji_bot.db import init_schema

async def main():
    await init_schema()

if __name__ == "__main__":
    asyncio.run(main())

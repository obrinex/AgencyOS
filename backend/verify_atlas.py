import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    load_dotenv()
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "agencyos")
    if not mongo_url:
        raise RuntimeError("MONGO_URL is required")

    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=10000)
    try:
        await client.admin.command("ping")
        db = client[db_name]
        await db.command("ping")
        print(f"MongoDB Atlas connection OK: database={db_name}")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())

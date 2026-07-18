"""Purge operational/demo data while preserving users and company settings.

Run only with --confirm. This is intended for the final clean-up before hosting.
"""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

from database import db, client


COLLECTIONS = (
    "clients", "contacts", "leads", "lead_activities", "projects", "milestones",
    "tasks", "time_entries", "invoices", "expenses", "proposals",
    "contracts", "tickets", "files", "notes", "notifications", "audit_logs",
    "automation_logs", "counters", "meetings", "kb_articles", "ai_chat_messages",
    "vault_entries", "google_oauth_states", "booking_settings", "leadform_settings",
)


async def main():
    if "--confirm" not in sys.argv:
        raise SystemExit("Refusing to delete data without --confirm")
    for collection in COLLECTIONS:
        await db[collection].delete_many({})
    await db.users.delete_many({"role": "client"})
    await db.password_reset_tokens.delete_many({})
    await db.login_attempts.delete_many({})
    print("Operational data cleared. Users and company settings were preserved.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())

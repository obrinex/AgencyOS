"""Purge operational data for a fresh start, preserving logins and settings.

    python clear_operational_data.py                  # dry run - shows what would go
    python clear_operational_data.py --confirm        # delete (writes a backup first)
    python clear_operational_data.py --confirm --no-backup

Dry run is the default because this is irreversible and usually aimed at a
production database. It prints the target cluster first: check that it is the
database you mean before adding --confirm.

To purge the deployed CRM, point MONGO_URL at Atlas for the run:

    MONGO_URL="mongodb+srv://..." DB_NAME=agencyos python clear_operational_data.py
"""
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# .env.purge wins when present: it is how a one-off production purge is pointed
# at Atlas without putting the connection string on a command line (where it
# would land in shell history). Blank entries are ignored so a half-filled
# template silently falls back to .env instead of connecting nowhere.
_purge_env = Path(__file__).with_name(".env.purge")
if _purge_env.exists():
    from dotenv import dotenv_values

    for _k, _v in dotenv_values(_purge_env).items():
        if _v and _v.strip():
            os.environ[_k] = _v.strip()
load_dotenv(Path(__file__).with_name(".env"))

from database import db, client

# Operational records: wiped for a fresh start.
COLLECTIONS = (
    "clients", "contacts", "leads", "lead_activities", "projects", "milestones",
    "tasks", "time_entries", "invoices", "expenses", "proposals",
    "contracts", "tickets", "files", "notes", "notifications", "audit_logs",
    "automation_logs", "counters", "meetings", "kb_articles", "ai_chat_messages",
    "vault_entries", "google_oauth_states", "booking_settings", "leadform_settings",
    # Payment records. payment_links holds real money-collection links, so it
    # must go too; payment_requests is a leftover of the removed ask-for-link
    # flow and should not linger.
    "payment_links", "payment_requests",
)

# Deliberately preserved: without these you cannot log in, and the agency's own
# configuration is not "operational data".
PRESERVED = (
    "users",             # admin/staff logins (client-role users ARE removed)
    "company_settings",  # company name, branding
    "payment_settings",  # crypto wallets, payment config
    "brand_assets",      # uploaded logo
    "fx_rates",          # exchange-rate cache, not business data
    "system_state",      # cron bookkeeping
)


def target() -> str:
    url = os.environ.get("MONGO_URL", "")
    safe = re.sub(r"://[^@]*@", "://***@", url)
    return f"{safe[:70]}  db={os.environ.get('DB_NAME')}"


async def snapshot() -> dict:
    counts = {}
    for name in COLLECTIONS:
        counts[name] = await db[name].count_documents({})
    counts["users (client role)"] = await db.users.count_documents({"role": "client"})
    return counts


async def backup(path: Path) -> int:
    """Dump everything about to be emptied, so a mistake stays recoverable."""
    path.mkdir(parents=True, exist_ok=True)
    total = 0
    for name in COLLECTIONS:
        docs = await db[name].find({}).to_list(100000)
        if not docs:
            continue
        for d in docs:
            d["_id"] = str(d["_id"])
        (path / f"{name}.json").write_text(
            json.dumps(docs, indent=2, default=str), encoding="utf-8"
        )
        total += len(docs)

    portal_users = await db.users.find({"role": "client"}).to_list(10000)
    if portal_users:
        for d in portal_users:
            d["_id"] = str(d["_id"])
            d.pop("password_hash", None)  # never write credentials to disk
        (path / "users_client_role.json").write_text(
            json.dumps(portal_users, indent=2, default=str), encoding="utf-8"
        )
        total += len(portal_users)
    return total


async def main() -> int:
    confirm = "--confirm" in sys.argv
    do_backup = "--no-backup" not in sys.argv

    print(f"Target: {target()}\n")
    counts = await snapshot()
    live = {k: v for k, v in counts.items() if v}

    if not live:
        print("Nothing to clear - already a clean slate.")
        client.close()
        return 0

    print("WILL BE DELETED:")
    for name, count in sorted(live.items(), key=lambda kv: -kv[1]):
        print(f"   {name:28} {count}")
    print(f"\n   total documents: {sum(live.values())}")
    print("\nPRESERVED: " + ", ".join(PRESERVED))
    print("   (staff logins, company + payment settings, branding)")

    if not confirm:
        print("\nDRY RUN - nothing was deleted.")
        print("Check the target above is the right database, then re-run with --confirm.")
        client.close()
        return 0

    if do_backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = Path(__file__).with_name("backups") / f"purge-{stamp}"
        written = await backup(out)
        print(f"\nBackup: {written} documents -> {out}")

    print("\nDeleting...")
    for name in COLLECTIONS:
        await db[name].delete_many({})
    await db.users.delete_many({"role": "client"})
    await db.password_reset_tokens.delete_many({})
    await db.login_attempts.delete_many({})

    remaining = sum((await snapshot()).values())
    print(f"Done. Operational documents remaining: {remaining}")
    print("Staff logins, company settings and payment settings were preserved.")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

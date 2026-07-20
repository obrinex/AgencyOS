"""Restore configuration collections from a purge backup.

The purge treats booking_settings and leadform_settings as operational data,
but they are really configuration: wiping them takes the public booking page
and lead form offline until they are set up again. This restores them from a
backup without touching anything else.

    python restore_settings.py backups/purge-YYYYMMDD-HHMMSS            # dry run
    python restore_settings.py backups/purge-YYYYMMDD-HHMMSS --confirm

Point MONGO_URL at the target database first (or fill .env.purge), exactly as
with the purge script.
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv, dotenv_values

_purge_env = Path(__file__).with_name(".env.purge")
if _purge_env.exists():
    for _k, _v in dotenv_values(_purge_env).items():
        if _v and _v.strip():
            os.environ[_k] = _v.strip()
load_dotenv(Path(__file__).with_name(".env"))

from bson import ObjectId

from database import db, client

# Configuration only. Business records are deliberately not restorable here -
# undoing a "fresh start" by hand is not what this script is for.
RESTORABLE = ("booking_settings", "leadform_settings")


def target() -> str:
    url = os.environ.get("MONGO_URL", "")
    return f"{re.sub(r'://[^@]*@', '://***@', url)[:70]}  db={os.environ.get('DB_NAME')}"


async def main() -> int:
    if len(sys.argv) < 2:
        sys.exit("Usage: python restore_settings.py <backup-dir> [--confirm]")
    backup = Path(sys.argv[1])
    if not backup.is_dir():
        sys.exit(f"! Not a directory: {backup}")
    confirm = "--confirm" in sys.argv

    print(f"Target: {target()}")
    print(f"Backup: {backup}\n")

    planned = []
    for name in RESTORABLE:
        f = backup / f"{name}.json"
        if not f.exists():
            print(f"  {name}: not in this backup")
            continue
        docs = json.loads(f.read_text(encoding="utf-8"))
        existing = await db[name].count_documents({})
        planned.append((name, docs, existing))
        print(f"  {name}: {len(docs)} record(s) to restore "
              f"({'collection currently empty' if not existing else f'{existing} already present - will NOT overwrite'})")

    if not confirm:
        print("\nDRY RUN - nothing written. Re-run with --confirm.")
        client.close()
        return 0

    print()
    for name, docs, existing in planned:
        if existing:
            print(f"  {name}: skipped, already has data")
            continue
        for d in docs:
            # Preserve the original _id so any reference to it still resolves.
            if isinstance(d.get("_id"), str) and ObjectId.is_valid(d["_id"]):
                d["_id"] = ObjectId(d["_id"])
            await db[name].insert_one(d)
        print(f"  {name}: restored {len(docs)} record(s)")

    print("\nDone.")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

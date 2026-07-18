"""Repair non-INR records that were saved with a 1:1 conversion rate.

Before live rates were wired in, `conversion_rate` defaulted to 1.0 whenever
nobody typed one. A $100 invoice therefore counted as ₹100 in every dashboard
total — understating USD revenue by roughly the exchange rate.

Dry-run by default. Nothing is written without --apply, because this edits
financial history.

    python backfill_fx_rates.py                 # report only
    python backfill_fx_rates.py --apply         # write live rates
    python backfill_fx_rates.py --apply --rate 96.3   # pin a rate you choose
"""
import argparse
import asyncio
import sys

import fx
from database import db

COLLECTIONS = ("invoices", "expenses")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the changes")
    parser.add_argument("--rate", type=float, default=None,
                        help="use this rate instead of the live one")
    args = parser.parse_args()

    if args.rate:
        rate, source = args.rate, "manual-backfill"
    else:
        info = await fx.get_rate("USD", "INR")
        rate, source = info["rate"], f"{info['source']}-backfill"
        if info["stale"]:
            print(f"! Live rate unavailable; would use last known {rate} ({info['source']})")

    print(f"Rate: 1 USD = INR {rate}  (source: {source})")
    print(f"Mode: {'APPLY — records will be updated' if args.apply else 'DRY RUN — nothing written'}\n")

    grand_total = 0
    for name in COLLECTIONS:
        coll = getattr(db, name)
        # Only rows still sitting at the 1:1 default; anything deliberately set
        # to another value is left alone.
        query = {"currency": {"$nin": [None, "INR"]},
                 "$or": [{"conversion_rate": 1.0}, {"conversion_rate": 1},
                         {"conversion_rate": None}, {"conversion_rate": {"$exists": False}}]}
        docs = await coll.find(query).to_list(5000)
        if not docs:
            print(f"{name}: nothing to fix")
            continue

        print(f"{name}: {len(docs)} record(s) with a 1:1 rate")
        for d in docs[:10]:
            label = d.get("invoice_number") or d.get("description") or str(d["_id"])
            amount = d.get("total") if "total" in d else d.get("amount")
            print(f"   {label}: {d.get('currency')} {amount} → INR {round((amount or 0) * rate, 2)}")
        if len(docs) > 10:
            print(f"   … and {len(docs) - 10} more")

        if args.apply:
            for d in docs:
                await coll.update_one(
                    {"_id": d["_id"]},
                    {"$set": {"conversion_rate": rate, "conversion_rate_source": source}},
                )
            print(f"   updated {len(docs)} record(s)")
        grand_total += len(docs)
        print()

    if not grand_total:
        print("Nothing needed fixing.")
    elif not args.apply:
        print(f"{grand_total} record(s) would change. Re-run with --apply to write them.")
    else:
        print(f"Done — {grand_total} record(s) updated.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

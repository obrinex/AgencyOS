"""Verification: admin-set custom portal passwords, against real MongoDB.

  - create a portal user with a chosen password -> that password logs in
  - reset to a chosen password -> the new one logs in, and it's what was asked
  - reset with no body -> still works, still random (unchanged behaviour)
  - a too-short custom password is refused, and nothing is changed
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "portal_pw_scratch")

PASS, FAIL = [], []


def check(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")


async def main() -> int:
    from fastapi import HTTPException

    from database import db, client
    from auth_utils import verify_password
    from routers.clients import (create_portal_user, reset_portal_user_password,
                                 PortalUserCreate, ResetPortalPasswordRequest)

    await client.drop_database(db.name)
    print(f"\n=== scratch db: {db.name} (dropped clean) ===\n")
    staff = {"id": "000000000000000000000001"}

    cid = str((await db.clients.insert_one({"company_name": "Acme Corp"})).inserted_id)

    async def portal_hash():
        c = await db.clients.find_one({"company_name": "Acme Corp"})
        u = await db.users.find_one({"_id": __import__("bson").ObjectId(c["portal_user_id"])})
        return u["password_hash"], c.get("portal_temp_password")

    # --- 1. create with a custom password ------------------------------------
    print("1. Create with a custom password")
    await create_portal_user(cid, PortalUserCreate(
        email="dana@example.com", name="Dana", custom_password="Sup3rSecret!"), staff)
    h, stored = await portal_hash()
    check("the chosen password logs in", verify_password("Sup3rSecret!", h))
    check("a random one does not", not verify_password("Sup3rSecret?", h))
    check("stored credential matches what was set", stored == "Sup3rSecret!")

    # --- 2. reset to a custom password ---------------------------------------
    print("\n2. Reset to a custom password")
    out = await reset_portal_user_password(
        cid, ResetPortalPasswordRequest(custom_password="Another0ne#2026"), staff)
    h, _ = await portal_hash()
    check("the new chosen password logs in", verify_password("Another0ne#2026", h))
    check("the previous password no longer works", not verify_password("Sup3rSecret!", h))
    check("response echoes the set password", out["temp_password"] == "Another0ne#2026")

    # --- 3. reset with no body still generates a random one ------------------
    print("\n3. Reset with no custom password (random, unchanged behaviour)")
    out = await reset_portal_user_password(cid, None, staff)
    h, _ = await portal_hash()
    check("a random password was generated", bool(out["temp_password"]) and len(out["temp_password"]) >= 8)
    check("it is not the previous custom one", out["temp_password"] != "Another0ne#2026")
    check("the random password logs in", verify_password(out["temp_password"], h))

    # --- 4. too-short custom password is refused -----------------------------
    print("\n4. A too-short custom password is refused")
    before_hash, _ = await portal_hash()
    try:
        await reset_portal_user_password(
            cid, ResetPortalPasswordRequest(custom_password="short"), staff)
        check("too-short is rejected", False, "no error raised")
    except HTTPException as exc:
        check("too-short is rejected", exc.status_code == 400, str(exc.status_code))
    after_hash, _ = await portal_hash()
    check("nothing changed on a rejected reset", before_hash == after_hash)

    print(f"\n=== {len(PASS)} passed, {len(FAIL)} failed ===")
    for f in FAIL:
        print(f"  FAILED: {f}")
    await client.drop_database(db.name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

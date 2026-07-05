import os
from datetime import datetime, timezone
from database import db
from auth_utils import hash_password, verify_password


async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@obrinex.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Admin",
            "role": "admin",
            "is_active": True,
            "two_fa_enabled": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"_id": existing["_id"]}, {"$set": {"password_hash": hash_password(admin_password)}})


async def seed_company_settings():
    existing = await db.company_settings.find_one({"key": "main"})
    if not existing:
        await db.company_settings.insert_one({
            "key": "main", "company_name": "Obrinex", "logo_url": None,
            "custom_domain": None, "currency": "USD",
        })

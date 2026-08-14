import os
import jwt
import bcrypt
import pyotp
from datetime import datetime, timezone, timedelta
from fastapi import Request, HTTPException, Depends
from database import db, to_object_id, serialize_doc

JWT_ALGORITHM = "HS256"
ACCESS_EXPIRE_MIN = int(os.environ.get("ACCESS_EXPIRE_MIN", "1440"))
REFRESH_EXPIRE_DAYS = 7


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_EXPIRE_MIN),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRE_DAYS),
        "type": "refresh",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


# Set COOKIE_SECURE=false when serving over plain HTTP (e.g. LAN preview);
# browsers reject Secure cookies on non-HTTPS origins other than localhost.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() != "false"
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax").lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise RuntimeError("COOKIE_SAMESITE must be lax, strict, or none")


def set_auth_cookies(response, access_token: str, refresh_token: str):
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=ACCESS_EXPIRE_MIN * 60, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=604800, path="/")


def clear_auth_cookies(response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        user_id = to_object_id(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"_id": user_id})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="User not found")
    user = serialize_doc(user)
    user.pop("password_hash", None)
    user.pop("two_fa_secret", None)
    return user


def require_roles(*roles):
    async def checker(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


require_admin = require_roles("admin")
require_staff = require_roles("admin", "team_member")
require_client = require_roles("client")

# Modules a team member's access can be limited to. An empty/missing permissions
# list on a team_member means full access (backward compatible). Admins always pass.
#
# The `ai_sdr` and `agents` keys were removed along with the modules they
# gated. Existing team members may still carry them in their stored
# permissions list; an unrecognised entry is simply never matched, so those
# rows need no migration. A new agent system should add its own key here
# rather than reviving either name.
PERMISSION_MODULES = [
    "crm", "emails", "documents", "clients", "projects", "support",
    "calendar", "finance", "knowledge", "vault", "files", "notes", "analytics",
]


def require_module(module: str):
    """Staff-only dependency that also enforces per-member module permissions."""
    async def checker(user: dict = Depends(get_current_user)):
        if user["role"] == "admin":
            return user
        if user["role"] != "team_member":
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        perms = user.get("permissions") or []
        if perms and module not in perms:
            raise HTTPException(status_code=403, detail=f"You don't have access to the {module} module. Ask your admin.")
        return user

    return checker


async def log_audit(user_id: str, action: str, entity_type: str = None, entity_id: str = None,
                    request: Request = None, *,
                    actor_id: str = None, via_run_id: str = None,
                    before: dict = None, after: dict = None):
    """Write an audit row.

    The first five parameters are unchanged and every existing caller keeps
    working. The four additions are keyword-only, so they can never be filled
    by accident from a positional call.

    `via_run_id` is the important one: its presence is what distinguishes an
    agent-caused write from a human one. Every agent-originated write to any
    collection in this application must set it (Velliom spec §3.3). It is
    never set speculatively - a row without it was written by a person.

    Fields are omitted rather than written as null when unset. The indexes on
    `actor_id` and `via_run_id` are sparse, and MongoDB's sparse indexes skip
    only *missing* fields, not null ones - writing nulls would put every
    historical human action into an index meant to hold agent actions.
    """
    doc = {
        "user_id": user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "ip_address": request.client.host if request else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if actor_id is not None:
        doc["actor_id"] = actor_id
    if via_run_id is not None:
        doc["via_run_id"] = via_run_id
    if before is not None:
        doc["before"] = before
    if after is not None:
        doc["after"] = after
    await db.audit_logs.insert_one(doc)


async def check_brute_force(identifier: str):
    rec = await db.login_attempts.find_one({"identifier": identifier})
    if rec and rec.get("count", 0) >= 5:
        locked_until = rec.get("locked_until")
        if locked_until and datetime.fromisoformat(locked_until) > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")


async def record_failed_attempt(identifier: str):
    rec = await db.login_attempts.find_one({"identifier": identifier})
    count = (rec.get("count", 0) if rec else 0) + 1
    locked_until = None
    if count >= 5:
        locked_until = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    await db.login_attempts.update_one(
        {"identifier": identifier},
        {"$set": {"count": count, "locked_until": locked_until}},
        upsert=True,
    )


async def clear_attempts(identifier: str):
    await db.login_attempts.delete_one({"identifier": identifier})


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name="AgencyOS")


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)

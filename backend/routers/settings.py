import secrets
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, require_admin, require_staff, hash_password, log_audit
from email_service import send_invite_email
from finance_utils import SUPPORTED_CURRENCIES

router = APIRouter(prefix="/api/settings", tags=["settings"])


class CompanySettings(BaseModel):
    company_name: Optional[str] = None
    logo_url: Optional[str] = None
    custom_domain: Optional[str] = None
    currency: Optional[str] = "INR"


class TeamInvite(BaseModel):
    email: EmailStr
    name: str
    role: str = "team_member"
    permissions: Optional[List[str]] = []


class TeamUpdate(BaseModel):
    role: Optional[str] = None
    permissions: Optional[List[str]] = None
    is_active: Optional[bool] = None


@router.get("/company")
async def get_company_settings(user: dict = Depends(get_current_user)):
    settings = await db.company_settings.find_one({"key": "main"})
    if not settings:
        settings = {"key": "main", "company_name": "Obrinex", "logo_url": None, "custom_domain": None, "currency": "INR"}
        await db.company_settings.insert_one(settings)
    return serialize_doc(settings)


@router.put("/company")
async def update_company_settings(payload: CompanySettings, user: dict = Depends(require_admin)):
    if payload.currency and payload.currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail=f"Currency must be one of {SUPPORTED_CURRENCIES}")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    await db.company_settings.update_one({"key": "main"}, {"$set": updates}, upsert=True)
    settings = await db.company_settings.find_one({"key": "main"})
    return serialize_doc(settings)


@router.get("/team")
async def list_team(user: dict = Depends(require_staff)):
    members = await db.users.find({"role": {"$in": ["admin", "team_member"]}}).to_list(200)
    result = []
    for m in members:
        m = serialize_doc(m)
        m.pop("password_hash", None)
        m.pop("two_fa_secret", None)
        result.append(m)
    return result


@router.post("/team")
async def invite_team_member(payload: TeamInvite, user: dict = Depends(require_admin)):
    existing = await db.users.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    temp_password = secrets.token_urlsafe(8)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "email": payload.email.lower(), "password_hash": hash_password(temp_password), "name": payload.name,
        "role": payload.role, "permissions": payload.permissions, "is_active": True, "two_fa_enabled": False,
        "created_at": now,
    }
    res = await db.users.insert_one(doc)
    await log_audit(user["id"], "invite_team_member", "user", str(res.inserted_id))
    await send_invite_email(payload.email, payload.name, temp_password)
    member = await db.users.find_one({"_id": res.inserted_id})
    member = serialize_doc(member)
    member.pop("password_hash", None)
    member["temp_password"] = temp_password
    return member


@router.put("/team/{member_id}")
async def update_team_member(member_id: str, payload: TeamUpdate, user: dict = Depends(require_admin)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    result = await db.users.update_one({"_id": to_object_id(member_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Member not found")
    member = await db.users.find_one({"_id": to_object_id(member_id)})
    member = serialize_doc(member)
    member.pop("password_hash", None)
    member.pop("two_fa_secret", None)
    return member


@router.delete("/team/{member_id}")
async def remove_team_member(member_id: str, user: dict = Depends(require_admin)):
    await db.users.delete_one({"_id": to_object_id(member_id)})
    return {"message": "Team member removed"}


@router.get("/audit-logs")
async def get_audit_logs(limit: int = 100, user: dict = Depends(require_admin)):
    logs = await db.audit_logs.find({}).sort("created_at", -1).to_list(limit)
    return serialize_list(logs)

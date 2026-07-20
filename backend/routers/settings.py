import secrets
import base64
import re
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, EmailStr

import cashfree
from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, require_admin, require_staff, hash_password, log_audit, PERMISSION_MODULES
from email_service import send_invite_email, get_brand, build_wrapper, send_email, BRAND_DEFAULTS
from finance_utils import SUPPORTED_CURRENCIES

router = APIRouter(prefix="/api/settings", tags=["settings"])

BACKEND_URL = None  # resolved lazily from env
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
LOGO_MIME = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif", "image/svg+xml"}
MAX_LOGO_BYTES = 1_000_000  # 1 MB


class EmailBrandSettings(BaseModel):
    logo_url: Optional[str] = None
    show_logo: Optional[bool] = None
    brand_name: Optional[str] = None
    tagline: Optional[str] = None
    bg_color: Optional[str] = None
    card_color: Optional[str] = None
    text_color: Optional[str] = None
    muted_color: Optional[str] = None
    accent_color: Optional[str] = None
    accent_text_color: Optional[str] = None
    border_color: Optional[str] = None
    box_color: Optional[str] = None
    footer_text: Optional[str] = None
    footer_note: Optional[str] = None


class TestEmailRequest(BaseModel):
    to: Optional[EmailStr] = None


def _sample_email_html(brand: dict) -> str:
    """A representative branded email body, used for live preview and test sends."""
    accent, atext, box, muted = brand["accent_color"], brand["accent_text_color"], brand["box_color"], brand["muted_color"]
    inner = f"""
      <tr><td style="font-size:22px;font-weight:700;padding-bottom:10px;">Invoice INV-0042</td></tr>
      <tr><td style="font-size:14px;color:{muted};padding-bottom:20px;line-height:1.6;">A new invoice has been issued to your account. The full invoice is attached as a PDF.</td></tr>
      <tr><td style="background:{box};border-radius:10px;padding:18px;font-size:14px;line-height:1.7;">
        Amount Due: <b>INR 25,000.00</b><br/>Due Date: 2026-08-01
      </td></tr>
      <tr><td style="padding-top:22px;">
        <a href="#" style="display:inline-block;background:{accent};color:{atext};padding:12px 24px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:700;">Pay Invoice</a>
      </td></tr>
    """
    return build_wrapper(inner, brand)


@router.get("/email-template")
async def get_email_template(user: dict = Depends(require_staff)):
    brand = await get_brand()
    return {"brand": brand, "defaults": BRAND_DEFAULTS}


@router.get("/email-template/preview")
async def preview_email_template(user: dict = Depends(require_staff)):
    return {"html": _sample_email_html(await get_brand())}


@router.put("/email-template")
async def update_email_template(payload: EmailBrandSettings, user: dict = Depends(require_admin)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    for key, val in updates.items():
        if key.endswith("_color") and isinstance(val, str) and val and not HEX_RE.match(val):
            raise HTTPException(status_code=400, detail=f"{key} must be a hex color like #0B0B0C")
    updates["key"] = "main"
    await db.email_settings.update_one({"key": "main"}, {"$set": updates}, upsert=True)
    await log_audit(user["id"], "update_email_template", "settings", "email")
    return {"brand": await get_brand()}


@router.post("/email-template/logo")
async def upload_email_logo(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    if file.content_type not in LOGO_MIME:
        raise HTTPException(status_code=415, detail="Logo must be a PNG, JPG, WEBP, GIF or SVG image")
    content = await file.read()
    if len(content) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=413, detail="Logo is too large. Keep it under 1 MB.")
    await db.brand_assets.update_one(
        {"key": "email_logo"},
        {"$set": {"key": "email_logo", "data": base64.b64encode(content).decode("ascii"),
                  "content_type": file.content_type, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    import os
    base = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    ver = int(datetime.now(timezone.utc).timestamp())
    logo_url = f"{base}/api/public/brand/logo?v={ver}"
    await db.email_settings.update_one({"key": "main"}, {"$set": {"key": "main", "logo_url": logo_url, "show_logo": True}}, upsert=True)
    await log_audit(user["id"], "upload_email_logo", "settings", "email")
    return {"logo_url": logo_url}


@router.post("/email-template/test")
async def send_test_email(payload: TestEmailRequest, user: dict = Depends(require_admin)):
    to = payload.to or user["email"]
    html = _sample_email_html(await get_brand())
    await send_email(to, "Your Obrinex email — brand preview", html)
    return {"message": f"Test email sent to {to}"}


class CompanySettings(BaseModel):
    company_name: Optional[str] = None
    logo_url: Optional[str] = None
    custom_domain: Optional[str] = None
    currency: Optional[str] = "INR"
    # Postal address for the outreach email footer. CAN-SPAM (US) and PECR
    # (UK/EU) require a physical address on commercial email; India's DPDP
    # does not. Without it, the send agent refuses US/UK recipients rather
    # than dispatching non-compliant mail.
    address: Optional[str] = None


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


class PaymentSettings(BaseModel):
    custom_link_enabled: Optional[bool] = None
    custom_payment_link: Optional[str] = None
    custom_link_label: Optional[str] = None
    crypto_enabled: Optional[bool] = None
    usdt_trc20_address: Optional[str] = None
    usdt_pol_address: Optional[str] = None
    usdt_bep20_address: Optional[str] = None
    btc_address: Optional[str] = None
    eth_address: Optional[str] = None
    sol_address: Optional[str] = None


PAYMENT_DEFAULTS = {
    "key": "main",
    "custom_link_enabled": False,
    "custom_payment_link": "",
    "custom_link_label": "Pay Online",
    "crypto_enabled": False,
    "usdt_trc20_address": "",
    "usdt_pol_address": "",
    "usdt_bep20_address": "",
    "btc_address": "",
    "eth_address": "",
    "sol_address": "",
}


@router.get("/payments")
async def get_payment_settings(user: dict = Depends(require_staff)):
    settings = await db.payment_settings.find_one({"key": "main"})
    if not settings:
        await db.payment_settings.insert_one(dict(PAYMENT_DEFAULTS))
        settings = await db.payment_settings.find_one({"key": "main"})
    data = serialize_doc(settings)
    # Cashfree credentials live in the environment, never the database — the UI
    # only needs to know whether they are present and which mode is active.
    data["cashfree_configured"] = cashfree.is_configured()
    data["cashfree_env"] = cashfree.environment()
    return data


@router.put("/payments")
async def update_payment_settings(payload: PaymentSettings, user: dict = Depends(require_admin)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    await db.payment_settings.update_one({"key": "main"}, {"$set": updates, "$setOnInsert": {"key": "main"}}, upsert=True)
    settings = await db.payment_settings.find_one({"key": "main"})
    await log_audit(user["id"], "update_payment_settings", "settings", "payments")
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


@router.get("/permission-modules")
async def list_permission_modules(user: dict = Depends(require_staff)):
    return {"modules": PERMISSION_MODULES}


@router.put("/team/{member_id}")
async def update_team_member(member_id: str, payload: TeamUpdate, user: dict = Depends(require_admin)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "permissions" in updates:
        invalid = [p for p in updates["permissions"] if p not in PERMISSION_MODULES]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Unknown permission(s): {', '.join(invalid)}")
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
    if member_id == user["id"]:
        raise HTTPException(status_code=400, detail="You can't remove your own account")
    await db.users.delete_one({"_id": to_object_id(member_id)})
    await log_audit(user["id"], "remove_team_member", "user", member_id)
    return {"message": "Team member removed"}


@router.get("/audit-logs")
async def get_audit_logs(limit: int = 100, user: dict = Depends(require_admin)):
    logs = await db.audit_logs.find({}).sort("created_at", -1).to_list(limit)
    return serialize_list(logs)

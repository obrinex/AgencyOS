import secrets
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr

from database import db, serialize_doc
from auth_utils import require_staff

router = APIRouter(prefix="/api", tags=["leadform"])


class LeadFormSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    title: Optional[str] = None
    description: Optional[str] = None


class LeadFormSubmit(BaseModel):
    name: str
    email: EmailStr
    company: str
    phone: Optional[str] = None
    budget: Optional[float] = None
    message: Optional[str] = None


async def _get_or_create_settings() -> dict:
    settings = await db.leadform_settings.find_one({"key": "main"})
    if not settings:
        await db.leadform_settings.insert_one({
            "key": "main",
            "enabled": True,
            "slug": secrets.token_urlsafe(8),
            "title": "Work with us",
            "description": "Tell us about your project and we'll get back to you within 24 hours.",
        })
        settings = await db.leadform_settings.find_one({"key": "main"})
    return settings


@router.get("/leadform/settings")
async def get_leadform_settings(user: dict = Depends(require_staff)):
    return serialize_doc(await _get_or_create_settings())


@router.put("/leadform/settings")
async def update_leadform_settings(payload: LeadFormSettingsUpdate, user: dict = Depends(require_staff)):
    await _get_or_create_settings()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    await db.leadform_settings.update_one({"key": "main"}, {"$set": updates})
    return serialize_doc(await db.leadform_settings.find_one({"key": "main"}))


@router.get("/public/leadform/{slug}")
async def public_leadform_info(slug: str):
    settings = await db.leadform_settings.find_one({"slug": slug})
    if not settings or not settings.get("enabled"):
        raise HTTPException(status_code=404, detail="Form not found")
    company = await db.company_settings.find_one({"key": "main"})
    return {
        "title": settings.get("title"),
        "description": settings.get("description"),
        "company_name": (company or {}).get("company_name") or "Obrinex",
    }


@router.post("/public/leadform/{slug}")
async def public_leadform_submit(slug: str, payload: LeadFormSubmit):
    settings = await db.leadform_settings.find_one({"slug": slug})
    if not settings or not settings.get("enabled"):
        raise HTTPException(status_code=404, detail="Form not found")
    now = datetime.now(timezone.utc).isoformat()
    lead_doc = {
        "company": payload.company,
        "website": None, "industry": None, "employees": None,
        "revenue": payload.budget,
        "location": None, "owner_id": None,
        "source": "website_form", "priority": "medium",
        "email": payload.email, "phone": payload.phone, "linkedin": None,
        "notes": f"Contact: {payload.name}" + (f"\n\n{payload.message}" if payload.message else ""),
        "tags": ["inbound"], "stage": "prospect", "custom_fields": {"contact_name": payload.name},
        "score": 0, "created_at": now, "updated_at": now, "converted_client_id": None,
    }
    res = await db.leads.insert_one(lead_doc)
    lead_id = str(res.inserted_id)
    await db.lead_activities.insert_one({
        "lead_id": lead_id, "type": "note",
        "content": f"Inbound lead via public form. Message: {payload.message or '(none)'}",
        "created_by": None, "created_at": now,
    })
    await db.contacts.insert_one({
        "name": payload.name, "lead_id": lead_id, "client_id": None,
        "company": payload.company, "position": None,
        "email": payload.email, "phone": payload.phone, "linkedin": None,
        "timezone": None, "birthday": None, "notes": None, "created_at": now,
    })
    admins = await db.users.find({"role": "admin"}).to_list(20)
    for a in admins:
        await db.notifications.insert_one({
            "user_id": str(a["_id"]), "type": "new_lead",
            "title": "New inbound lead",
            "message": f"{payload.name} from {payload.company} submitted your lead form.",
            "link": f"/crm/{lead_id}", "read": False, "created_at": now,
        })

    from whatsapp_service import notify_admin as _wa
    await _wa(f"🔥 New lead!\n{payload.name} from {payload.company}\n📧 {payload.email}" +
              (f"\n💰 Budget: {payload.budget:,.0f}" if payload.budget else "") +
              (f"\n📝 {payload.message[:200]}" if payload.message else ""))

    # Fire-and-forget: let the AI draft a reply in the background
    import asyncio

    async def _auto_draft():
        try:
            from routers.ai import generate_lead_reply
            lead = await db.leads.find_one({"_id": res.inserted_id})
            draft = await generate_lead_reply(lead)
            await db.leads.update_one({"_id": res.inserted_id}, {"$set": {"ai_draft_reply": draft}})
        except Exception:
            pass  # no AI key or transient failure — draft can be generated manually later

    asyncio.create_task(_auto_draft())
    return {"message": "Thanks! We'll be in touch shortly."}

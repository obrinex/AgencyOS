from datetime import datetime, timezone
from typing import Optional, List
import csv
import io
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, require_staff, log_audit
from automation_engine import run_won_automation

router = APIRouter(prefix="/api", tags=["crm"])

STAGES = ["prospect", "contacted", "qualified", "discovery", "meeting_scheduled",
          "proposal_sent", "negotiation", "won", "lost", "rejected", "cold"]


class LeadCreate(BaseModel):
    company: str
    website: Optional[str] = None
    industry: Optional[str] = None
    employees: Optional[int] = None
    revenue: Optional[float] = None
    location: Optional[str] = None
    owner_id: Optional[str] = None
    source: Optional[str] = "manual"
    priority: Optional[str] = "medium"
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = []
    stage: Optional[str] = "prospect"
    custom_fields: Optional[dict] = {}


class LeadUpdate(BaseModel):
    company: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    employees: Optional[int] = None
    revenue: Optional[float] = None
    location: Optional[str] = None
    owner_id: Optional[str] = None
    source: Optional[str] = None
    priority: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    score: Optional[int] = None
    custom_fields: Optional[dict] = None


class StagePatch(BaseModel):
    stage: str


class ActivityCreate(BaseModel):
    type: str
    content: str


class ContactCreate(BaseModel):
    name: str
    lead_id: Optional[str] = None
    client_id: Optional[str] = None
    company: Optional[str] = None
    position: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    timezone: Optional[str] = None
    birthday: Optional[str] = None
    notes: Optional[str] = None


@router.get("/leads")
async def list_leads(stage: Optional[str] = None, owner_id: Optional[str] = None, search: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if stage:
        query["stage"] = stage
    if owner_id:
        query["owner_id"] = owner_id
    if search:
        query["company"] = {"$regex": search, "$options": "i"}
    leads = await db.leads.find(query).sort("updated_at", -1).to_list(1000)
    return serialize_list(leads)


@router.post("/leads")
async def create_lead(payload: LeadCreate, user: dict = Depends(require_staff)):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({"score": 0, "owner_id": doc.get("owner_id") or user["id"], "created_at": now, "updated_at": now, "converted_client_id": None})
    res = await db.leads.insert_one(doc)
    await db.lead_activities.insert_one({"lead_id": str(res.inserted_id), "type": "note", "content": "Lead created", "created_by": user["id"], "created_at": now})
    await log_audit(user["id"], "create_lead", "lead", str(res.inserted_id))
    lead = await db.leads.find_one({"_id": res.inserted_id})
    return serialize_doc(lead)


@router.post("/leads/import-csv")
async def import_leads_csv(file: UploadFile = File(...), user: dict = Depends(require_staff)):
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded CSV")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "company" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(status_code=400, detail="CSV must include a 'company' column")

    now = datetime.now(timezone.utc).isoformat()
    imported = 0
    errors = []
    for i, raw_row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        company = row.get("company", "")
        if not company:
            errors.append(f"Row {i}: missing company name")
            continue
        try:
            doc = {
                "company": company,
                "website": row.get("website") or None,
                "industry": row.get("industry") or None,
                "employees": int(row["employees"]) if row.get("employees") else None,
                "revenue": float(row["revenue"]) if row.get("revenue") else None,
                "location": row.get("location") or None,
                "owner_id": user["id"],
                "source": row.get("source") or "csv_import",
                "priority": row.get("priority") or "medium",
                "email": row.get("email") or None,
                "phone": row.get("phone") or None,
                "linkedin": row.get("linkedin") or None,
                "notes": row.get("notes") or None,
                "tags": [],
                "stage": row.get("stage") if row.get("stage") in STAGES else "prospect",
                "custom_fields": {},
                "score": 0, "created_at": now, "updated_at": now, "converted_client_id": None,
            }
        except ValueError as e:
            errors.append(f"Row {i}: invalid number format ({e})")
            continue
        res = await db.leads.insert_one(doc)
        await db.lead_activities.insert_one({"lead_id": str(res.inserted_id), "type": "note", "content": "Lead imported via CSV", "created_by": user["id"], "created_at": now})
        imported += 1

    await log_audit(user["id"], "import_leads_csv", "lead", None)
    return {"imported": imported, "errors": errors}


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"_id": to_object_id(lead_id)})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return serialize_doc(lead)


@router.put("/leads/{lead_id}")
async def update_lead(lead_id: str, payload: LeadUpdate, user: dict = Depends(require_staff)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.leads.update_one({"_id": to_object_id(lead_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead = await db.leads.find_one({"_id": to_object_id(lead_id)})
    return serialize_doc(lead)


@router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, user: dict = Depends(require_staff)):
    await db.leads.delete_one({"_id": to_object_id(lead_id)})
    return {"message": "Lead deleted"}


@router.patch("/leads/{lead_id}/stage")
async def patch_stage(lead_id: str, payload: StagePatch, user: dict = Depends(require_staff)):
    if payload.stage not in STAGES:
        raise HTTPException(status_code=400, detail="Invalid stage")
    lead = await db.leads.find_one({"_id": to_object_id(lead_id)})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    old_stage = lead.get("stage")
    now = datetime.now(timezone.utc).isoformat()
    await db.leads.update_one({"_id": lead["_id"]}, {"$set": {"stage": payload.stage, "updated_at": now}})
    await db.lead_activities.insert_one({"lead_id": lead_id, "type": "stage_change", "content": f"Stage changed from {old_stage} to {payload.stage}", "created_by": user["id"], "created_at": now})

    automation_result = None
    if payload.stage == "won" and old_stage != "won":
        lead["stage"] = "won"
        lead["id"] = lead_id
        automation_result = await run_won_automation(lead, user["id"])

    updated = await db.leads.find_one({"_id": lead["_id"]})
    return {"lead": serialize_doc(updated), "automation": automation_result}


@router.get("/leads/{lead_id}/activities")
async def get_activities(lead_id: str, user: dict = Depends(get_current_user)):
    activities = await db.lead_activities.find({"lead_id": lead_id}).sort("created_at", -1).to_list(500)
    return serialize_list(activities)


@router.post("/leads/{lead_id}/activities")
async def add_activity(lead_id: str, payload: ActivityCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc.update({"lead_id": lead_id, "created_by": user["id"], "created_at": datetime.now(timezone.utc).isoformat()})
    res = await db.lead_activities.insert_one(doc)
    activity = await db.lead_activities.find_one({"_id": res.inserted_id})
    return serialize_doc(activity)


@router.post("/webhooks/lead-capture")
async def webhook_lead_capture(payload: LeadCreate):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({"score": 0, "source": doc.get("source") or "webhook", "created_at": now, "updated_at": now, "converted_client_id": None})
    res = await db.leads.insert_one(doc)
    await db.lead_activities.insert_one({"lead_id": str(res.inserted_id), "type": "note", "content": "Lead captured via webhook", "created_by": None, "created_at": now})
    return {"message": "Lead created", "id": str(res.inserted_id)}


# ---------------- Contacts ----------------

@router.get("/contacts")
async def list_contacts(lead_id: Optional[str] = None, client_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if lead_id:
        query["lead_id"] = lead_id
    if client_id:
        query["client_id"] = client_id
    contacts = await db.contacts.find(query).sort("created_at", -1).to_list(1000)
    return serialize_list(contacts)


@router.post("/contacts")
async def create_contact(payload: ContactCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.contacts.insert_one(doc)
    contact = await db.contacts.find_one({"_id": res.inserted_id})
    return serialize_doc(contact)


@router.put("/contacts/{contact_id}")
async def update_contact(contact_id: str, payload: ContactCreate, user: dict = Depends(require_staff)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    await db.contacts.update_one({"_id": to_object_id(contact_id)}, {"$set": updates})
    contact = await db.contacts.find_one({"_id": to_object_id(contact_id)})
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return serialize_doc(contact)


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, user: dict = Depends(require_staff)):
    await db.contacts.delete_one({"_id": to_object_id(contact_id)})
    return {"message": "Contact deleted"}

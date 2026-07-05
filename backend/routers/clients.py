from datetime import datetime, timezone
import secrets
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, require_staff, require_admin, hash_password, log_audit

router = APIRouter(prefix="/api/clients", tags=["clients"])


class ClientUpdate(BaseModel):
    company_name: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    health_score: Optional[int] = None
    owner_id: Optional[str] = None


class PortalUserCreate(BaseModel):
    email: EmailStr
    name: str


class ChecklistPatch(BaseModel):
    index: int
    done: bool


@router.get("")
async def list_clients(user: dict = Depends(get_current_user)):
    clients = await db.clients.find({}).sort("created_at", -1).to_list(1000)
    result = []
    for c in clients:
        cid = str(c["_id"])
        invoices = await db.invoices.find({"client_id": cid}).to_list(1000)
        projects_count = await db.projects.count_documents({"client_id": cid})
        outstanding = sum(i["total"] for i in invoices if i["status"] in ("sent", "overdue", "partial", "viewed"))
        revenue = sum(i["total"] for i in invoices if i["status"] == "paid")
        c["outstanding_amount"] = outstanding
        c["revenue_generated"] = revenue
        c["projects_count"] = projects_count
        result.append(serialize_doc(c))
    return result


@router.get("/{client_id}")
async def get_client(client_id: str, user: dict = Depends(get_current_user)):
    client = await db.clients.find_one({"_id": to_object_id(client_id)})
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    projects = await db.projects.find({"client_id": client_id}).to_list(200)
    invoices = await db.invoices.find({"client_id": client_id}).sort("created_at", -1).to_list(200)
    contacts = await db.contacts.find({"client_id": client_id}).to_list(200)
    tickets = await db.tickets.find({"client_id": client_id}).to_list(200)
    contracts = await db.contracts.find({"client_id": client_id}).to_list(200)
    outstanding = sum(i["total"] for i in invoices if i["status"] in ("sent", "overdue", "partial", "viewed"))
    revenue = sum(i["total"] for i in invoices if i["status"] == "paid")
    data = serialize_doc(client)
    data["projects"] = serialize_list(projects)
    data["invoices"] = serialize_list(invoices)
    data["contacts"] = serialize_list(contacts)
    data["tickets"] = serialize_list(tickets)
    data["contracts"] = serialize_list(contracts)
    data["outstanding_amount"] = outstanding
    data["revenue_generated"] = revenue
    data["ltv"] = revenue
    return data


@router.put("/{client_id}")
async def update_client(client_id: str, payload: ClientUpdate, user: dict = Depends(require_staff)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.clients.update_one({"_id": to_object_id(client_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    client = await db.clients.find_one({"_id": to_object_id(client_id)})
    return serialize_doc(client)


@router.delete("/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(require_admin)):
    await db.clients.delete_one({"_id": to_object_id(client_id)})
    return {"message": "Client deleted"}


@router.patch("/{client_id}/checklist")
async def patch_checklist(client_id: str, payload: ChecklistPatch, user: dict = Depends(require_staff)):
    client = await db.clients.find_one({"_id": to_object_id(client_id)})
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    checklist = client.get("onboarding_checklist", [])
    if payload.index >= len(checklist):
        raise HTTPException(status_code=400, detail="Invalid checklist index")
    checklist[payload.index]["done"] = payload.done
    await db.clients.update_one({"_id": client["_id"]}, {"$set": {"onboarding_checklist": checklist}})
    return {"onboarding_checklist": checklist}


@router.post("/{client_id}/portal-user")
async def create_portal_user(client_id: str, payload: PortalUserCreate, user: dict = Depends(require_staff)):
    client = await db.clients.find_one({"_id": to_object_id(client_id)})
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    existing = await db.users.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    temp_password = secrets.token_urlsafe(8)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "email": payload.email.lower(),
        "password_hash": hash_password(temp_password),
        "name": payload.name,
        "role": "client",
        "client_id": client_id,
        "is_active": True,
        "two_fa_enabled": False,
        "created_at": now,
    }
    res = await db.users.insert_one(doc)
    await db.clients.update_one({"_id": client["_id"]}, {"$set": {"portal_user_id": str(res.inserted_id)}})
    await log_audit(user["id"], "create_portal_user", "client", client_id)
    print(f"[WELCOME EMAIL] To: {payload.email} | Portal login: {payload.email} / {temp_password}")
    return {"email": payload.email, "temp_password": temp_password, "message": "Portal user created. Temporary password generated (see console log / share securely)."}

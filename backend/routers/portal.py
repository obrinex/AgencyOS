from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import require_client, log_audit
from finance_utils import to_base

router = APIRouter(prefix="/api/portal", tags=["portal"])


class TicketCreate(BaseModel):
    subject: str
    description: str
    priority: Optional[str] = "medium"


class TicketMessage(BaseModel):
    message: str


class MeetingRequest(BaseModel):
    title: str
    preferred_time: str
    notes: Optional[str] = None


class SignRequest(BaseModel):
    signature_name: str


async def get_client_id(user: dict) -> str:
    if not user.get("client_id"):
        raise HTTPException(status_code=403, detail="No client account linked")
    return user["client_id"]


@router.get("/overview")
async def portal_overview(user: dict = Depends(require_client)):
    client_id = await get_client_id(user)
    projects = await db.projects.find({"client_id": client_id}).to_list(200)
    invoices = await db.invoices.find({"client_id": client_id}).to_list(200)
    tickets = await db.tickets.find({"client_id": client_id}).to_list(200)
    outstanding = sum(to_base(i["total"], i.get("conversion_rate")) for i in invoices if i["status"] in ("sent", "overdue", "partial", "viewed"))
    active_projects = [p for p in projects if p["status"] not in ("completed", "archived")]
    open_tickets = [t for t in tickets if t["status"] not in ("resolved", "closed")]
    return {
        "projects_count": len(projects),
        "active_projects_count": len(active_projects),
        "outstanding_amount": outstanding,
        "open_tickets_count": len(open_tickets),
        "recent_projects": serialize_list(sorted(projects, key=lambda p: p.get("updated_at", ""), reverse=True)[:5]),
    }


@router.get("/projects")
async def portal_projects(user: dict = Depends(require_client)):
    client_id = await get_client_id(user)
    projects = await db.projects.find({"client_id": client_id}).to_list(200)
    return serialize_list(projects)


@router.get("/projects/{project_id}")
async def portal_project_detail(project_id: str, user: dict = Depends(require_client)):
    client_id = await get_client_id(user)
    project = await db.projects.find_one({"_id": to_object_id(project_id), "client_id": client_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    tasks = await db.tasks.find({"related_type": "project", "related_id": project_id}).to_list(500)
    total = len(tasks)
    done = len([t for t in tasks if t["status"] == "done"])
    data = serialize_doc(project)
    data["tasks"] = serialize_list(tasks)
    data["progress"] = round((done / total) * 100) if total else 0
    return data


@router.get("/invoices")
async def portal_invoices(user: dict = Depends(require_client)):
    client_id = await get_client_id(user)
    invoices = await db.invoices.find({"client_id": client_id}).sort("created_at", -1).to_list(200)
    return serialize_list(invoices)


@router.get("/invoices/{invoice_id}")
async def portal_invoice_detail(invoice_id: str, user: dict = Depends(require_client)):
    client_id = await get_client_id(user)
    invoice = await db.invoices.find_one({"_id": to_object_id(invoice_id), "client_id": client_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return serialize_doc(invoice)


@router.get("/contracts")
async def portal_contracts(user: dict = Depends(require_client)):
    client_id = await get_client_id(user)
    contracts = await db.contracts.find({"client_id": client_id}).to_list(200)
    return serialize_list(contracts)


@router.post("/contracts/{contract_id}/sign")
async def portal_sign_contract(contract_id: str, payload: SignRequest, user: dict = Depends(require_client)):
    client_id = await get_client_id(user)
    contract = await db.contracts.find_one({"_id": to_object_id(contract_id), "client_id": client_id})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    now = datetime.now(timezone.utc).isoformat()
    await db.contracts.update_one({"_id": contract["_id"]}, {"$set": {
        "status": "signed", "signature_name": payload.signature_name, "signed_at": now,
    }})
    await log_audit(user["id"], "sign_contract", "contract", contract_id)
    updated = await db.contracts.find_one({"_id": contract["_id"]})
    return serialize_doc(updated)


@router.get("/files")
async def portal_files(user: dict = Depends(require_client)):
    client_id = await get_client_id(user)
    files = await db.files.find({"related_type": "client", "related_id": client_id}).to_list(500)
    return serialize_list(files)


@router.get("/tickets")
async def portal_tickets(user: dict = Depends(require_client)):
    client_id = await get_client_id(user)
    tickets = await db.tickets.find({"client_id": client_id}).sort("created_at", -1).to_list(200)
    return serialize_list(tickets)


@router.post("/tickets")
async def portal_create_ticket(payload: TicketCreate, user: dict = Depends(require_client)):
    client_id = await get_client_id(user)
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({"client_id": client_id, "status": "open", "messages": [], "created_at": now, "updated_at": now})
    res = await db.tickets.insert_one(doc)
    ticket = await db.tickets.find_one({"_id": res.inserted_id})
    return serialize_doc(ticket)


@router.post("/tickets/{ticket_id}/messages")
async def portal_ticket_message(ticket_id: str, payload: TicketMessage, user: dict = Depends(require_client)):
    client_id = await get_client_id(user)
    ticket = await db.tickets.find_one({"_id": to_object_id(ticket_id), "client_id": client_id})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    msg = {"sender_id": user["id"], "sender_role": "client", "message": payload.message, "created_at": datetime.now(timezone.utc).isoformat()}
    await db.tickets.update_one({"_id": ticket["_id"]}, {"$push": {"messages": msg}, "$set": {"updated_at": msg["created_at"]}})
    updated = await db.tickets.find_one({"_id": ticket["_id"]})
    return serialize_doc(updated)


@router.post("/meetings")
async def portal_request_meeting(payload: MeetingRequest, user: dict = Depends(require_client)):
    client_id = await get_client_id(user)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "title": payload.title, "client_id": client_id, "notes": payload.notes,
        "start_time": payload.preferred_time, "end_time": None, "status": "requested",
        "created_by": user["id"], "created_at": now,
    }
    res = await db.meetings.insert_one(doc)
    await log_audit(user["id"], "request_meeting", "meeting", str(res.inserted_id))
    return {"message": "Meeting request submitted", "id": str(res.inserted_id)}

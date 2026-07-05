from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, require_staff, require_client

router = APIRouter(prefix="/api/tickets", tags=["support"])


class TicketUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    subject: Optional[str] = None


class TicketMessage(BaseModel):
    message: str
    internal: Optional[bool] = False


@router.get("")
async def list_tickets(status: Optional[str] = None, client_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if user["role"] == "client":
        query["client_id"] = user.get("client_id")
    elif client_id:
        query["client_id"] = client_id
    if status:
        query["status"] = status
    tickets = await db.tickets.find(query).sort("created_at", -1).to_list(500)
    result = []
    for t in tickets:
        client = await db.clients.find_one({"_id": to_object_id(t["client_id"])}) if t.get("client_id") else None
        t = serialize_doc(t)
        t["client_name"] = client.get("company_name") if client else None
        result.append(t)
    return result


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: str, user: dict = Depends(get_current_user)):
    ticket = await db.tickets.find_one({"_id": to_object_id(ticket_id)})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if user["role"] == "client" and ticket.get("client_id") != user.get("client_id"):
        raise HTTPException(status_code=403, detail="Not authorized")
    return serialize_doc(ticket)


@router.put("/{ticket_id}")
async def update_ticket(ticket_id: str, payload: TicketUpdate, user: dict = Depends(require_staff)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.tickets.update_one({"_id": to_object_id(ticket_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ticket = await db.tickets.find_one({"_id": to_object_id(ticket_id)})
    return serialize_doc(ticket)


@router.post("/{ticket_id}/messages")
async def add_message(ticket_id: str, payload: TicketMessage, user: dict = Depends(require_staff)):
    ticket = await db.tickets.find_one({"_id": to_object_id(ticket_id)})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    msg = {"sender_id": user["id"], "sender_role": user["role"], "message": payload.message, "internal": payload.internal, "created_at": datetime.now(timezone.utc).isoformat()}
    await db.tickets.update_one({"_id": ticket["_id"]}, {"$push": {"messages": msg}, "$set": {"updated_at": msg["created_at"]}})
    updated = await db.tickets.find_one({"_id": ticket["_id"]})
    return serialize_doc(updated)

"""Standalone crypto payment links — generate a shareable link for any amount,
not tied to an invoice. Clients open it and pay with crypto."""
import os
import secrets
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import db, serialize_doc, to_object_id
from auth_utils import require_module
from finance_utils import SUPPORTED_CURRENCIES

require_finance = require_module("finance")
router = APIRouter(prefix="/api/payment-links", tags=["payment-links"])


class PaymentLinkCreate(BaseModel):
    title: str
    amount: float
    currency: Optional[str] = "INR"
    note: Optional[str] = None


def _with_url(doc: dict) -> dict:
    d = serialize_doc(doc)
    base = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    d["url"] = f"{base}/pay/{doc['token']}"
    return d


@router.get("")
async def list_payment_links(user: dict = Depends(require_finance)):
    links = await db.payment_links.find({}).sort("created_at", -1).to_list(500)
    return [_with_url(l) for l in links]


@router.post("")
async def create_payment_link(payload: PaymentLinkCreate, user: dict = Depends(require_finance)):
    if payload.amount is None or payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
    currency = (payload.currency or "INR").upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail=f"Currency must be one of {SUPPORTED_CURRENCIES}")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "token": secrets.token_urlsafe(12),
        "title": payload.title.strip() or "Payment",
        "amount": float(payload.amount),
        "currency": currency,
        "note": (payload.note or "").strip(),
        "status": "active",
        "payment_claim": None,
        "created_by": user["id"],
        "created_at": now,
    }
    res = await db.payment_links.insert_one(doc)
    return _with_url(await db.payment_links.find_one({"_id": res.inserted_id}))


@router.post("/{link_id}/mark-paid")
async def mark_link_paid(link_id: str, user: dict = Depends(require_finance)):
    result = await db.payment_links.update_one({"_id": to_object_id(link_id)}, {"$set": {"status": "paid"}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Payment link not found")
    return {"message": "Marked as paid"}


@router.post("/{link_id}/reopen")
async def reopen_link(link_id: str, user: dict = Depends(require_finance)):
    await db.payment_links.update_one({"_id": to_object_id(link_id)}, {"$set": {"status": "active"}})
    return {"message": "Reopened"}


@router.delete("/{link_id}")
async def delete_payment_link(link_id: str, user: dict = Depends(require_finance)):
    await db.payment_links.delete_one({"_id": to_object_id(link_id)})
    return {"message": "Deleted"}

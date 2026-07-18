import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

import cashfree
from database import db, serialize_doc, to_object_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["public"])


class ProposalSignRequest(BaseModel):
    signature_name: str
    signer_email: EmailStr
    accept: bool = True


@router.get("/proposals/{token}")
async def get_public_proposal(token: str):
    proposal = await db.proposals.find_one({"share_token": token})
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal["status"] == "sent":
        await db.proposals.update_one({"_id": proposal["_id"]}, {"$set": {"status": "viewed"}})
        proposal["status"] = "viewed"
    data = serialize_doc(proposal)
    data.pop("versions", None)
    return data


# ---------------- Public brand logo (for email templates) ----------------

@router.get("/brand/logo")
async def public_brand_logo():
    import base64
    from fastapi.responses import Response
    asset = await db.brand_assets.find_one({"key": "email_logo"})
    if not asset or not asset.get("data"):
        raise HTTPException(status_code=404, detail="No logo uploaded")
    try:
        raw = base64.b64decode(asset["data"])
    except Exception:
        raise HTTPException(status_code=500, detail="Logo is corrupted")
    return Response(content=raw, media_type=asset.get("content_type", "image/png"),
                    headers={"Cache-Control": "public, max-age=86400"})


# ---------------- Public invoice payment (crypto + custom link) ----------------

class CryptoClaimRequest(BaseModel):
    network: str
    tx_hash: str
    payer_email: EmailStr
    note: str = ""


async def _build_wallets() -> list:
    settings = await db.payment_settings.find_one({"key": "main"}) or {}
    WALLET_DEFS = [
        ("usdt_trc20_address", "usdt_trc20", "USDT · TRON (TRC-20)", "Near-zero fees — recommended"),
        ("usdt_pol_address", "usdt_pol", "USDT · Polygon (POL)", "Very low fees on the Polygon network"),
        ("usdt_bep20_address", "usdt_bep20", "USDT · BNB Chain (BEP-20)", "Low fees on BNB Smart Chain"),
        ("eth_address", "eth", "Ethereum (ETH / ERC-20)", "Also accepts USDT/USDC on Ethereum"),
        ("btc_address", "btc", "Bitcoin (BTC)", "Bitcoin network"),
        ("sol_address", "sol", "Solana (SOL)", "Fast confirmations, minimal fees"),
    ]
    wallets = []
    if settings.get("crypto_enabled"):
        for field, wid, label, note in WALLET_DEFS:
            if settings.get(field):
                wallets.append({"id": wid, "label": label, "note": note, "address": settings[field]})
    return wallets


async def _find_payable(token: str):
    """Return (doc, kind) where kind is 'invoice' or 'link', or (None, None)."""
    invoice = await db.invoices.find_one({"payment_token": token})
    if invoice:
        return invoice, "invoice"
    link = await db.payment_links.find_one({"token": token})
    if link:
        return link, "link"
    return None, None


@router.get("/pay/{token}")
async def get_public_payment_page(token: str):
    doc, kind = await _find_payable(token)
    if not doc:
        raise HTTPException(status_code=404, detail="Payment page not found")
    # Catch a payment whose webhook never landed, so a returning payer sees
    # "already paid" instead of being invited to pay twice.
    if await _settle_if_paid_upstream(doc, kind):
        doc, kind = await _find_payable(token)
    company = await db.company_settings.find_one({"key": "main"})
    agency_name = (company or {}).get("company_name") or "Obrinex"
    wallets = await _build_wallets()

    if kind == "invoice":
        client = await db.clients.find_one({"_id": to_object_id(doc["client_id"])}) if doc.get("client_id") else None
        return {
            "kind": "invoice",
            "invoice_number": doc["invoice_number"],
            "total": doc["total"],
            "currency": doc.get("currency", "INR"),
            "status": doc["status"],
            "due_date": doc.get("due_date"),
            "client_name": (client or {}).get("company_name"),
            "agency_name": agency_name,
            "payment_link": await _ensure_cashfree_link(doc, "invoice"),
            # Crypto is preferred for USD (no FX spread, no card fees) and
            # Cashfree for INR. The page opens on whichever this names.
            "preferred_method": _preferred_method(doc.get("currency"), wallets),
            "wallets": wallets,
            "payment_claimed": bool(doc.get("payment_claim")),
        }
    # Standalone payment link
    return {
        "kind": "link",
        "invoice_number": doc.get("title") or "Payment",
        "total": doc["amount"],
        "currency": doc.get("currency", "INR"),
        "status": "paid" if doc.get("status") == "paid" else "active",
        "due_date": None,
        "client_name": None,
        "agency_name": agency_name,
        "note": doc.get("note"),
        "payment_link": await _ensure_cashfree_link(doc, "link"),
        "preferred_method": _preferred_method(doc.get("currency"), wallets),
        "wallets": wallets,
        "payment_claimed": bool(doc.get("payment_claim")),
    }


def _preferred_method(currency: Optional[str], wallets: list) -> str:
    """Which tab the payment page should open on.

    USD settles better in crypto — no FX spread and no international card fee —
    so it leads there when a wallet is configured. INR leads with Cashfree.
    """
    if (currency or "INR").upper() == "USD" and wallets:
        return "crypto"
    return "other"


async def _settle_if_paid_upstream(doc: dict, kind: str) -> bool:
    """Ask Cashfree whether this link is already paid, and settle it if so.

    A safety net for a webhook that never arrived — a dropped delivery would
    otherwise leave a genuinely paid invoice showing as unpaid forever.
    """
    link_id = doc.get("cashfree_link_id")
    if not link_id or doc.get("status") == "paid" or not cashfree.is_configured():
        return False
    try:
        remote = await cashfree.fetch_payment_link(link_id)
    except cashfree.CashfreeError:
        return False
    if not remote or (remote.get("link_status") or "").upper() != "PAID":
        return False
    await _mark_paid(kind, doc["_id"], doc.get("invoice_number") or doc.get("title") or "payment")
    return True


async def _mark_paid(kind: str, doc_id, label: str) -> None:
    """Settle a document and notify the team. Safe to call more than once."""
    coll = db.invoices if kind == "invoice" else db.payment_links
    now = datetime.now(timezone.utc).isoformat()
    result = await coll.update_one(
        {"_id": doc_id, "status": {"$ne": "paid"}},
        {"$set": {"status": "paid", "paid_at": now, "updated_at": now,
                  "payment_method": "cashfree"}},
    )
    if result.modified_count == 0:
        return  # already settled — do not notify twice

    admin_link = f"/invoices/{doc_id}" if kind == "invoice" else "/payment-links"
    admins = await db.users.find({"role": "admin"}).to_list(20)
    for a in admins:
        await db.notifications.insert_one({
            "user_id": str(a["_id"]), "type": "payment_received",
            "title": "Payment received via Cashfree",
            "message": f"{label} has been paid in full through Cashfree.",
            "link": admin_link, "read": False, "created_at": now,
        })


async def _ensure_cashfree_link(doc: dict, kind: str) -> Optional[str]:
    """Return a live Cashfree payment link for this invoice / payment link.

    Created on first view and cached on the document, so the payer never waits
    on anyone to send them a link. Returns None whenever Cashfree cannot serve
    this payment — unconfigured, non-INR, or the API is down — and the page
    falls back to crypto rather than failing.
    """
    if not cashfree.is_configured():
        return None

    currency = (doc.get("currency") or "INR").upper()
    if not cashfree.supports_currency(currency):
        return None

    coll = db.invoices if kind == "invoice" else db.payment_links
    amount = round(float(doc["total"] if kind == "invoice" else doc["amount"]), 2)
    label = doc["invoice_number"] if kind == "invoice" else (doc.get("title") or "Payment")

    # A cached link is only good while it still asks for the current amount.
    # Editing an invoice after a client has opened it would otherwise leave the
    # old link live, and they would pay the superseded total.
    existing = doc.get("cashfree_link_url")
    if existing and round(float(doc.get("cashfree_link_amount") or 0), 2) == amount             and (doc.get("cashfree_link_currency") or "INR") == currency:
        return existing

    # Cashfree link_ids are permanent, so a changed amount needs a fresh one.
    revision = int(doc.get("cashfree_link_rev") or 0) + (1 if existing else 0)
    frontend = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    backend = (os.environ.get("BACKEND_URL") or "").rstrip("/")

    customer_email = None
    if kind == "invoice" and doc.get("client_id"):
        portal_user = await db.users.find_one({"role": "client", "client_id": doc["client_id"]})
        if portal_user:
            customer_email = portal_user.get("email")
        else:
            contact = await db.contacts.find_one(
                {"client_id": doc["client_id"], "email": {"$ne": None}}
            )
            customer_email = (contact or {}).get("email")

    try:
        result = await cashfree.create_payment_link(
            # obx_<i|l>_<document id>_<revision>; the short kind keeps this
            # inside Cashfree's 45-character limit.
            link_id=f"obx_{'i' if kind == 'invoice' else 'l'}_{doc['_id']}_{revision}",
            amount=float(amount),
            currency=currency,
            purpose=f"Invoice {label}" if kind == "invoice" else label,
            customer_email=customer_email,
            return_url=f"{frontend}/pay/{doc['payment_token' if kind == 'invoice' else 'token']}"
            if frontend
            else None,
            notify_url=f"{backend}/api/public/cashfree/webhook" if backend else None,
        )
    except cashfree.CashfreeError as exc:
        logger.warning("Cashfree link unavailable for %s %s: %s", kind, doc["_id"], exc)
        return None

    url = result.get("link_url")
    if not url:
        return None

    await coll.update_one(
        {"_id": doc["_id"]},
        {"$set": {
            "cashfree_link_url": url,
            "cashfree_link_id": result.get("link_id"),
            "cashfree_link_amount": amount,
            "cashfree_link_currency": currency,
            "cashfree_link_rev": revision,
        }},
    )
    return url


@router.post("/cashfree/webhook")
async def cashfree_webhook(request: Request):
    """Mark an invoice / payment link paid when Cashfree confirms settlement.

    Unverified payloads are dropped: without a valid signature anyone who found
    this URL could mark invoices paid. Always answers 200 so Cashfree does not
    retry a payload we have deliberately ignored.
    """
    raw = await request.body()
    signature = request.headers.get("x-webhook-signature", "")
    timestamp = request.headers.get("x-webhook-timestamp", "")

    if not cashfree.verify_webhook(raw, signature, timestamp):
        logger.warning("Rejected Cashfree webhook with an invalid signature")
        return {"status": "ignored"}

    try:
        event = json.loads(raw.decode("utf-8"))
    except Exception:
        return {"status": "ignored"}

    data = event.get("data") or {}
    link = data.get("link") or {}
    link_id = link.get("link_id") or ""
    status = (link.get("link_status") or "").upper()

    if status != "PAID" or not link_id.startswith("obx_"):
        return {"status": "ignored"}

    # link_id encodes its target: obx_<i|l>_<document id>_<revision>
    parts = link_id.split("_")
    if len(parts) != 4:
        return {"status": "ignored"}
    _, kind_code, doc_id, _rev = parts
    if kind_code not in ("i", "l"):
        return {"status": "ignored"}
    kind = "invoice" if kind_code == "i" else "link"
    coll = db.invoices if kind == "invoice" else db.payment_links
    try:
        oid = to_object_id(doc_id)
    except Exception:
        return {"status": "ignored"}

    doc = await coll.find_one({"_id": oid})
    if not doc:
        return {"status": "ignored"}

    await _mark_paid(kind, oid, doc.get("invoice_number") or doc.get("title") or "payment")
    return {"status": "ok"}


@router.post("/pay/{token}/claim")
async def claim_crypto_payment(token: str, payload: CryptoClaimRequest):
    doc, kind = await _find_payable(token)
    if not doc:
        raise HTTPException(status_code=404, detail="Payment page not found")
    if doc.get("status") == "paid":
        raise HTTPException(status_code=400, detail="This is already paid")
    now = datetime.now(timezone.utc).isoformat()
    claim = {
        "network": payload.network, "tx_hash": payload.tx_hash.strip(),
        "payer_email": payload.payer_email, "note": payload.note,
        "claimed_at": now,
    }
    coll = db.invoices if kind == "invoice" else db.payment_links
    await coll.update_one({"_id": doc["_id"]}, {"$set": {"payment_claim": claim}})
    label = doc["invoice_number"] if kind == "invoice" else (doc.get("title") or "payment link")
    admin_link = f"/invoices/{doc['_id']}" if kind == "invoice" else "/payment-links"
    admins = await db.users.find({"role": "admin"}).to_list(20)
    for a in admins:
        await db.notifications.insert_one({
            "user_id": str(a["_id"]), "type": "payment_claimed",
            "title": "Crypto payment submitted",
            "message": f"{payload.payer_email} says they paid {label} via {payload.network}. Verify the transaction in your wallet, then mark it paid.",
            "link": admin_link, "read": False, "created_at": now,
        })
    return {"message": "Thanks! Your payment is being verified — you'll receive a confirmation shortly."}


# ---------------- Public project status ----------------

@router.get("/projects/{token}")
async def get_public_project_status(token: str):
    project = await db.projects.find_one({"share_token": token})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    pid = str(project["_id"])
    milestones = await db.milestones.find({"project_id": pid}).to_list(100)
    tasks = await db.tasks.find({"related_type": "project", "related_id": pid}).to_list(500)
    company = await db.company_settings.find_one({"key": "main"})
    client = await db.clients.find_one({"_id": to_object_id(project["client_id"])}) if project.get("client_id") else None

    done_tasks = len([t for t in tasks if t.get("status") == "done"])
    done_milestones = len([m for m in milestones if m.get("completed")])
    total_units = len(tasks) + len(milestones)
    done_units = done_tasks + done_milestones
    progress = round(done_units / total_units * 100) if total_units else 0

    return {
        "name": project.get("name"),
        "status": project.get("status"),
        "health": project.get("health"),
        "description": project.get("description"),
        "start_date": project.get("start_date"),
        "end_date": project.get("end_date"),
        "updated_at": project.get("updated_at"),
        "progress": progress,
        "agency_name": (company or {}).get("company_name") or "Obrinex",
        "client_name": (client or {}).get("company_name"),
        "milestones": [{"title": m.get("title"), "completed": bool(m.get("completed"))} for m in milestones],
        "tasks_summary": {
            "total": len(tasks), "done": done_tasks,
            "in_progress": len([t for t in tasks if t.get("status") == "in_progress"]),
        },
        "recent_completed": [t.get("title") for t in tasks if t.get("status") == "done"][-5:],
    }


# ---------------- Public agreements (e-sign) ----------------

@router.get("/agreements/{token}")
async def get_public_agreement(token: str):
    contract = await db.contracts.find_one({"share_token": token})
    if not contract:
        raise HTTPException(status_code=404, detail="Agreement not found")
    client = await db.clients.find_one({"_id": to_object_id(contract["client_id"])})
    company = await db.company_settings.find_one({"key": "main"})
    data = serialize_doc(contract)
    data["client_name"] = (client or {}).get("company_name") or "Client"
    data["agency_name"] = (company or {}).get("company_name") or "Obrinex"
    return data


@router.post("/agreements/{token}/sign")
async def sign_public_agreement(token: str, payload: ProposalSignRequest):
    contract = await db.contracts.find_one({"share_token": token})
    if not contract:
        raise HTTPException(status_code=404, detail="Agreement not found")
    if contract.get("status") == "signed":
        raise HTTPException(status_code=400, detail="Agreement already signed")
    now = datetime.now(timezone.utc).isoformat()
    await db.contracts.update_one({"_id": contract["_id"]}, {"$set": {
        "status": "signed", "signature_name": payload.signature_name,
        "signer_email": payload.signer_email, "signed_at": now,
    }})
    admins = await db.users.find({"role": "admin"}).to_list(20)
    for a in admins:
        await db.notifications.insert_one({
            "user_id": str(a["_id"]), "type": "contract_signed",
            "title": "Agreement signed",
            "message": f"{payload.signature_name} signed \"{contract['title']}\".",
            "link": "/contracts", "read": False, "created_at": now,
        })
    updated = await db.contracts.find_one({"_id": contract["_id"]})
    return serialize_doc(updated)


@router.get("/agreements/{token}/pdf")
async def public_agreement_pdf(token: str):
    contract = await db.contracts.find_one({"share_token": token})
    if not contract:
        raise HTTPException(status_code=404, detail="Agreement not found")
    from routers.documents import build_agreement_pdf
    return await build_agreement_pdf(contract)


@router.post("/proposals/{token}/sign")
async def sign_public_proposal(token: str, payload: ProposalSignRequest):
    proposal = await db.proposals.find_one({"share_token": token})
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal["status"] in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Proposal already finalized")
    now = datetime.now(timezone.utc).isoformat()
    new_status = "accepted" if payload.accept else "rejected"
    await db.proposals.update_one({"_id": proposal["_id"]}, {"$set": {
        "status": new_status, "signature_name": payload.signature_name,
        "signer_email": payload.signer_email, "signed_at": now,
    }})
    updated = await db.proposals.find_one({"_id": proposal["_id"]})
    return serialize_doc(updated)

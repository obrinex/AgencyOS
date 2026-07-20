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
            # Sandbox links look exactly like live ones but move no money, so
            # the page must say so outright.
            "test_mode": cashfree.is_configured() and cashfree.environment() == "sandbox",
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
        "test_mode": cashfree.is_configured() and cashfree.environment() == "sandbox",
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

    # Replace the estimated FX rate with the one Cashfree actually applied.
    # The live feed is only ever an estimate; what the business received is
    # whatever Cashfree converted at, so that is what the books should show.
    doc = await coll.find_one({"_id": doc_id})
    currency = (doc or {}).get("currency", "INR")
    link_id = (doc or {}).get("cashfree_link_id")
    if currency and currency.upper() != "INR" and link_id:
        rate = await cashfree.fetch_settlement_rate(link_id)
        if rate:
            await coll.update_one(
                {"_id": doc_id},
                {"$set": {"conversion_rate": rate,
                          "conversion_rate_source": "cashfree-settlement"}},
            )
            logger.info("Applied Cashfree settlement rate %s to %s", rate, label)
        else:
            # Keep the estimate rather than record a number we cannot stand behind.
            logger.warning(
                "No Cashfree settlement rate for %s; keeping the estimated rate", label
            )

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


# --- AI SDR one-click unsubscribe ---------------------------------------------
#
# Unauthenticated by necessity: it is reached from a link in an email, and
# Gmail/Yahoo's one-click POST carries no session. The signed token is what
# stops it being used to suppress an arbitrary third party by editing the
# address in the URL.

@router.get("/sdr/unsubscribe")
async def unsubscribe_page(email: str, token: str):
    """Human-facing confirmation page. GET must not mutate anything.

    Mail clients and security scanners prefetch links; unsubscribing on GET
    would opt people out who never clicked. This renders a real HTML page -
    the person arriving here clicked a footer link in an email, and handing
    them raw JSON reads as a broken site at the worst possible moment.
    """
    from fastapi.responses import HTMLResponse
    from html import escape

    from sdr.repositories import suppression as sdr_suppression

    if not sdr_suppression.verify_unsubscribe_token(email, token):
        raise HTTPException(status_code=400, detail="This unsubscribe link is not valid.")

    existing = await sdr_suppression.is_suppressed(email=email)
    safe_email = escape(email, quote=True)
    safe_token = escape(token, quote=True)

    if existing:
        inner = (
            "<h1>You're already unsubscribed</h1>"
            f"<p><strong>{safe_email}</strong> will not be contacted again, "
            "on any channel, permanently.</p>"
        )
    else:
        inner = (
            "<h1>Unsubscribe</h1>"
            f"<p>Stop all email to <strong>{safe_email}</strong>? "
            "This takes effect immediately and is permanent.</p>"
            f'<form method="post" action="/api/public/sdr/unsubscribe'
            f'?email={safe_email}&amp;token={safe_token}">'
            '<button type="submit">Yes, unsubscribe me</button></form>'
        )

    page = (
        "<title>Unsubscribe</title>"
        '<div style="min-height:100vh;display:flex;align-items:center;'
        'justify-content:center;background:#131315;color:#F4F4F5;'
        "font-family:Arial,Helvetica,sans-serif\">"
        '<div style="max-width:420px;padding:32px;border:1px solid #2D2D30;'
        'border-radius:12px;background:#18181A;text-align:center">'
        + inner.replace(
            "<button ",
            '<button style="margin-top:12px;padding:10px 22px;border:0;'
            'border-radius:8px;background:#EF4444;color:#fff;font-size:15px;'
            'cursor:pointer" ',
        )
        + '<p style="color:#85858C;font-size:12px;margin-top:18px">'
        "If you did not expect this page, you can simply close it - "
        "nothing happens without the button.</p></div></div>"
    )
    return HTMLResponse(page)


@router.post("/sdr/unsubscribe")
async def unsubscribe(request: Request, email: str, token: str):
    """Honour an opt-out immediately, across every channel and campaign.

    Idempotent: the unique index makes a repeat a no-op rather than a 500 on
    a public endpoint that mail providers may retry.
    """
    from sdr.repositories import suppression as sdr_suppression

    if not sdr_suppression.verify_unsubscribe_token(email, token):
        raise HTTPException(status_code=400, detail="This unsubscribe link is not valid.")

    await sdr_suppression.suppress(
        value=email, value_type="email", reason="unsubscribe", source="one_click",
    )
    # The consent trail is what DPDP and GDPR actually require on request:
    # when and how someone opted out, not merely that they are on a list now.
    await sdr_suppression.record_consent(
        action="opt_out", value=email, channel="email", legal_basis="withdrawal",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        evidence={"method": "one_click_list_unsubscribe"},
    )

    # Stop any queued outreach to this address in the same breath. Suppression
    # already blocks the send, but leaving the jobs queued means they churn
    # through retries being refused.
    await db.sdr_jobs.update_many(
        {"status": "queued", "payload.recipient_email": email.strip().lower()},
        {"$set": {"status": "cancelled", "last_error": {
            "type": "Unsubscribed", "message": "Recipient unsubscribed",
        }}},
    )

    # Two callers land here: Gmail's one-click POST (machine - JSON is right)
    # and the confirmation form on the GET page (human - JSON reads as a
    # broken site). The Accept header tells them apart.
    if "text/html" in (request.headers.get("accept") or ""):
        from fastapi.responses import HTMLResponse
        from html import escape

        return HTMLResponse(
            "<title>Unsubscribed</title>"
            '<div style="min-height:100vh;display:flex;align-items:center;'
            'justify-content:center;background:#131315;color:#F4F4F5;'
            "font-family:Arial,Helvetica,sans-serif\">"
            '<div style="max-width:420px;padding:32px;border:1px solid #2D2D30;'
            'border-radius:12px;background:#18181A;text-align:center">'
            "<h1>Done</h1>"
            f"<p><strong>{escape(email, quote=True)}</strong> is unsubscribed, "
            "effective immediately and permanently. Sorry to have bothered you.</p>"
            "</div></div>"
        )
    return {"unsubscribed": True, "email": email}


@router.post("/sdr/webhooks/resend")
async def resend_webhook(request: Request):
    """Delivery, bounce and complaint events from Resend.

    Signature-verified (svix HMAC) with the same posture as the Cashfree
    webhook: a payload we cannot verify is a payload we do not act on. With
    no RESEND_WEBHOOK_SECRET configured this returns 503 rather than
    trusting the network - a forged "complained" event would suppress an
    arbitrary address permanently.
    """
    import base64
    import hashlib
    import hmac as hmac_mod
    import os
    import time as time_mod

    secret = os.environ.get("RESEND_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Webhook signing is not configured (RESEND_WEBHOOK_SECRET).",
        )

    body = await request.body()
    svix_id = request.headers.get("svix-id", "")
    svix_timestamp = request.headers.get("svix-timestamp", "")
    svix_signature = request.headers.get("svix-signature", "")
    if not (svix_id and svix_timestamp and svix_signature):
        raise HTTPException(status_code=401, detail="Missing signature headers")

    # Freshness: a replayed webhook older than 5 minutes is refused.
    try:
        age = abs(time_mod.time() - int(svix_timestamp))
    except ValueError:
        raise HTTPException(status_code=401, detail="Bad timestamp")
    if age > 300:
        raise HTTPException(status_code=401, detail="Stale webhook")

    key = base64.b64decode(secret.split("_", 1)[-1])
    signed = f"{svix_id}.{svix_timestamp}.".encode() + body
    expected = base64.b64encode(
        hmac_mod.new(key, signed, hashlib.sha256).digest()
    ).decode()
    candidates = [
        part.split(",", 1)[-1] for part in svix_signature.split(" ") if part
    ]
    if not any(hmac_mod.compare_digest(expected, candidate) for candidate in candidates):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)
    event_type = payload.get("type", "")
    data = payload.get("data") or {}
    provider_id = data.get("email_id") or data.get("id")

    from sdr.repositories import campaigns as sdr_campaigns
    from sdr.repositories import identities as sdr_identities
    from sdr.repositories import suppression as sdr_suppression

    message = await sdr_campaigns.find_by_provider_id(provider_id)
    if not message:
        # Not ours (an invoice email, or a message we never recorded).
        # Acknowledged so the provider stops retrying.
        return {"received": True, "matched": False}

    to_email = message.get("to_email")
    identity = message.get("identity")

    if event_type == "email.delivered":
        # Statuses only move forward: a late "delivered" after a bounce
        # or complaint must not resurrect the message.
        if message["status"] == "sent":
            await sdr_campaigns.update_message(message["id"], {"status": "delivered"})
            await sdr_campaigns.bump_stat(message["campaign_id"], "delivered")

    elif event_type == "email.bounced":
        await sdr_campaigns.update_message(message["id"], {"status": "bounced"})
        await sdr_campaigns.bump_stat(message["campaign_id"], "bounced")
        await sdr_suppression.suppress(
            value=to_email, reason="bounce", source="resend_webhook",
        )
        if identity:
            await sdr_identities.record_outcome(identity, bounced=1)
        if message.get("enrollment_id"):
            await sdr_campaigns.stop_enrollment(message["enrollment_id"], "bounced")

    elif event_type == "email.complained":
        await sdr_campaigns.update_message(message["id"], {"status": "complained"})
        await sdr_suppression.suppress(
            value=to_email, reason="complaint", source="resend_webhook",
        )
        await sdr_suppression.record_consent(
            action="opt_out", value=to_email, channel="email",
            legal_basis="complaint", evidence={"source": "resend_webhook"},
        )
        if identity:
            await sdr_identities.record_outcome(identity, complained=1)
        if message.get("enrollment_id"):
            await sdr_campaigns.stop_enrollment(message["enrollment_id"], "unsubscribed")

    return {"received": True, "matched": True, "event": event_type}


@router.post("/sdr/webhooks/inbound")
async def inbound_webhook(request: Request):
    """Replies, delivered by the Cloudflare Email Routing Worker.

    Same posture as the Resend webhook above, and for a sharper reason: a
    forged inbound reply stops a live sequence, marks a lead as answered, and
    can suppress an arbitrary address permanently. So no secret means 503,
    and a bad signature means 401 - never a best-effort parse.

    Beyond that it always returns 200. The Worker cannot do anything useful
    with a 500, and a retry storm on a reply we already stored helps nobody;
    `ingest_key` makes the duplicate delivery a no-op anyway.
    """
    from sdr.providers import inbound_cloudflare
    from sdr.services import inbound as inbound_service

    if not inbound_cloudflare.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Inbound webhook signing is not configured "
                   "(SDR_INBOUND_WEBHOOK_SECRET).",
        )

    body = await request.body()
    ok, reason = inbound_cloudflare.verify(
        body=body,
        timestamp=request.headers.get("x-sdr-timestamp", ""),
        signature=request.headers.get("x-sdr-signature", ""),
    )
    if not ok:
        raise HTTPException(status_code=401, detail=f"Rejected: {reason}")

    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Body is not valid JSON")

    normalized = inbound_cloudflare.normalize(payload)
    if not normalized.get("ingest_key"):
        # Without a stable key a provider retry would be processed twice.
        raise HTTPException(
            status_code=400,
            detail="Inbound message has neither a Message-ID header nor an id.",
        )
    if not normalized.get("from_email"):
        raise HTTPException(status_code=400, detail="Inbound message has no sender")

    result = await inbound_service.ingest(normalized)
    return {"received": True, **result}

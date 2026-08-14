"""AI-drafted emails: tell the AI what to say, review/edit the draft, then send via Resend."""
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field

from database import db, serialize_list
from auth_utils import require_staff, require_module
require_emails = require_module("emails")
from email_service import send_custom_email, resolve_booking_url

router = APIRouter(prefix="/api/emails", tags=["emails"])


class DraftRequest(BaseModel):
    instruction: str
    recipient_name: Optional[str] = None
    recipient_context: Optional[str] = None  # e.g. "client since March, project X in progress"
    tone: Optional[str] = "professional"


class SendRequest(BaseModel):
    to: EmailStr
    subject: str
    body: str
    recipient_name: Optional[str] = None
    # Conditional CTA buttons: each renders only when its link is provided /
    # requested, so no email carries a dead button.
    demo_url: Optional[str] = Field(default=None, pattern=r"^https://\S+$",
                                    max_length=500)
    include_booking_button: bool = False
    booking_url: Optional[str] = Field(default=None, pattern=r"^https://\S+$",
                                       max_length=500)


@router.post("/draft")
async def draft_email(payload: DraftRequest, user: dict = Depends(require_emails)):
    from routers.ai import _select_provider, response_text
    client, model, _ = _select_provider()

    prompt = (
        f"Draft a {payload.tone or 'professional'} business email for Obrinex, an AI automation agency.\n"
        f"What the owner wants to say: {payload.instruction}\n"
    )
    if payload.recipient_name:
        prompt += f"Recipient: {payload.recipient_name}\n"
    if payload.recipient_context:
        prompt += f"Context about the recipient: {payload.recipient_context}\n"
    prompt += (
        "\nRespond in EXACTLY this format (no extra commentary, no markdown):\n"
        "SUBJECT: <one clear subject line>\n"
        "---\n"
        "<the email body as plain text, paragraphs separated by blank lines, no subject inside, signed off as the Obrinex team>"
    )

    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You write clear, warm, effective business emails. Follow the requested output format exactly."},
            {"role": "user", "content": prompt},
        ],
    )
    raw = response_text(resp)
    if raw.startswith("```"):
        raw = raw.strip("`").strip()

    subject, body = "Message from Obrinex", raw
    if "---" in raw:
        head, _, rest = raw.partition("---")
        if head.strip().upper().startswith("SUBJECT:"):
            subject = head.strip()[8:].strip()
            body = rest.strip()
    elif raw.upper().startswith("SUBJECT:"):
        first, _, rest = raw.partition("\n")
        subject = first[8:].strip()
        body = rest.strip()
    return {"subject": subject, "body": body}


@router.post("/send")
async def send_drafted_email(payload: SendRequest, user: dict = Depends(require_emails)):
    if not payload.subject.strip() or not payload.body.strip():
        raise HTTPException(status_code=400, detail="Subject and body are required")
    booking_url = (await resolve_booking_url(payload.booking_url)
                   if (payload.include_booking_button or payload.booking_url) else None)
    result = await send_custom_email(payload.to, payload.subject.strip(), payload.body.strip(),
                                     demo_url=payload.demo_url, booking_url=booking_url)
    now = datetime.now(timezone.utc).isoformat()
    await db.sent_emails.insert_one({
        "to": payload.to,
        "recipient_name": payload.recipient_name,
        "subject": payload.subject.strip(),
        "body": payload.body.strip(),
        "demo_url": payload.demo_url,
        "booking_url": booking_url,
        "sent_by": user["id"],
        "sent_by_name": user.get("name"),
        "provider_id": (result or {}).get("id") if isinstance(result, dict) else None,
        "created_at": now,
    })
    return {"message": f"Email sent to {payload.to}"}


@router.get("")
async def list_sent_emails(user: dict = Depends(require_emails)):
    emails = await db.sent_emails.find({}).sort("created_at", -1).to_list(100)
    return serialize_list(emails)


@router.get("/recipients")
async def list_recipients(user: dict = Depends(require_emails)):
    """All known email addresses across clients (portal users), contacts, and leads."""
    out, seen = [], set()
    portal_users = await db.users.find({"role": "client"}).to_list(500)
    for u in portal_users:
        if u.get("email") and u["email"] not in seen:
            seen.add(u["email"])
            out.append({"email": u["email"], "name": u.get("name"), "kind": "client"})
    contacts = await db.contacts.find({"email": {"$nin": [None, ""]}}).to_list(500)
    for c in contacts:
        if c.get("email") and c["email"] not in seen:
            seen.add(c["email"])
            out.append({"email": c["email"], "name": c.get("name"), "kind": "contact"})
    # Soft-deleted leads are excluded. This list is the recipient picker, so a
    # lead deleted in the SDR UI was still an address staff could email.
    leads = await db.leads.find({"email": {"$nin": [None, ""]},
                                 "deleted_at": None}).to_list(500)
    for l in leads:
        if l.get("email") and l["email"] not in seen:
            seen.add(l["email"])
            out.append({"email": l["email"], "name": l.get("company"), "kind": "lead"})
    return out

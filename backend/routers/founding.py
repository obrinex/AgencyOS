"""The Founding Circle: applications, review, and the members' own portal.

Three audiences, three access levels, one router:

- **The public** applies from obrinex.space. Unauthenticated, so nothing here
  trusts its input and everything is throttled.
- **Staff** review, score and decide. Approving mints a portal invite.
- **Members** get a portal that is deliberately not the client portal: their
  own role, their own routes, their own chat.

## Membership is never announced

There is no public endpoint that lists members, and the public form reports
only whether the round is open - never who is in, never how many seats are
gone. Seat counts are visible to staff and to members inside the circle, and
nowhere else. That is the whole of what "anonymous" means here: the ten people
are not published.

## Why a separate role rather than a flag on `client`

A founding member is not a client and must not inherit the client portal's
routes. `require_client` is an exact role match, so a `founding` user cannot
reach `/api/portal/*` even by guessing URLs, and vice versa. A boolean on the
client role would have made every existing `require_client` endpoint a
question rather than an answer.
"""

import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

import founding
from auth_utils import (get_current_user, hash_password, log_audit,
                        require_admin, require_roles, require_staff)
from database import db, serialize_doc, serialize_list, to_object_id
from rate_limit import check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["founding"])

APPLICATIONS = "founding_applications"
ROUNDS = "founding_rounds"
CHAT = "founding_chat_messages"
ASSISTANT = "founding_assistant_messages"

#: The members' own role. Distinct from `client` on purpose - see module docs.
FOUNDING_ROLE = "founding"
require_founding = require_roles(FOUNDING_ROLE)

#: Unauthenticated and it writes a document plus sends an email, so it is
#: throttled twice: per IP, and per address so rotating IPs buys nothing.
APPLY_RATE_LIMIT = 3
APPLY_EMAIL_RATE_LIMIT = 2
APPLY_RATE_WINDOW_SECONDS = 3600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Rounds -------------------------------------------------------------------

async def _current_round(create: bool = False) -> dict:
    """The round applications land in right now, opening one if needed.

    Rounds are created lazily rather than by a scheduled job. A cron that fails
    silently on the 1st would mean an application form that rejects everyone
    for a month; deriving the round from the calendar means the worst a missed
    job can do is nothing at all.
    """
    key = founding.round_key()
    existing = await db[ROUNDS].find_one({"key": key})
    if existing:
        return existing
    if not create:
        return {"key": key, "status": founding.ROUND_OPEN, "received": 0,
                "closed_reason": None}
    doc = {"key": key, "status": founding.ROUND_OPEN, "received": 0,
           "closed_reason": None, "opened_at": _now(), "closed_at": None}
    await db[ROUNDS].update_one({"key": key}, {"$setOnInsert": doc}, upsert=True)
    return await db[ROUNDS].find_one({"key": key})


async def _approved_count() -> int:
    return await db[APPLICATIONS].count_documents({"status": founding.APPROVED})


async def _close_round(key: str, reason: str) -> None:
    await db[ROUNDS].update_one(
        {"key": key},
        {"$set": {"status": founding.ROUND_CLOSED, "closed_reason": reason,
                  "closed_at": _now()}},
    )


# --- Public: the application form ---------------------------------------------

class ApplicationSubmit(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    answers: dict


@router.get("/public/founding/form")
async def public_form():
    """Everything the website needs to render the form.

    Reports whether the round is open and nothing about who is in the circle -
    not names, not a seat count. A public "3 seats left" is a countdown that
    tells strangers how the private group is doing.
    """
    current = await _current_round()
    return {
        "open": current.get("status", founding.ROUND_OPEN) == founding.ROUND_OPEN,
        "round": current["key"],
        "questions": founding.QUESTIONS,
        "band_labels": founding.BAND_LABELS,
        "closes": "when the round fills or at the end of the month",
        "decision_by": "the 30th",
    }


@router.post("/public/founding/apply")
async def public_apply(payload: ApplicationSubmit, request: Request):
    """Accept an application. Unauthenticated, so nothing is trusted.

    Status, score and round are all set here rather than taken from the body;
    an applicant supplying their own `status` is exactly the sort of thing an
    open endpoint invites.
    """
    too_many = "Thanks — we already have your application for this round."
    await check_rate_limit(request, scope="founding_apply",
                           limit=APPLY_RATE_LIMIT,
                           window_seconds=APPLY_RATE_WINDOW_SECONDS,
                           detail=too_many)
    await check_rate_limit(request, scope="founding_apply_email",
                           key=payload.email.lower(),
                           limit=APPLY_EMAIL_RATE_LIMIT,
                           window_seconds=APPLY_RATE_WINDOW_SECONDS,
                           detail=too_many)

    current = await _current_round(create=True)
    if current["status"] == founding.ROUND_CLOSED:
        raise HTTPException(
            status_code=409,
            detail="Applications for this round are closed. The next round opens on the 1st.",
        )

    problems = founding.validate_answers(payload.answers)
    if problems:
        raise HTTPException(status_code=400, detail=" ".join(problems))

    email = payload.email.lower()
    duplicate = await db[APPLICATIONS].find_one({"email": email, "round": current["key"]})
    if duplicate:
        # Same reply as a successful submission. Telling a stranger "you already
        # applied" confirms an address is in the system to anyone who guesses it.
        return {"message": "Application received."}

    answers = {k: v for k, v in (payload.answers or {}).items()
               if k in {q["key"] for q in founding.QUESTIONS}}
    score = founding.total_score(answers, {})
    doc = {
        "round": current["key"],
        "name": payload.name.strip(),
        "email": email,
        "answers": answers,
        "status": founding.PENDING,
        "ratings": {},
        "score": score,
        "created_at": _now(),
        "decided_at": None, "decided_by": None, "decision_note": None,
        "invite_token": None, "invite_used_at": None,
    }
    await db[APPLICATIONS].insert_one(doc)

    received = await db[APPLICATIONS].count_documents({"round": current["key"]})
    await db[ROUNDS].update_one({"key": current["key"]}, {"$set": {"received": received}})
    reason = founding.should_close(received, current["status"],
                                   founding.round_key(), current["key"])
    if reason:
        await _close_round(current["key"], reason)

    try:
        from email_service import send_founding_received_email
        await send_founding_received_email(email, doc["name"])
    except Exception:
        # An acknowledgement that fails to send must not lose the application.
        logger.exception("Could not send founding acknowledgement to %s", email)

    return {"message": "Application received."}


# --- Staff: review and decide -------------------------------------------------

@router.get("/founding/overview")
async def overview(user: dict = Depends(require_staff)):
    current = await _current_round()
    approved = await _approved_count()
    return {
        "round": current["key"],
        "round_status": current.get("status", founding.ROUND_OPEN),
        "closed_reason": current.get("closed_reason"),
        "received": await db[APPLICATIONS].count_documents({"round": current["key"]}),
        "application_cap": founding.ROUND_APPLICATION_CAP,
        "pending": await db[APPLICATIONS].count_documents({"status": founding.PENDING}),
        "approved": approved,
        "rejected": await db[APPLICATIONS].count_documents({"status": founding.REJECTED}),
        "seats_total": founding.TOTAL_SEATS,
        "seats_remaining": founding.seats_remaining(approved),
        "score_max": founding.TOTAL_MAX,
    }


@router.get("/founding/applications")
async def list_applications(status: Optional[str] = None, round: Optional[str] = None,
                            user: dict = Depends(require_staff)):
    """Applications, highest score first, so the review queue orders itself."""
    query = {}
    if status:
        if status not in founding.STATUSES:
            raise HTTPException(status_code=400, detail=f"Unknown status '{status}'.")
        query["status"] = status
    if round:
        query["round"] = round
    rows = await db[APPLICATIONS].find(query).to_list(500)
    rows.sort(key=lambda r: (r.get("score") or {}).get("total", 0), reverse=True)
    return serialize_list(rows)


@router.get("/founding/applications/{application_id}")
async def get_application(application_id: str, user: dict = Depends(require_staff)):
    doc = await db[APPLICATIONS].find_one({"_id": to_object_id(application_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
    return serialize_doc(doc)


class RatingsUpdate(BaseModel):
    clarity: int = Field(default=0, ge=0, le=10)
    self_awareness: int = Field(default=0, ge=0, le=10)
    work_quality: int = Field(default=0, ge=0, le=10)
    fit: int = Field(default=0, ge=0, le=5)


@router.patch("/founding/applications/{application_id}/ratings")
async def set_ratings(application_id: str, payload: RatingsUpdate,
                      user: dict = Depends(require_staff)):
    """Record the 35 qualitative points and recompute the total."""
    doc = await db[APPLICATIONS].find_one({"_id": to_object_id(application_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
    if doc["status"] != founding.PENDING:
        raise HTTPException(status_code=409,
                            detail="This application has already been decided.")

    ratings = payload.model_dump()
    score = founding.total_score(doc.get("answers"), ratings)
    await db[APPLICATIONS].update_one(
        {"_id": doc["_id"]},
        {"$set": {"ratings": ratings, "score": score, "rated_by": user["id"],
                  "rated_at": _now()}},
    )
    return {"ratings": ratings, "score": score}


class Decision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Optional[str] = Field(default=None, max_length=1000)


class AccessChange(BaseModel):
    active: bool


@router.post("/founding/applications/{application_id}/decide")
async def decide(application_id: str, payload: Decision, request: Request,
                 user: dict = Depends(require_admin)):
    """Approve or reject, and tell the applicant either way.

    Admin-only: a seat in a ten-person circle is not a team_member decision.

    The seat check happens here rather than in the UI because two people
    reviewing at once would otherwise both see nine seats gone and both
    approve. It re-counts immediately before writing.
    """
    doc = await db[APPLICATIONS].find_one({"_id": to_object_id(application_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
    if doc["status"] != founding.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Already {doc['status']} on {str(doc.get('decided_at'))[:10]}.")

    approving = payload.decision == founding.APPROVED
    invite_token = None

    if approving:
        if not founding.can_approve(await _approved_count()):
            raise HTTPException(
                status_code=409,
                detail=f"All {founding.TOTAL_SEATS} seats are taken. Remove a member first.")
        invite_token = secrets.token_urlsafe(32)

    await db[APPLICATIONS].update_one(
        {"_id": doc["_id"]},
        {"$set": {"status": payload.decision, "decided_at": _now(),
                  "decided_by": user["id"], "decision_note": payload.note,
                  "invite_token": invite_token}},
    )

    # The decision is committed before the email. A send failure must not leave
    # an applicant approved in the UI and un-emailed, or worse, decided twice.
    email_sent = True
    try:
        from email_service import (send_founding_approved_email,
                                   send_founding_rejected_email)
        if approving:
            await send_founding_approved_email(doc["email"], doc["name"], invite_token)
        else:
            await send_founding_rejected_email(doc["email"], doc["name"])
    except Exception:
        email_sent = False
        logger.exception("Founding decision email failed for %s", doc["email"])

    await log_audit(user["id"], f"founding_{payload.decision}", "founding_application",
                    application_id, request)
    return {"status": payload.decision, "email_sent": email_sent,
            "seats_remaining": founding.seats_remaining(await _approved_count())}


@router.get("/founding/members")
async def list_members(user: dict = Depends(require_staff)):
    """The circle. Staff-only - there is no public equivalent of this.

    `access` is the state of their portal login, which is a different question
    from whether they hold a seat:

    - `pending`  - approved, invite not yet accepted, no login exists
    - `active`   - they can sign in
    - `revoked`  - the login is disabled, the seat is still theirs
    """
    rows = await db[APPLICATIONS].find({"status": founding.APPROVED}).to_list(100)
    out = []
    for r in rows:
        portal_user = None
        if r.get("portal_user_id"):
            portal_user = await db.users.find_one({"_id": to_object_id(r["portal_user_id"])})
        if not portal_user:
            access = "pending"
        else:
            access = "active" if portal_user.get("is_active", True) else "revoked"
        out.append({
            "id": str(r["_id"]), "name": r.get("name"), "email": r.get("email"),
            "company": (r.get("answers") or {}).get("company"),
            "joined_at": r.get("decided_at"),
            "access": access,
            "score": (r.get("score") or {}).get("total"),
        })
    out.sort(key=lambda m: m.get("joined_at") or "")
    return out


@router.post("/founding/members/{application_id}/access")
async def set_member_access(application_id: str, payload: "AccessChange",
                            request: Request, user: dict = Depends(require_admin)):
    """Turn a member's portal login on or off without touching their seat.

    Revoking is `is_active = False` on the user row rather than a deletion:
    `get_current_user` already refuses an inactive user, so the next request
    fails and existing sessions die with it. Deleting the row instead would
    take their chat authorship with it and make restoring them a re-invite.

    The seat is untouched either way. Someone who has lost access is still one
    of the ten - use the remove endpoint if the intent is to free the seat.
    """
    doc = await db[APPLICATIONS].find_one({"_id": to_object_id(application_id),
                                           "status": founding.APPROVED})
    if not doc:
        raise HTTPException(status_code=404, detail="Member not found")
    if not doc.get("portal_user_id"):
        raise HTTPException(
            status_code=409,
            detail="They haven't accepted their invite yet, so there is no login to change.")

    await db.users.update_one({"_id": to_object_id(doc["portal_user_id"])},
                              {"$set": {"is_active": payload.active}})
    await log_audit(user["id"],
                    f"founding_access_{'granted' if payload.active else 'revoked'}",
                    "founding_member", application_id, request)
    return {"access": "active" if payload.active else "revoked"}


@router.post("/founding/members/{application_id}/remove")
async def remove_member(application_id: str, request: Request,
                        user: dict = Depends(require_admin)):
    """Take back a seat.

    Distinct from revoking access, and the heavier of the two: this frees one
    of the ten for someone else. The application drops back to rejected so the
    seat count - which counts approved applications - is correct, and the login
    goes with it.
    """
    doc = await db[APPLICATIONS].find_one({"_id": to_object_id(application_id),
                                           "status": founding.APPROVED})
    if not doc:
        raise HTTPException(status_code=404, detail="Member not found")

    if doc.get("portal_user_id"):
        await db.users.delete_one({"_id": to_object_id(doc["portal_user_id"])})
    await db[APPLICATIONS].update_one(
        {"_id": doc["_id"]},
        {"$set": {"status": founding.REJECTED, "portal_user_id": None,
                  "invite_token": None,
                  "removed_at": _now(), "removed_by": user["id"]}},
    )
    await log_audit(user["id"], "founding_member_removed", "founding_member",
                    application_id, request)
    return {"removed": True,
            "seats_remaining": founding.seats_remaining(await _approved_count())}


@router.post("/founding/members/{application_id}/reinvite")
async def reinvite_member(application_id: str, user: dict = Depends(require_admin)):
    """Mint a fresh invite for someone whose link expired in an inbox.

    Replaces the old token rather than adding one, so a forwarded original
    stops working the moment a replacement is issued.
    """
    doc = await db[APPLICATIONS].find_one({"_id": to_object_id(application_id),
                                           "status": founding.APPROVED})
    if not doc:
        raise HTTPException(status_code=404, detail="Member not found")
    if doc.get("portal_user_id"):
        raise HTTPException(status_code=409,
                            detail="They already have an account. Use access instead.")

    token = secrets.token_urlsafe(32)
    await db[APPLICATIONS].update_one({"_id": doc["_id"]},
                                      {"$set": {"invite_token": token,
                                                "invite_used_at": None}})
    sent = True
    try:
        from email_service import send_founding_approved_email
        await send_founding_approved_email(doc["email"], doc["name"], token)
    except Exception:
        sent = False
        logger.exception("Founding re-invite email failed for %s", doc["email"])
    return {"email_sent": sent}


# --- Public: accepting the invite ---------------------------------------------

class AcceptInvite(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=10, max_length=128)


@router.post("/public/founding/accept")
async def accept_invite(payload: AcceptInvite, request: Request):
    """Turn an approval into a portal login, with a password they choose.

    Single-use: the token is cleared as it is consumed, so a forwarded email
    cannot be replayed into a second account.
    """
    await check_rate_limit(request, scope="founding_accept", limit=10,
                           window_seconds=3600,
                           detail="Too many attempts. Try again shortly.")

    doc = await db[APPLICATIONS].find_one({"invite_token": payload.token,
                                           "status": founding.APPROVED})
    if not doc or doc.get("invite_used_at"):
        raise HTTPException(status_code=400,
                            detail="This invite link is not valid or has already been used.")

    if await db.users.find_one({"email": doc["email"]}):
        raise HTTPException(
            status_code=409,
            detail="An account already exists for this address. Use password reset instead.")

    now = _now()
    result = await db.users.insert_one({
        "email": doc["email"],
        "password_hash": hash_password(payload.password),
        "name": doc["name"],
        "role": FOUNDING_ROLE,
        "founding_application_id": str(doc["_id"]),
        "is_active": True,
        "two_fa_enabled": False,
        "created_at": now,
    })
    await db[APPLICATIONS].update_one(
        {"_id": doc["_id"]},
        {"$set": {"invite_used_at": now, "invite_token": None,
                  "portal_user_id": str(result.inserted_id)}},
    )
    return {"message": "Your account is ready. You can sign in now."}


# --- Members: the circle's own portal -----------------------------------------

async def _member(user: dict) -> dict:
    doc = await db[APPLICATIONS].find_one(
        {"_id": to_object_id(user["founding_application_id"])}
    ) if user.get("founding_application_id") else None
    if not doc:
        raise HTTPException(status_code=403, detail="No Founding Circle membership found.")
    return doc


@router.get("/founding/me")
async def my_membership(user: dict = Depends(require_founding)):
    doc = await _member(user)
    return {
        "name": doc.get("name"),
        "company": (doc.get("answers") or {}).get("company"),
        "joined_at": doc.get("decided_at"),
        "seats_total": founding.TOTAL_SEATS,
        "members": await _approved_count(),
    }


class ChatPost(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


#: The community room is open to members and to staff. Staff are in it because
#: the circle is the agency's own room - a host who cannot speak in their own
#: community is not hosting it. Everyone else, including clients, is refused by
#: exact role match.
require_circle = require_roles(FOUNDING_ROLE, "admin", "team_member")


async def _author(user: dict) -> dict:
    """Who a chat message is from.

    Staff post as the house rather than under a personal name: a member should
    be able to tell at a glance whether they are hearing from another founder
    or from Obrinex, and a first name in a ten-person room does not carry that.
    """
    if user["role"] in ("admin", "team_member"):
        return {"author_name": "Obrinex", "author_company": None, "is_host": True}
    doc = await _member(user)
    return {"author_name": doc.get("name"),
            "author_company": (doc.get("answers") or {}).get("company"),
            "is_host": False}


@router.get("/founding/chat")
async def read_chat(limit: int = 100, user: dict = Depends(require_circle)):
    """One shared room for the circle. Members see each other here - a community
    where nobody knows who they are talking to is not a community. What stays
    private is that the membership is never published outside this room."""
    await _author(user)
    rows = await db[CHAT].find({}).sort("created_at", -1).to_list(min(limit, 300))
    return serialize_list(list(reversed(rows)))


@router.post("/founding/chat")
async def post_chat(payload: ChatPost, user: dict = Depends(require_circle)):
    message = {"author_id": user["id"], **await _author(user),
               "body": payload.body.strip(), "created_at": _now()}
    result = await db[CHAT].insert_one(message)
    return serialize_doc(await db[CHAT].find_one({"_id": result.inserted_id}))


@router.delete("/founding/chat/{message_id}")
async def delete_chat_message(message_id: str, user: dict = Depends(get_current_user)):
    """A member deletes their own message; an admin deletes any."""
    doc = await db[CHAT].find_one({"_id": to_object_id(message_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Message not found")
    if user["role"] != "admin" and doc.get("author_id") != user["id"]:
        raise HTTPException(status_code=403, detail="You can only delete your own messages.")
    await db[CHAT].delete_one({"_id": doc["_id"]})
    return {"message": "Deleted"}


class AssistantAsk(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


ASSISTANT_SYSTEM = """You are the Founding Circle assistant at Obrinex, an AI \
automation agency. You help one member with general questions: how the circle \
works, how to think about a business problem, drafting and reviewing their own \
writing, and finding their way around their portal.

Rules you do not break:
- You have no access to the agency's client data, invoices, or other members' \
information. If asked for any of it, say plainly that you cannot see it.
- You never reveal who else is in the Founding Circle. Membership is not public.
- If you do not know something, say so. Do not invent a feature, a price, a \
deadline or a policy.
- Be concise and practical.

Facts you may state: the circle has ten seats; applications open on the 1st of \
each month, close when the round fills or the month ends, and every applicant \
hears back by the 30th."""


@router.get("/founding/assistant")
async def assistant_history(user: dict = Depends(require_founding)):
    rows = await db[ASSISTANT].find({"member_id": user["id"]}) \
        .sort("created_at", 1).to_list(100)
    return serialize_list(rows)


@router.post("/founding/assistant")
async def assistant_ask(payload: AssistantAsk, user: dict = Depends(require_founding)):
    """The member's own assistant.

    Scoped to this member: the prompt carries their name and nothing about the
    agency's other data, and the history query is filtered by `member_id`, so
    one member's thread is not reachable from another's session.
    """
    doc = await _member(user)
    import llm_providers

    chain = llm_providers.chain()
    if not chain:
        raise HTTPException(status_code=503,
                            detail="The assistant is not configured yet.")
    _key, make_client, model = chain[0]

    history = await db[ASSISTANT].find({"member_id": user["id"]}) \
        .sort("created_at", -1).to_list(10)
    turns = [{"role": m["role"], "content": m["content"]}
             for m in reversed(history)]

    messages = (
        [{"role": "system",
          "content": f"{ASSISTANT_SYSTEM}\n\nYou are speaking with {doc.get('name')}."}]
        + turns
        + [{"role": "user", "content": payload.message}]
    )

    try:
        response = await make_client().chat.completions.create(
            model=model, messages=messages, stream=False, timeout=30)
        choices = getattr(response, "choices", None) or []
        reply = ((choices[0].message.content or "") if choices else "").strip()
    except Exception as exc:
        logger.warning("Founding assistant call failed: %s", exc)
        raise HTTPException(status_code=502,
                            detail="The assistant could not answer right now. Try again.")

    if not reply:
        # An empty completion is a filtered response, not an answer. Storing it
        # would leave a blank turn in the thread that reads as the assistant
        # having nothing to say.
        raise HTTPException(status_code=502,
                            detail="The assistant returned nothing. Try rephrasing.")

    now = _now()
    await db[ASSISTANT].insert_many([
        {"member_id": user["id"], "role": "user", "content": payload.message,
         "created_at": now},
        {"member_id": user["id"], "role": "assistant", "content": reply,
         "created_at": now},
    ])
    return {"reply": reply}


async def create_founding_indexes() -> None:
    """Called from `database.create_indexes()`. Idempotent."""
    try:
        await db[APPLICATIONS].create_index([("round", 1), ("email", 1)], unique=True)
        await db[APPLICATIONS].create_index("status")
        await db[APPLICATIONS].create_index("invite_token", sparse=True)
        await db[ROUNDS].create_index("key", unique=True)
        await db[CHAT].create_index("created_at")
        await db[ASSISTANT].create_index([("member_id", 1), ("created_at", 1)])
    except Exception as exc:
        logger.error("Could not create Founding Circle indexes: %s", exc)

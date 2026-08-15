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
from datetime import datetime, timedelta, timezone
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

#: The members' own role. Distinct from `client` on purpose - see module docs.
FOUNDING_ROLE = "founding"
require_founding = require_roles(FOUNDING_ROLE)

#: The community room, the directory and the projects page are open to members
#: and to staff. Staff are in because the circle is the agency's own room - a
#: host who cannot see their own community is not hosting it. Everyone else,
#: including clients, is refused by exact role match.
#:
#: Defined up here rather than beside the chat endpoints because `Depends()`
#: resolves when the module is imported: any route declared above this line
#: would fail at import with a NameError, not at request time.
require_circle = require_roles(FOUNDING_ROLE, "admin", "team_member")

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


async def _approved_in_round(round_key: str | None = None) -> int:
    """Approvals in one intake - what the ten seats are counted against.

    Seats reset each quarter, so the cap is per intake. `_total_members` is the
    lifetime figure and is reported separately; conflating the two would either
    cap the circle at ten forever or never cap an intake at all.
    """
    return await db[APPLICATIONS].count_documents(
        {"status": founding.APPROVED, "round": round_key or founding.round_key()})


async def _total_members() -> int:
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
    #: A member's invitation code, if they arrived through one. Carries a tag
    #: onto the application and nothing else — it buys no points and skips no
    #: questions. An invalid or spent code is ignored rather than rejected: the
    #: applicant did nothing wrong and losing their answers over a stale link
    #: would be absurd.
    referral: Optional[str] = Field(default=None, max_length=64)


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
        "closes": "when the intake fills or at the end of the quarter",
        "decision_by": "the end of the quarter",
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
            detail="This intake is closed. The next one opens at the start of the quarter.",
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

    referral = None
    if payload.referral:
        referral = await db[REFERRALS].find_one({"code": payload.referral, "used_at": None})

    doc = {
        "round": current["key"],
        "name": payload.name.strip(),
        "email": email,
        "answers": answers,
        "status": founding.PENDING,
        "ratings": {},
        "score": score,
        "referred_by": referral.get("referrer_name") if referral else None,
        "referred_by_id": referral.get("referrer_application_id") if referral else None,
        "referral_note": referral.get("note") if referral else None,
        "created_at": _now(),
        "decided_at": None, "decided_by": None, "decision_note": None,
        "invite_token": None, "invite_used_at": None,
    }
    inserted = await db[APPLICATIONS].insert_one(doc)

    if referral:
        # Marked used on submission, not on approval. The invitation did its
        # job the moment it produced an application; leaving it live would let
        # one link introduce a queue of people.
        await db[REFERRALS].update_one(
            {"_id": referral["_id"]},
            {"$set": {"used_at": _now(),
                      "used_by_application_id": str(inserted.inserted_id)}},
        )

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
    key = current["key"]
    approved_this_intake = await _approved_in_round(key)
    return {
        "round": key,
        "round_label": f"Q{key.split('-Q')[1]} {key.split('-')[0]}",
        "round_status": current.get("status", founding.ROUND_OPEN),
        "closed_reason": current.get("closed_reason"),
        "received": await db[APPLICATIONS].count_documents({"round": key}),
        "application_cap": founding.ROUND_APPLICATION_CAP,
        "pending": await db[APPLICATIONS].count_documents(
            {"status": founding.PENDING, "round": key}),
        "approved": approved_this_intake,
        "rejected": await db[APPLICATIONS].count_documents(
            {"status": founding.REJECTED, "round": key}),
        "seats_total": founding.SEATS_PER_INTAKE,
        "seats_remaining": founding.seats_remaining(approved_this_intake),
        "total_members": await _total_members(),
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
        if not founding.can_approve(await _approved_in_round(doc.get("round"))):
            raise HTTPException(
                status_code=409,
                detail=(f"All {founding.SEATS_PER_INTAKE} seats in this intake are "
                        f"taken. The next intake opens next quarter."))
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
            "seats_remaining": founding.seats_remaining(
                await _approved_in_round(doc.get("round")))}


@router.delete("/founding/applications/{application_id}")
async def delete_application(application_id: str, request: Request,
                             user: dict = Depends(require_admin)):
    """Erase an application for good.

    Admin-only and a genuine hard delete, not a hidden flag. Two things need it
    and both want the row actually gone: spam and test submissions, which
    otherwise sit in the count forever and skew every intake number; and an
    applicant asking to be erased, which a soft delete does not answer.

    The audit entry carries the email, so the trail outlives the document it
    describes - a log saying "admin deleted 6712a…" is not a record of anything
    once the row it points at no longer exists.

    ## Deleting a member takes their login with them

    An approved application may have minted a portal account. Removing the
    application and leaving the user behind would strand a `founding` login with
    no membership record: it authenticates, resolves to nothing, and every
    member endpoint 404s at someone who can still sign in. So the account goes
    too, exactly as `remove_member` does it.

    Deleting an approved application also frees its seat, because seats are
    counted from approved documents rather than stored. That is a real
    consequence and the UI says so before you confirm.

    ## The round's counter is recomputed, not decremented

    `rounds.received` decides when an intake closes on its cap. Subtracting one
    would drift the moment anything else touched the collection; recounting is
    the same query the submit path already runs and cannot drift.

    An intake closed *by its cap* reopens if the deletion puts it back under -
    which is the whole point of deleting spam from a full round. It stays shut
    if the quarter ended, because that is not a fault a deletion can repair.
    """
    try:
        oid = to_object_id(application_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Application not found")

    doc = await db[APPLICATIONS].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")

    if doc.get("portal_user_id"):
        await db.users.delete_one({"_id": to_object_id(doc["portal_user_id"])})

    await db[APPLICATIONS].delete_one({"_id": oid})

    round_key = doc.get("round")
    received = None
    reopened = False
    if round_key:
        received = await db[APPLICATIONS].count_documents({"round": round_key})
        update = {"received": received}
        current = await db[ROUNDS].find_one({"key": round_key})
        if (current
                and current.get("status") == founding.ROUND_CLOSED
                and current.get("closed_reason") == founding.CLOSED_BY_CAP
                and received < founding.ROUND_APPLICATION_CAP
                and round_key == founding.round_key()):
            update.update({"status": founding.ROUND_OPEN, "closed_reason": None,
                           "closed_at": None})
            reopened = True
        await db[ROUNDS].update_one({"key": round_key}, {"$set": update})

    # Logged with the identifying detail rather than only the id, because the id
    # now points at nothing.
    await log_audit(user["id"], "founding_application_deleted", "founding_application",
                    f"{application_id} ({doc.get('email')} · {doc.get('status')})",
                    request)

    return {
        "deleted": True,
        "was_status": doc.get("status"),
        "had_account": bool(doc.get("portal_user_id")),
        "round": round_key,
        "received": received,
        "round_reopened": reopened,
        "seats_remaining": founding.seats_remaining(
            await _approved_in_round(round_key)),
    }


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
            "seats_remaining": founding.seats_remaining(
                await _approved_in_round(doc.get("round")))}


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
        "seats_total": founding.SEATS_PER_INTAKE,
        "members": await _total_members(),
    }


# --- Membership: the passport --------------------------------------------------
#
# Everything below is *derived*, never stored. A membership number that lives in
# a column can drift from the thing it names; one computed from the intake and
# the order of admission cannot, because those two facts are the membership.

#: Seat order within an intake. Sorted by when the decision was made, so the
#: fourth person admitted in 2026-Q3 is seat 4 for good — a later approval
#: cannot renumber someone who was already in.
async def _seat_number(application: dict) -> int:
    round_key = application.get("round") or founding.round_key()
    peers = await db[APPLICATIONS].find(
        {"status": founding.APPROVED, "round": round_key},
        {"decided_at": 1},
    ).to_list(200)
    # Undecided-but-approved rows would sort unpredictably against real dates,
    # so they fall to the end rather than jumbling the people with timestamps.
    peers.sort(key=lambda p: (p.get("decided_at") or "9999"))
    for index, peer in enumerate(peers, start=1):
        if str(peer["_id"]) == str(application["_id"]):
            return index
    return len(peers) + 1


def _member_number(round_key: str, seat: int) -> str:
    """`OBX-2026-Q3-004`. Reads as an identity, parses as a fact."""
    return f"OBX-{round_key}-{seat:03d}"


def _parse(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


#: One quarter of membership, in days. Used only for the season stamp.
SEASON_DAYS = 90

#: How many posts make someone a voice in the room rather than a visitor.
VOICE_POSTS = 25


async def _stamps(application: dict, profile: dict) -> list:
    """The journey, read back out of records that already exist.

    Nothing here is awarded by a background job — each stamp is a question
    asked of the database at read time, so a stamp can never be out of step
    with the thing it claims happened.
    """
    app_id = str(application["_id"])
    joined = _parse(application.get("decided_at"))
    now = datetime.now(timezone.utc)

    # The room stores `author_id` as the *user* id, not the application id, so
    # the member's posts have to be found through their user record.
    user = await db.users.find_one({"founding_application_id": app_id})
    user_id = str(user["_id"]) if user else None

    first_post = None
    post_count = 0
    if user_id:
        post_count = await db[CHAT].count_documents({"author_id": user_id})
        earliest = await db[CHAT].find({"author_id": user_id}).sort(
            "created_at", 1).to_list(1)
        first_post = earliest[0].get("created_at") if earliest else None

    referrals = await db[REFERRALS].find(
        {"referrer_application_id": app_id}).sort("created_at", 1).to_list(200)
    first_referral = referrals[0].get("created_at") if referrals else None

    # Someone they introduced who actually got in. The strongest thing a member
    # can do for the circle, so it gets its own stamp rather than a counter.
    sponsored_at = None
    for row in referrals:
        if not row.get("used_by_application_id"):
            continue
        introduced = await db[APPLICATIONS].find_one(
            {"_id": to_object_id(row["used_by_application_id"])})
        if introduced and introduced.get("status") == founding.APPROVED:
            when = introduced.get("decided_at")
            if when and (sponsored_at is None or when < sponsored_at):
                sponsored_at = when

    told_us = bool((profile.get("headline") or "").strip()
                   or (profile.get("bio") or "").strip())
    builds = len(profile.get("projects") or []) > 0
    profile_touched = profile.get("updated_at")

    # Dated to the day it was actually reached, not to today — a stamp that
    # moves every time the page loads is a clock, not a record.
    season_at, season_hint = None, None
    if joined:
        elapsed = (now - joined).days
        if elapsed >= SEASON_DAYS:
            season_at = (joined + timedelta(days=SEASON_DAYS)).isoformat()
        else:
            season_hint = f"{SEASON_DAYS - elapsed} days to go"

    return [
        {"key": "admitted", "label": "Admitted",
         "note": "The day the circle said yes.",
         "earned_at": application.get("decided_at")},
        {"key": "identified", "label": "Named",
         "note": "Wrote a line about what you do.",
         "earned_at": profile_touched if told_us else None,
         "hint": "Add a headline under Profile."},
        {"key": "first_word", "label": "First Word",
         "note": "Said something in the room.",
         "earned_at": first_post,
         "hint": "Post once in Community."},
        {"key": "builder", "label": "Builder",
         "note": "Put work on the table.",
         "earned_at": profile_touched if builds else None,
         "hint": "List a project under Profile."},
        {"key": "connector", "label": "Connector",
         "note": "Minted an invitation.",
         "earned_at": first_referral,
         "hint": "Create an invitation under Refer."},
        {"key": "sponsor", "label": "Sponsor",
         "note": "Someone you introduced got in.",
         "earned_at": sponsored_at,
         "hint": "Nobody you invited has been admitted yet."},
        {"key": "voice", "label": "Voice",
         "note": f"{VOICE_POSTS} posts in the room.",
         "earned_at": first_post if post_count >= VOICE_POSTS else None,
         "hint": f"{max(0, VOICE_POSTS - post_count)} posts to go"},
        {"key": "season", "label": "Season One",
         "note": "A full quarter inside.",
         "earned_at": season_at,
         "hint": season_hint or "Counting from the day you joined."},
    ]


@router.get("/founding/membership")
async def my_passport(user: dict = Depends(require_founding)):
    """Everything that says *you are a member*: the number, the tenure, the
    journey, and what the membership actually entitles you to."""
    application = await _member(user)
    profile = await _profile(application)

    round_key = application.get("round") or founding.round_key()
    seat = await _seat_number(application)
    joined = _parse(application.get("decided_at"))
    tenure_days = (datetime.now(timezone.utc) - joined).days if joined else None

    app_id = str(application["_id"])
    referrals = await db[REFERRALS].find(
        {"referrer_application_id": app_id}).to_list(200)
    landed = [r for r in referrals if r.get("used_at")]
    admitted = 0
    for row in landed:
        if not row.get("used_by_application_id"):
            continue
        introduced = await db[APPLICATIONS].find_one(
            {"_id": to_object_id(row["used_by_application_id"])})
        if introduced and introduced.get("status") == founding.APPROVED:
            admitted += 1

    return {
        "member_number": _member_number(round_key, seat),
        "name": application.get("name"),
        "company": (application.get("answers") or {}).get("company") or "",
        "headline": profile.get("headline") or "",
        "seat": seat,
        "seats_total": founding.SEATS_PER_INTAKE,
        "intake": round_key,
        "joined_at": application.get("decided_at"),
        "tenure_days": tenure_days,
        "members": await _total_members(),
        "cohort": await _approved_in_round(round_key),
        "status": "active",
        "stamps": await _stamps(application, profile),
        "perks": {
            "invites_total": REFERRAL_CAP,
            "invites_used": len(referrals),
            "invites_remaining": max(0, REFERRAL_CAP - len(referrals)),
            "invites_landed": len(landed),
            "members_admitted": admitted,
        },
    }


# --- Members: profile, directory, projects ------------------------------------
#
# A member's application is not their profile. The application is a fixed record
# of what they said to get in and must never change; the profile is theirs to
# edit, and it is what other members actually see. Keeping them in separate
# documents is what makes "edit my profile" incapable of rewriting history.

PROFILES = "founding_profiles"

#: What a member can choose to expose. Everything here defaults to False except
#: the three fields the directory is useless without.
#:
#: Opt-in per field, because the phone number and socials on an application were
#: given to *us*, to be assessed - not to be published to nine strangers. A
#: private community that quietly republishes contact details is one leak away
#: from being the reason someone leaves.
SHAREABLE = ("email", "phone", "linkedin", "instagram", "twitter")
DEFAULT_VISIBILITY = {field: False for field in SHAREABLE}


class ProjectEntry(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=400)
    #: Free text on purpose. A fixed enum of statuses is a taxonomy argument
    #: nobody in a ten-person room needs to have.
    status: str = Field(default="", max_length=40)
    link: str = Field(default="", max_length=400)


class ProfileUpdate(BaseModel):
    headline: Optional[str] = Field(default=None, max_length=160)
    bio: Optional[str] = Field(default=None, max_length=1200)
    #: Editable copies, seeded from the application. A member who changes jobs
    #: should not have to ask us to edit a record they cannot see.
    email: Optional[str] = Field(default=None, max_length=254)
    phone: Optional[str] = Field(default=None, max_length=40)
    linkedin: Optional[str] = Field(default=None, max_length=300)
    instagram: Optional[str] = Field(default=None, max_length=300)
    twitter: Optional[str] = Field(default=None, max_length=300)
    projects: Optional[list[ProjectEntry]] = None
    visibility: Optional[dict] = None
    #: Members can ask to be listed at all. Off means the directory shows them
    #: as a member and nothing else.
    listed: Optional[bool] = None


async def _profile(application: dict) -> dict:
    """A member's profile, seeded from their application the first time.

    Seeded rather than empty so the directory is useful on day one: someone who
    never opens their profile still appears with their company and whatever
    socials they applied with — but only the three always-public fields are
    visible until they choose otherwise.
    """
    existing = await db[PROFILES].find_one({"application_id": str(application["_id"])})
    if existing:
        return existing

    answers = application.get("answers") or {}
    doc = {
        "application_id": str(application["_id"]),
        "name": application.get("name"),
        "company": answers.get("company"),
        "headline": answers.get("one_liner") or "",
        "bio": "",
        "email": application.get("email"),
        "phone": answers.get("phone") or "",
        "linkedin": answers.get("linkedin") or "",
        "instagram": answers.get("instagram") or "",
        "twitter": answers.get("twitter") or "",
        "projects": [],
        "visibility": dict(DEFAULT_VISIBILITY),
        "listed": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[PROFILES].update_one({"application_id": doc["application_id"]},
                                  {"$setOnInsert": doc}, upsert=True)
    return await db[PROFILES].find_one({"application_id": doc["application_id"]})


def _public_profile(profile: dict) -> dict:
    """One member as the rest of the circle sees them.

    Name, company and projects are always on - a directory that hides those is
    not a directory. Everything else appears only where its own visibility flag
    says so, and absent flags mean hidden.
    """
    visibility = {**DEFAULT_VISIBILITY, **(profile.get("visibility") or {})}
    view = {
        "id": profile.get("application_id"),
        "name": profile.get("name"),
        "company": profile.get("company"),
        "headline": profile.get("headline") or "",
        "bio": profile.get("bio") or "",
        "projects": profile.get("projects") or [],
    }
    for field in SHAREABLE:
        view[field] = profile.get(field) or "" if visibility.get(field) else ""
    return view


@router.get("/founding/profile")
async def my_profile(user: dict = Depends(require_founding)):
    """Your own profile, in full — visibility flags never hide it from you."""
    profile = await _profile(await _member(user))
    profile["visibility"] = {**DEFAULT_VISIBILITY, **(profile.get("visibility") or {})}
    return serialize_doc(profile)


@router.put("/founding/profile")
async def update_my_profile(payload: ProfileUpdate,
                            user: dict = Depends(require_founding)):
    """Edit your own profile. Nothing here touches the application."""
    profile = await _profile(await _member(user))

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "projects" in changes:
        # Twelve is not a rule about ambition; it keeps one member's list from
        # becoming the whole projects page.
        changes["projects"] = [p.model_dump() for p in (payload.projects or [])][:12]
    if "visibility" in changes:
        # Only the known flags, only booleans. An unknown key here would be a
        # field nothing ever reads, silently believed to be doing something.
        changes["visibility"] = {
            field: bool(changes["visibility"].get(field, False)) for field in SHAREABLE
        }
    changes["updated_at"] = _now()

    await db[PROFILES].update_one({"_id": profile["_id"]}, {"$set": changes})
    updated = await db[PROFILES].find_one({"_id": profile["_id"]})
    updated["visibility"] = {**DEFAULT_VISIBILITY, **(updated.get("visibility") or {})}
    return serialize_doc(updated)


@router.get("/founding/directory")
async def directory(user: dict = Depends(require_circle)):
    """Everyone in the circle, filtered by what each of them chose to share.

    Members only. There is no public version of this and there should not be —
    the ten people are not published, which is most of what makes it a private
    room rather than a list.
    """
    approved = await db[APPLICATIONS].find({"status": founding.APPROVED}).to_list(500)
    people = []
    for application in approved:
        profile = await _profile(application)
        if not profile.get("listed", True):
            people.append({"id": str(application["_id"]),
                           "name": profile.get("name"),
                           "company": profile.get("company"),
                           "headline": "", "bio": "", "projects": [],
                           **{f: "" for f in SHAREABLE}})
            continue
        people.append(_public_profile(profile))
    people.sort(key=lambda p: (p.get("name") or "").lower())
    return people


@router.get("/founding/projects")
async def projects(user: dict = Depends(require_circle)):
    """Every project every member is working on, newest member last.

    A flat list rather than grouped by person: the point is to see what is being
    built in the room, and grouping buries a one-project member under a
    six-project one.
    """
    people = await directory(user)
    out = []
    for person in people:
        for project in person.get("projects") or []:
            out.append({**project, "owner": person["name"],
                        "owner_company": person.get("company"),
                        "owner_id": person["id"]})
    return out


# --- Members: referrals -------------------------------------------------------
#
# A member mints a link and sends it to someone themselves. The alternative -
# the member types their friend's name and email into our form - has us emailing
# a stranger who never asked to hear from us, on the say-so of a third party.
# A link the referrer sends personally is both better manners and a better
# introduction than any automated invite we could write.
#
# The link does not skip anything. It carries a tag through to the application
# so you can see who vouched; the eleven questions, the score and the decision
# are identical. A referral that bought a seat would make the circle a place you
# get into by knowing someone, which is the opposite of the point.

REFERRALS = "founding_referrals"

#: Per member, for the life of their membership. Generous enough that nobody
#: sensible hits it, low enough that a leaked account cannot mint a thousand.
REFERRAL_CAP = 25


class ReferralCreate(BaseModel):
    #: Who they mean to send it to. For the member's own list only — we never
    #: contact this person, so it is a label rather than a recipient.
    label: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=400)


@router.get("/founding/referrals")
async def my_referrals(user: dict = Depends(require_founding)):
    """The links you've minted, and what became of them."""
    member = await _member(user)
    rows = await db[REFERRALS].find(
        {"referrer_application_id": str(member["_id"])}).sort("created_at", -1).to_list(200)

    out = []
    for row in rows:
        application = None
        if row.get("used_by_application_id"):
            application = await db[APPLICATIONS].find_one(
                {"_id": to_object_id(row["used_by_application_id"])})
        out.append({
            "id": str(row["_id"]),
            "code": row["code"],
            "label": row.get("label") or "",
            "note": row.get("note") or "",
            "created_at": row.get("created_at"),
            "used_at": row.get("used_at"),
            # Deliberately coarse. A referrer is told their introduction landed
            # and whether it went anywhere; they are not shown someone else's
            # score, answers or rejection.
            "status": (application or {}).get("status") if application else None,
            "applicant_name": (application or {}).get("name") if application else None,
        })
    return out


@router.post("/founding/referrals")
async def create_referral(payload: ReferralCreate,
                          user: dict = Depends(require_founding)):
    member = await _member(user)
    used = await db[REFERRALS].count_documents(
        {"referrer_application_id": str(member["_id"])})
    if used >= REFERRAL_CAP:
        raise HTTPException(
            status_code=409,
            detail=f"That's all {REFERRAL_CAP} of your invitations. Ask us if you need more.")

    code = secrets.token_urlsafe(9)
    await db[REFERRALS].insert_one({
        "code": code,
        "referrer_application_id": str(member["_id"]),
        "referrer_name": member.get("name"),
        "label": payload.label.strip(),
        "note": payload.note.strip(),
        "created_at": _now(),
        "used_at": None,
        "used_by_application_id": None,
    })
    return {"code": code}


@router.delete("/founding/referrals/{referral_id}")
async def revoke_referral(referral_id: str, user: dict = Depends(require_founding)):
    """Withdraw a link that hasn't been used. A used one stays as a record."""
    member = await _member(user)
    try:
        oid = to_object_id(referral_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Invitation not found")

    result = await db[REFERRALS].delete_one({
        "_id": oid,
        "referrer_application_id": str(member["_id"]),
        "used_at": None,
    })
    if not result.deleted_count:
        raise HTTPException(status_code=404,
                            detail="Not found, or it has already been used.")
    return {"revoked": True}


@router.get("/public/founding/referral/{code}")
async def check_referral(code: str):
    """Does this invitation code mean anything? Used by the website's form.

    Says who vouched and nothing else. It is a public endpoint, so it must not
    become a way to enumerate members: an unknown code and a used one both
    answer `valid: false` with no further detail.
    """
    row = await db[REFERRALS].find_one({"code": code, "used_at": None})
    if not row:
        return {"valid": False}
    return {"valid": True, "referrer": row.get("referrer_name")}


class ChatPost(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


# `require_circle` is defined at the top of the module — see the note there on
# why it cannot live beside the endpoints that use it.


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
    await _notify_circle(message, exclude_user_id=user["id"])
    return serialize_doc(await db[CHAT].find_one({"_id": result.inserted_id}))


# --- The room's unread state ---------------------------------------------------
#
# Read state is a marker per person, not a flag per message. Ten members and one
# shared room means a per-message `read_by` array would grow with the circle and
# be rewritten on every glance; a single timestamp answers the only question the
# interface asks — is there anything since I last looked.

READS = "founding_reads"


async def _notify_circle(message: dict, *, exclude_user_id: str) -> None:
    """Tell everyone else in the room that something was said.

    Best-effort on purpose: a failure to write a notification must never lose
    the message that caused it, so this swallows rather than raises.
    """
    try:
        recipients = await db.users.find(
            {"role": {"$in": [FOUNDING_ROLE, "admin", "team_member"]}},
            {"_id": 1},
        ).to_list(200)
        now = _now()
        rows = [{
            "user_id": str(person["_id"]),
            "type": "founding_chat",
            "title": f"{message.get('author_name') or 'Someone'} posted in the circle",
            "message": (message.get("body") or "")[:200],
            "link": "/founding-portal?tab=chat",
            "read": False,
            "created_at": now,
        } for person in recipients if str(person["_id"]) != str(exclude_user_id)]
        if rows:
            await db.notifications.insert_many(rows)
    except Exception:
        logger.warning("Could not write circle notifications", exc_info=True)


@router.get("/founding/unread")
async def unread(user: dict = Depends(require_circle)):
    """How many messages have landed in the room since this person last read it.

    Their own posts never count: you do not have unread mail from yourself.
    """
    marker = await db[READS].find_one({"user_id": user["id"]})
    since = (marker or {}).get("chat_read_at")
    query = {"author_id": {"$ne": user["id"]}}
    if since:
        query["created_at"] = {"$gt": since}
    return {"community": await db[CHAT].count_documents(query)}


@router.post("/founding/chat/read")
async def mark_chat_read(user: dict = Depends(require_circle)):
    """Called when the room is on screen. Idempotent — the marker only ever
    moves forward, because it is always set to now."""
    await db[READS].update_one(
        {"user_id": user["id"]},
        {"$set": {"chat_read_at": _now()}},
        upsert=True,
    )
    return {"community": 0}


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


# The member's assistant used to live here, with its own system prompt and its
# own copy of the facts about Obrinex. It went on telling members that intakes
# were monthly for a full quarter after they became quarterly, because the copy
# here was never updated with the model.
#
# It is now `routers/me.py`, which serves members and clients from one prompt
# and one set of house facts — so there is exactly one place a fact about
# Obrinex can be wrong, instead of two that can disagree.


async def create_founding_indexes() -> None:
    """Called from `database.create_indexes()`. Idempotent."""
    try:
        await db[APPLICATIONS].create_index([("round", 1), ("email", 1)], unique=True)
        await db[APPLICATIONS].create_index("status")
        await db[APPLICATIONS].create_index("invite_token", sparse=True)
        await db[ROUNDS].create_index("key", unique=True)
        await db[CHAT].create_index("created_at")
    except Exception as exc:
        logger.error("Could not create Founding Circle indexes: %s", exc)

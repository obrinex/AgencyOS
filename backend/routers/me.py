"""Everything that belongs to *the person signed in*: their onboarding, their
portal guide, and their assistant.

One router for two audiences. A founding member and a client have different
portals, different roles and different data, but "what do you know about me" and
"answer my question" are the same two operations — and writing them twice is how
two assistants drift into behaving differently for no reason anyone chose.

## The assistant is scoped by the server, not by the prompt

Every request rebuilds a snapshot of *only this person's* data and puts it in
the system message. A client's snapshot is built from their `client_id`; a
member's from their application. Nothing else is reachable, and that is enforced
by the queries below rather than by asking the model nicely — a prompt that says
"do not mention other clients" is a wish, and a query filtered by `client_id` is
a fact.

## Staff do not come through here

`/api/ai/*` is the staff assistant and sees the whole agency. This one never
does. They are separate endpoints with separate prompts because they have
separate blast radii.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import onboarding
from auth_utils import get_current_user
from database import db, serialize_list, to_object_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/me", tags=["me"])

#: One document per user: their interview answers and whether they have seen the
#: portal guide. Separate from `users` so an auth record stays an auth record.
CONTEXT = "portal_contexts"
#: One thread per user, for the portal assistant. Not shared with the staff
#: assistant's `ai_chat_messages` — different audience, different retention.
MESSAGES = "assistant_messages"

#: How much of the thread is replayed to the model. Ten turns is roughly the
#: length of one working conversation; beyond that the interview answers carry
#: the continuity, which is what they are for.
HISTORY_TURNS = 10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _context(user: dict) -> dict:
    doc = await db[CONTEXT].find_one({"user_id": user["id"]})
    if doc:
        return doc
    seed = {
        "user_id": user["id"],
        "role": user.get("role"),
        "answers": {},
        "guide_seen": False,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[CONTEXT].update_one({"user_id": user["id"]}, {"$setOnInsert": seed}, upsert=True)
    return await db[CONTEXT].find_one({"user_id": user["id"]})


# --- Onboarding ---------------------------------------------------------------

class AnswerSave(BaseModel):
    #: One answer at a time. The gate saves on every step rather than at the end
    #: — ten questions behind a single submit is ten answers lost to one dropped
    #: connection.
    key: str = Field(min_length=1, max_length=60)
    value: str = Field(default="", max_length=2000)


@router.get("/context")
async def my_context(user: dict = Depends(get_current_user)):
    """What the portal shell needs before it can render: am I interviewed, have
    I seen the guide, and what am I being asked."""
    doc = await _context(user)
    role = user.get("role")
    questions = onboarding.questions_for(role)
    answers = doc.get("answers") or {}
    return {
        "role": role,
        "name": user.get("name"),
        "questions": questions,
        "answers": answers,
        # Roles with no interview (staff) are complete by definition, which is
        # what keeps the gate from appearing in the CRM.
        "onboarding_complete": onboarding.is_complete(role, answers),
        "guide_seen": bool(doc.get("guide_seen")),
    }


@router.post("/onboarding")
async def save_answer(payload: AnswerSave, user: dict = Depends(get_current_user)):
    role = user.get("role")
    known = {q["key"] for q in onboarding.questions_for(role)}
    if payload.key not in known:
        # An unknown key would be a field nothing ever reads, silently believed
        # to be doing something.
        raise HTTPException(status_code=400, detail="Not a question we asked.")

    await _context(user)
    await db[CONTEXT].update_one(
        {"user_id": user["id"]},
        {"$set": {f"answers.{payload.key}": payload.value.strip(),
                  "updated_at": _now()}},
    )
    doc = await db[CONTEXT].find_one({"user_id": user["id"]})
    answers = doc.get("answers") or {}
    return {"saved": True, "onboarding_complete": onboarding.is_complete(role, answers)}


@router.post("/guide-seen")
async def mark_guide_seen(user: dict = Depends(get_current_user)):
    await _context(user)
    await db[CONTEXT].update_one(
        {"user_id": user["id"]},
        {"$set": {"guide_seen": True, "updated_at": _now()}},
    )
    return {"guide_seen": True}


@router.post("/guide-reset")
async def reset_guide(user: dict = Depends(get_current_user)):
    """Replay the tour. Someone who skimmed it the first time should not have to
    clear site data to see it again."""
    await _context(user)
    await db[CONTEXT].update_one(
        {"user_id": user["id"]}, {"$set": {"guide_seen": False, "updated_at": _now()}}
    )
    return {"guide_seen": False}


# --- What the assistant is allowed to see -------------------------------------

def _money(value) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value or 0)


async def _client_snapshot(user: dict) -> str:
    """One client's own account, in prose.

    Every query below is filtered by `client_id`. That filter is the security
    boundary — remove it and the assistant becomes a way for any client to read
    the whole agency.
    """
    client_id = user.get("client_id")
    if not client_id:
        return "This person has no client account linked, so there is no account data to draw on."

    client = None
    try:
        client = await db.clients.find_one({"_id": to_object_id(client_id)})
    except Exception:
        pass

    projects = await db.projects.find({"client_id": client_id}).to_list(100)
    invoices = await db.invoices.find({"client_id": client_id}).to_list(100)
    tickets = await db.tickets.find({"client_id": client_id}).sort("created_at", -1).to_list(50)
    contracts = await db.contracts.find({"client_id": client_id}).to_list(50)

    unpaid = [i for i in invoices if i.get("status") in ("sent", "overdue", "partial", "viewed")]
    open_tickets = [t for t in tickets if t.get("status") not in ("resolved", "closed")]
    unsigned = [c for c in contracts if c.get("status") != "signed"]

    parts = [f"Account: {(client or {}).get('company_name') or 'this client'}."]

    if projects:
        parts.append("Projects:")
        for p in projects[:12]:
            parts.append(
                f"- {p.get('name')} — {p.get('status')}, {p.get('progress', 0)}% complete"
            )
    else:
        parts.append("Projects: none yet.")

    if invoices:
        parts.append(f"Invoices: {len(invoices)} total, {len(unpaid)} unpaid.")
        for i in unpaid[:8]:
            due = f", due {i.get('due_date')}" if i.get("due_date") else ""
            parts.append(
                f"- {i.get('invoice_number')} — {i.get('status')}, "
                f"{i.get('currency') or ''}{_money(i.get('total'))}{due}"
            )
    else:
        parts.append("Invoices: none yet.")

    parts.append(f"Support: {len(open_tickets)} open of {len(tickets)} tickets.")
    for t in open_tickets[:6]:
        parts.append(f"- “{t.get('subject')}” — {t.get('status')}, priority {t.get('priority')}")

    if unsigned:
        parts.append("Contracts awaiting their signature: "
                     + ", ".join(c.get("title") or "untitled" for c in unsigned[:6]))

    return "\n".join(parts)


async def _member_snapshot(user: dict) -> str:
    """One member's own membership.

    Imported lazily. `routers.founding` is a heavy module and importing it at
    the top would couple this router's import time to it for the client half of
    the traffic, which never touches any of this.
    """
    from routers import founding as founding_router
    import founding as founding_model

    try:
        application = await founding_router._member(user)
    except HTTPException:
        return "This member's application record could not be found."

    profile = await founding_router._profile(application)
    round_key = application.get("round") or founding_model.round_key()
    seat = await founding_router._seat_number(application)
    number = founding_router._member_number(round_key, seat)
    stamps = await founding_router._stamps(application, profile)
    earned = [s["label"] for s in stamps if s.get("earned_at")]
    missing = [f"{s['label']} ({s.get('hint') or 'not yet'})"
               for s in stamps if not s.get("earned_at")]

    referrals = await db[founding_router.REFERRALS].find(
        {"referrer_application_id": str(application["_id"])}).to_list(200)

    # Names only. A member may ask "who's in the circle" and should be told —
    # they are in it. What is never included is anyone's contact details, which
    # are opt-in per field and belong to the directory, not to a prompt.
    approved = await db[founding_router.APPLICATIONS].find(
        {"status": founding_model.APPROVED}, {"name": 1}).to_list(200)

    return "\n".join([
        f"Membership: {number}, seat {seat} of {founding_model.SEATS_PER_INTAKE}, "
        f"intake {round_key}, admitted {application.get('decided_at')}.",
        f"Stamps earned: {', '.join(earned) or 'none yet'}.",
        f"Stamps outstanding: {'; '.join(missing) or 'none — all earned'}.",
        f"Invitations: {len(referrals)} minted of {founding_router.REFERRAL_CAP}, "
        f"{founding_router.REFERRAL_CAP - len(referrals)} remaining.",
        f"The circle currently has {len(approved)} members: "
        + ", ".join(a.get("name") or "unnamed" for a in approved) + ".",
        "Their profile headline: " + (profile.get("headline") or "not set yet") + ".",
    ])


# --- Who the assistant is -----------------------------------------------------

#: Facts about Obrinex both assistants may state. Kept in one string so the two
#: audiences cannot be told different things about the same company — which is
#: exactly what happened when the founding assistant carried its own copy and
#: went on saying intakes were monthly for a quarter after they became
#: quarterly.
HOUSE_FACTS = """About Obrinex:
- Obrinex is an AI automation agency. It builds automation, AI assistants and \
internal systems for businesses, and runs its own CRM (Obrinex CRM) which is \
what this portal is part of.
- The Founding Circle is a private community Obrinex runs. Intakes are \
QUARTERLY, ten seats per intake. Membership accumulates across intakes, so the \
circle grows by up to ten people a quarter.
- Applications are scored on eleven questions. A referral from a member gets an \
application read sooner, never accepted sooner.
- Membership is never published. The list of members is visible only inside the \
circle."""

SHARED_RULES = """Rules you do not break:
- Everything in "What you know about them" below is real, current data about \
THIS person. Use it. If they ask about their invoices, projects, membership or \
tickets, answer from it directly and specifically.
- You cannot see anyone else's data — no other client, no other member's \
private details. If asked, say so plainly rather than guessing.
- Never invent a price, a date, a deadline, a policy or a feature. If you do \
not know, say you do not know and say who can tell them.
- Do not repeat their whole context back at them. You know it; just use it.
- Be concise. Answer first, explain second. Skip preamble entirely."""

CLIENT_PERSONA = """You are the Obrinex client assistant, speaking with a client \
of the agency inside their own portal.

You can help with: where their projects stand, what they owe and when, what a \
document or invoice means, how to use any part of this portal, chasing up a \
ticket, drafting a message to their Obrinex team, and general business or \
marketing thinking.

What you cannot do: change anything. You cannot pay an invoice, sign a \
contract, close a ticket or edit a project. When something needs doing, tell \
them exactly which page does it."""

MEMBER_PERSONA = """You are the Founding Circle assistant, speaking privately \
with one member inside the members' portal.

You can help with: how the circle works, their membership and its stamps, \
finding the right person in the circle to talk to, and — mostly — their actual \
work. Thinking through a business problem, pressure-testing a plan, drafting \
and cutting their writing, pricing, hiring, positioning.

Talk to them like a peer, not a support desk. They were selected; they do not \
need to be sold to or congratulated."""


PORTAL_MAP = {
    onboarding.CLIENT_ROLE: """The pages of their portal, so you can point \
precisely: Overview (figures and recent projects), Projects (progress and \
tasks), Invoices (amounts, status, payment), Contracts (review and e-sign), \
Files (upload and download), Messages (direct thread with their Obrinex team), \
Support (tickets), Policies, and Assistant (you).""",
    onboarding.FOUNDING_ROLE: """The sections of their portal, so you can point \
precisely: Membership (their passport, member number, stamps and invitations), \
Community (the one shared room), Members (the directory, contact details \
opt-in per person), Projects (what everyone is building), Refer (minting \
invitation links), Profile (what the circle sees), Guidelines, Help, and \
Assistant (you).""",
}


async def _system_prompt(user: dict, context_doc: dict) -> str:
    role = user.get("role")
    persona = MEMBER_PERSONA if role == onboarding.FOUNDING_ROLE else CLIENT_PERSONA
    snapshot = (
        await _member_snapshot(user)
        if role == onboarding.FOUNDING_ROLE
        else await _client_snapshot(user)
    )
    interview = onboarding.summarise(role, context_doc.get("answers"))

    return "\n\n".join([
        persona,
        HOUSE_FACTS,
        PORTAL_MAP.get(role, ""),
        SHARED_RULES,
        f"Who you are speaking with: {user.get('name') or 'a member'}.",
        "What they told us about themselves when they joined:\n"
        + (interview or "They have not been interviewed yet."),
        "What you know about them right now (live, from their account):\n" + snapshot,
    ])


# --- The assistant ------------------------------------------------------------

class Ask(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.get("/assistant")
async def history(user: dict = Depends(get_current_user)):
    rows = await db[MESSAGES].find({"user_id": user["id"]}) \
        .sort("created_at", 1).to_list(200)
    return serialize_list(rows)


@router.delete("/assistant")
async def clear_thread(user: dict = Depends(get_current_user)):
    """Start again. The interview answers survive — those are memory, not chat."""
    result = await db[MESSAGES].delete_many({"user_id": user["id"]})
    return {"cleared": result.deleted_count}


@router.get("/assistant/suggestions")
async def suggestions(user: dict = Depends(get_current_user)):
    """Openers worth tapping, chosen from what is actually true of this account.

    A fixed list of prompts is decoration. "Why is INV-0042 overdue?" is a
    question they were probably already going to ask.
    """
    role = user.get("role")
    out = []

    if role == onboarding.FOUNDING_ROLE:
        try:
            from routers import founding as founding_router
            application = await founding_router._member(user)
            profile = await founding_router._profile(application)
            stamps = await founding_router._stamps(application, profile)
            nxt = next((s for s in stamps if not s.get("earned_at")), None)
            if nxt:
                out.append(f"How do I earn the {nxt['label']} stamp?")
        except Exception:
            pass
        out += [
            "Who in the circle should I talk to about my bottleneck?",
            "Pressure-test what I'm building right now.",
            "How does the invitation system actually work?",
        ]
    else:
        client_id = user.get("client_id")
        if client_id:
            unpaid = await db.invoices.find({
                "client_id": client_id,
                "status": {"$in": ["overdue", "sent", "partial"]},
            }).to_list(3)
            for invoice in unpaid[:1]:
                out.append(f"What is invoice {invoice.get('invoice_number')} for?")
            active = await db.projects.find({
                "client_id": client_id,
                "status": {"$nin": ["completed", "archived"]},
            }).to_list(3)
            for project in active[:1]:
                out.append(f"Where are we on {project.get('name')}?")
        out += [
            "Summarise everything outstanding on my account.",
            "How do I pay an invoice from here?",
        ]

    return out[:4]


@router.post("/assistant")
async def ask(payload: Ask, user: dict = Depends(get_current_user)):
    import llm_providers

    chain = llm_providers.chain()
    if not chain:
        raise HTTPException(status_code=503, detail="The assistant is not configured yet.")

    context_doc = await _context(user)
    system = await _system_prompt(user, context_doc)

    past = await db[MESSAGES].find({"user_id": user["id"]}) \
        .sort("created_at", -1).to_list(HISTORY_TURNS * 2)
    turns = [{"role": m["role"], "content": m["content"]} for m in reversed(past)]

    messages = (
        [{"role": "system", "content": system}]
        + turns
        + [{"role": "user", "content": payload.message}]
    )

    # Walk the chain rather than trusting the first provider. One provider
    # rate-limiting should not read to a member as "the assistant is broken".
    reply, last_error = "", None
    for _key, make_client, model in chain[:3]:
        try:
            response = await make_client().chat.completions.create(
                model=model, messages=messages, stream=False, timeout=30)
            choices = getattr(response, "choices", None) or []
            reply = ((choices[0].message.content or "") if choices else "").strip()
            if reply:
                break
        except Exception as exc:
            last_error = exc
            logger.warning("Portal assistant provider %s failed: %s", _key, exc)

    if not reply:
        logger.warning("Portal assistant produced nothing; last error: %s", last_error)
        raise HTTPException(
            status_code=502,
            detail="The assistant could not answer right now. Try again in a moment.")

    now = _now()
    await db[MESSAGES].insert_many([
        {"user_id": user["id"], "role": "user", "content": payload.message,
         "created_at": now},
        {"user_id": user["id"], "role": "assistant", "content": reply,
         "created_at": now},
    ])
    return {"reply": reply}


async def create_me_indexes() -> None:
    """Called from `database.create_indexes()`. Idempotent."""
    try:
        await db[CONTEXT].create_index("user_id", unique=True)
        await db[MESSAGES].create_index([("user_id", 1), ("created_at", 1)])
    except Exception as exc:
        logger.error("Could not create portal-context indexes: %s", exc)

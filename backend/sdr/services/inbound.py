"""Inbound replies: match, classify, act.

The order is deliberate and each step can stand alone:

1. **Store first.** Before matching, before classifying. A reply we cannot
   route is still a person waiting on an answer, and it must be findable.
2. **Match by Message-ID.** The header we minted at dispatch. Falls back to
   the from-address only when nothing threads — and anything matched that way
   is flagged for a human, because it cannot tell two campaigns apart.
3. **Classify by headers, then by model.** Machine detection is deterministic
   and runs first; the model is only asked about what survives it.
4. **Act.** One switch, driven by `inbound_domain.action_for`.

The invariant worth stating plainly: **only a human reply stops a sequence.**
An out-of-office defers. An auto-reply changes nothing. Getting that backwards
strands live leads in a state that looks like success.
"""

import logging

from database import db, now_iso
from sdr.agents.base.agent import AgentContext
from sdr.agents.inbound.agent import InboundClassifierAgent
from sdr.collections import ENROLLMENTS
from sdr.domain import inbound as inbound_domain
from sdr.domain import sequence as sequence_domain
from sdr.repositories import campaigns as campaigns_repo
from sdr.repositories import inbound as inbound_repo
from sdr.repositories import suppression as suppression_repo
from sdr.repositories.base import object_id
from sdr.errors import ValidationError

logger = logging.getLogger(__name__)


async def ingest(normalized: dict) -> dict:
    """The whole inbound path for one reply. Safe to call twice."""
    stored = await inbound_repo.record(
        ingest_key=normalized.get("ingest_key") or "",
        from_email=normalized.get("from_email") or "",
        to_email=normalized.get("to_email") or "",
        subject=normalized.get("subject") or "",
        text_body=normalized.get("text_body") or "",
        headers=normalized.get("headers") or {},
        in_reply_to=normalized.get("in_reply_to"),
        references=normalized.get("references"),
        provider=normalized.get("provider") or "unknown",
        received_at=normalized.get("received_at"),
    )
    if stored.get("duplicate"):
        # The provider retried something already handled. Acting again would
        # re-suppress and re-stamp; both are meant to happen once.
        return {"inbound_id": stored["id"], "duplicate": True,
                "category": stored.get("category")}

    matched = await _match(stored)
    await inbound_repo.update(stored["id"], matched)
    stored = {**stored, **matched}

    classified = await _classify(stored)
    await inbound_repo.update(stored["id"], classified)
    stored = {**stored, **classified}

    acted = await _act(stored)
    await inbound_repo.update(stored["id"], {**acted, "processed_at": now_iso()})

    return {"inbound_id": stored["id"], "duplicate": False,
            "category": stored["category"], "match_method": stored["match_method"],
            **acted}


async def reclassify(inbound_id: str, category: str, *, user: dict) -> dict:
    """A human overrides the category, and the new one is applied for real.

    The point is not to relabel a row - it is to undo a wrong call. The
    classifier deciding `interested` on an out-of-office is exactly the case
    this exists for, and correcting it has to actually restart the sequence,
    not just change a word on screen.
    """
    if category not in inbound_domain.CATEGORIES:
        raise ValidationError(f"Unknown category '{category}'.")

    stored = await inbound_repo.get(inbound_id)
    previous = stored.get("category")
    if previous == category:
        return {**stored, "changed": False}

    stored["category"] = category
    acted = await _act(stored)

    # Reversing a stop is the whole point of the override, and it has to be
    # explicit: `stop_enrollment` is one-way, so nothing else would undo it.
    was_stopped = bool(inbound_domain.action_for(previous or "auto_reply")["stop_reason"])
    now_stops = bool(inbound_domain.action_for(category)["stop_reason"])
    if was_stopped and not now_stops and stored.get("enrollment_id"):
        resumed = await _resume_enrollment(stored["enrollment_id"])
        if resumed:
            acted["action_taken"] = list(acted["action_taken"]) + ["resumed"]

    return {**await inbound_repo.update(inbound_id, {
        **acted,
        "category": category,
        "category_source": "human",
        "category_confidence": 1.0,
        "needs_human": False,
        "reclassified_by": user.get("id"),
        "reclassified_from": previous,
        "processed_at": now_iso(),
    }), "changed": True}


async def mark_reviewed(inbound_id: str, *, user: dict) -> dict:
    """A human looked at it and the classification stands."""
    return await inbound_repo.update(inbound_id, {
        "needs_human": False,
        "reviewed_by": user.get("id"),
        "reviewed_at": now_iso(),
    })


async def summary() -> dict:
    """Counts for the inbox filter tabs."""
    from sdr.collections import INBOUND

    counts = {}
    cursor = db[INBOUND].aggregate([
        {"$group": {"_id": "$category", "count": {"$sum": 1}}}
    ])
    async for row in cursor:
        if row["_id"]:
            counts[row["_id"]] = row["count"]

    return {
        "by_category": counts,
        "total": sum(counts.values()),
        "needs_human": await db[INBOUND].count_documents({"needs_human": True}),
        "unmatched": await inbound_repo.count_unmatched(),
    }


async def _resume_enrollment(enrollment_id: str) -> bool:
    """Put a wrongly-stopped enrollment back into rotation.

    Only ever un-stops something this module stopped for a reply-shaped
    reason. An enrollment stopped because the address bounced or the lead
    unsubscribed is not resurrected by relabelling a message - those refusals
    outrank a human's opinion about one email.
    """
    enrollment = await campaigns_repo.get_enrollment(enrollment_id)
    if enrollment["status"] != sequence_domain.STOPPED:
        return False
    if enrollment.get("stopped_reason") not in ("replied", "wrong_person"):
        return False

    await db[ENROLLMENTS].update_one(
        {"_id": object_id(enrollment_id, "enrollment id")},
        {"$set": {
            "status": sequence_domain.ACTIVE,
            "stopped_reason": None,
            "stopped_at": None,
            "resumed_at": now_iso(),
            "updated_at": now_iso(),
        }},
    )
    return True


# --- Matching -----------------------------------------------------------------

async def _match(stored: dict) -> dict:
    """Find the outbound message this reply answers."""
    candidates = inbound_domain.match_order(
        stored.get("in_reply_to"), stored.get("references")
    )
    for candidate in candidates:
        message = await campaigns_repo.find_by_email_message_id(candidate)
        if message:
            return _match_fields(message, "threaded", needs_human=False)

    # Nothing threaded. Either the client stripped the headers, the reply was
    # composed fresh, or the message predates threading entirely.
    message = await inbound_repo.latest_message_to(stored["from_email"])
    if message:
        return _match_fields(message, "sender", needs_human=True)

    return {"message_id": None, "enrollment_id": None, "campaign_id": None,
            "lead_id": None, "match_method": "none", "needs_human": True}


def _match_fields(message: dict, method: str, *, needs_human: bool) -> dict:
    return {
        "message_id": message.get("id"),
        "enrollment_id": message.get("enrollment_id"),
        "campaign_id": message.get("campaign_id"),
        "lead_id": message.get("lead_id"),
        "match_method": method,
        # A sender match is a guess. It routes, but a person confirms it.
        "needs_human": needs_human,
    }


# --- Classification -----------------------------------------------------------

async def _classify(stored: dict) -> dict:
    """Headers decide if they can; the model decides the rest."""
    machine = inbound_domain.detect_machine_reply(
        headers=stored.get("headers"),
        subject=stored.get("subject"),
        from_email=stored.get("from_email"),
    )
    if machine:
        # No model call: headers are authoritative here, and this is the
        # classification we least want a model's opinion on.
        return {"category": machine, "category_confidence": 1.0,
                "category_source": "headers",
                "needs_human": stored.get("needs_human", False)}

    sent = {}
    if stored.get("message_id"):
        try:
            sent = await campaigns_repo.get_message(stored["message_id"])
        except Exception:   # a deleted message must not block the reply
            logger.warning("Inbound %s references a missing message", stored["id"])

    try:
        result = await InboundClassifierAgent().run({
            "sent_subject": sent.get("subject"),
            "sent_body": sent.get("body"),
            "reply_subject": stored.get("subject"),
            "reply_body": stored.get("text_body"),
            "from_email": stored.get("from_email"),
        }, AgentContext(trigger="inbound_webhook"))
        output = result.output
    except Exception as exc:
        # A classifier outage must not lose the reply or, worse, guess. It
        # parks for a human with the sequence untouched - which is the safe
        # direction: a lead who answered gets a slow response rather than
        # another automated email, because `objection` stops the sequence.
        logger.exception("Inbound classification failed for %s", stored["id"])
        return {"category": "objection", "category_confidence": 0.0,
                "category_source": "error", "needs_human": True,
                "classification_error": str(exc)[:300]}

    return {
        "category": output["category"],
        "category_confidence": output["confidence"],
        "category_source": "classifier",
        "reasoning": output.get("reasoning"),
        "needs_human": bool(output.get("needs_human")) or stored.get("needs_human", False),
    }


# --- Acting -------------------------------------------------------------------

async def _act(stored: dict) -> dict:
    """Apply the category. One place, one switch."""
    action = inbound_domain.action_for(stored["category"])
    taken = []

    if action["suppress"]:
        await suppression_repo.suppress(
            value=stored["from_email"],
            reason="unsubscribe" if stored["category"] == "unsubscribe_request" else "bounce",
            source="inbound_reply",
        )
        if stored["category"] == "unsubscribe_request":
            await suppression_repo.record_consent(
                action="opt_out", value=stored["from_email"], channel="email",
                legal_basis="withdrawal", evidence={"source": "inbound_reply",
                                                    "inbound_id": stored["id"]},
            )
        taken.append("suppressed")

    if action["counts_as_reply"] and stored.get("lead_id"):
        await _stamp_lead_replied(stored)
        taken.append("lead_marked_replied")

    if action["stop_reason"] and stored.get("enrollment_id"):
        await campaigns_repo.stop_enrollment(
            stored["enrollment_id"], action["stop_reason"]
        )
        taken.append(f"stopped:{action['stop_reason']}")

    if action["defer_days"] and stored.get("enrollment_id"):
        deferred = await _defer_enrollment(
            stored["enrollment_id"], action["defer_days"]
        )
        if deferred:
            taken.append(f"deferred:{action['defer_days']}d")

    return {"action_taken": taken or ["none"],
            "needs_human": stored.get("needs_human", False)}


async def _stamp_lead_replied(stored: dict) -> None:
    """Mirror of the manual `mark_lead_replied` hook, minus the stopping -
    the caller decides that from the category."""
    await db.leads.update_one(
        {"_id": object_id(stored["lead_id"], "lead id")},
        {"$set": {"replied_at": now_iso(), "updated_at": now_iso()}},
    )
    await db.lead_activities.insert_one({
        "lead_id": stored["lead_id"], "type": "note",
        "content": f"Reply received ({stored['category']}): "
                   f"{(stored.get('subject') or '(no subject)')[:120]}",
        "created_by": None, "created_at": now_iso(),
    })


async def _defer_enrollment(enrollment_id: str, days: int) -> bool:
    """Push the next touch out without ending the sequence.

    The out-of-office path. Returns False for an enrollment that is not
    active, so a completed or already-stopped sequence is not resurrected by
    a vacation responder arriving late.
    """
    from datetime import datetime, timedelta, timezone

    enrollment = await campaigns_repo.get_enrollment(enrollment_id)
    if enrollment["status"] != sequence_domain.ACTIVE:
        return False

    base = datetime.now(timezone.utc)
    current = enrollment.get("next_touch_at")
    if current:
        try:
            parsed = datetime.fromisoformat(current)
            # Only ever push further out - an OOO must not pull a touch in.
            base = max(base, parsed)
        except ValueError:
            pass

    await db[ENROLLMENTS].update_one(
        {"_id": object_id(enrollment_id, "enrollment id")},
        {"$set": {
            "next_touch_at": (base + timedelta(days=days)).isoformat(),
            "deferred_reason": "out_of_office",
            "deferred_at": now_iso(),
            "updated_at": now_iso(),
        }},
    )
    return True

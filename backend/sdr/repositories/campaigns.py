"""Campaigns, enrollments and outbound messages.

Three collections, one invariant apiece:

- A campaign snapshots its sequence at launch. Editing a sequence later must
  never change what a running campaign sends - historical messages have to be
  attributable to the exact steps that produced them.
- One enrollment per (campaign, lead), and one *active* enrollment per lead
  across all campaigns. Two campaigns writing to the same person at once is
  how an agency looks like a botnet.
- One message per (enrollment, step), enforced by a unique index. This is the
  belt alongside the job-idempotency braces: even if a duplicate
  personalization job slips through after the job TTL, the insert fails
  rather than a second email existing.
"""

from datetime import datetime, timezone

from database import db, now_iso, serialize_doc, serialize_list
from sdr.collections import CAMPAIGNS, ENROLLMENTS, MESSAGES
from sdr.domain import sequence as sequence_domain
from sdr.errors import NotFoundError, ValidationError
from sdr.repositories.base import object_id, paginate, scope, stamp_create, stamp_update

# Campaign lifecycle. `stopped` is terminal (enrollments are stopped with it);
# `paused` holds enrollments without losing their place.
CAMPAIGN_STATUSES = ("draft", "running", "paused", "stopped", "completed")

# Message lifecycle. `needs_review` is the deliberately-uncomfortable state:
# a send whose outcome is unknown (crashed mid-provider-call) parks there for
# a human rather than risking a double send on retry.
MESSAGE_STATUSES = (
    "awaiting_approval", "approved", "sending", "sent", "delivered",
    "bounced", "complained", "failed", "rejected", "cancelled", "needs_review",
)


# --- Campaigns ----------------------------------------------------------------

async def create_campaign(*, name: str, sequence_steps: list, approval_mode: str,
                          user: dict, max_touches: int) -> dict:
    problems = sequence_domain.validate_sequence(sequence_steps, max_touches=max_touches)
    if problems:
        raise ValidationError("The sequence has problems: " + " ".join(problems))
    if approval_mode not in ("manual", "auto"):
        raise ValidationError("approval_mode must be 'manual' or 'auto'.")

    doc = {
        "name": (name or "").strip() or "Untitled campaign",
        "status": "draft",
        # Snapshot, not a reference - see the module docstring.
        "sequence": [
            {"delay_days": step["delay_days"], "goal": step.get("goal") or f"step_{i+1}",
             "instruction": step["instruction"].strip()}
            for i, step in enumerate(sequence_steps)
        ],
        "approval_mode": approval_mode,
        "enrolled_count": 0,
        "stats": {"sent": 0, "delivered": 0, "bounced": 0, "stopped": 0, "completed": 0},
        "launched_at": None,
        "created_by": user.get("id"),
    }
    stamp_create(doc, user)
    result = await db[CAMPAIGNS].insert_one(doc)
    return serialize_doc(await db[CAMPAIGNS].find_one({"_id": result.inserted_id}))


async def get_campaign(campaign_id: str) -> dict:
    doc = await db[CAMPAIGNS].find_one(scope({"_id": object_id(campaign_id, "campaign id")}))
    if not doc:
        raise NotFoundError("Campaign not found")
    return serialize_doc(doc)


async def list_campaigns(*, status: str | None = None, limit: int = 50,
                         cursor: str | None = None) -> dict:
    query = {}
    if status:
        query["status"] = status
    return await paginate(CAMPAIGNS, scope(query), sort=("created_at", -1),
                          limit=limit, cursor=cursor)


async def set_campaign_status(campaign_id: str, status: str) -> dict:
    if status not in CAMPAIGN_STATUSES:
        raise ValidationError(f"Unknown campaign status '{status}'.")
    campaign = await get_campaign(campaign_id)

    allowed = {
        "draft": {"running"},                 # launch
        "running": {"paused", "stopped", "completed"},
        "paused": {"running", "stopped"},
        "stopped": set(),                     # terminal
        "completed": set(),                   # terminal
    }[campaign["status"]]
    if status not in allowed:
        raise ValidationError(
            f"A {campaign['status']} campaign cannot move to {status}."
        )

    patch = {"status": status}
    if status == "running" and not campaign.get("launched_at"):
        patch["launched_at"] = now_iso()
    await db[CAMPAIGNS].update_one(
        {"_id": object_id(campaign_id, "campaign id")}, {"$set": stamp_update(patch)}
    )

    # Stopping the campaign stops every live enrollment with it, in one write.
    if status == "stopped":
        await db[ENROLLMENTS].update_many(
            {"campaign_id": campaign_id, "status": sequence_domain.ACTIVE},
            {"$set": stamp_update({
                "status": sequence_domain.STOPPED,
                "stopped_reason": "campaign_stopped",
                "stopped_at": now_iso(),
            })},
        )
    return await get_campaign(campaign_id)


async def bump_stat(campaign_id: str, field: str, delta: int = 1) -> None:
    await db[CAMPAIGNS].update_one(
        {"_id": object_id(campaign_id, "campaign id")},
        {"$inc": {f"stats.{field}": delta}},
    )


# --- Enrollments --------------------------------------------------------------

async def enroll_leads(campaign_id: str, lead_ids: list, *, cooldown_days: int) -> dict:
    """Enroll leads, skipping any that must not be sequenced. Returns a report.

    Every skip carries a reason - a lead that silently vanishes from a
    campaign is indistinguishable from a bug, and "why wasn't X contacted"
    must be answerable.
    """
    from pymongo.errors import DuplicateKeyError
    from sdr.repositories import suppression as suppression_repo

    campaign = await get_campaign(campaign_id)
    enrolled, skipped = [], []
    now = now_iso()

    for lead_id in lead_ids:
        lead_doc = await db.leads.find_one(scope({"_id": object_id(lead_id, "lead id")}))
        if not lead_doc:
            skipped.append({"lead_id": lead_id, "reason": "lead not found"})
            continue
        lead = serialize_doc(lead_doc)

        if not lead.get("email"):
            skipped.append({"lead_id": lead_id, "reason": "no email address"})
            continue
        if lead.get("qualification_status") == "disqualified":
            skipped.append({"lead_id": lead_id, "reason": "disqualified"})
            continue
        if lead.get("stage") in sequence_domain.CLOSING_STAGES:
            skipped.append({"lead_id": lead_id, "reason": f"stage is {lead['stage']}"})
            continue

        hit = await suppression_repo.is_suppressed(email=lead.get("email"))
        if hit:
            skipped.append({"lead_id": lead_id, "reason": f"suppressed ({hit['reason']})"})
            continue

        # One live sequence per person, across every campaign.
        active = await db[ENROLLMENTS].find_one(
            {"lead_id": lead_id, "status": sequence_domain.ACTIVE}
        )
        if active:
            skipped.append({"lead_id": lead_id, "reason": "already in an active sequence"})
            continue

        # Cool-down: a lead whose last sequence ended recently is left alone.
        if cooldown_days:
            recent = await db[ENROLLMENTS].find_one(
                {"lead_id": lead_id, "last_message_at": {"$ne": None}},
                sort=[("last_message_at", -1)],
            )
            if recent and recent.get("last_message_at"):
                last = datetime.fromisoformat(recent["last_message_at"])
                age_days = (datetime.now(timezone.utc) - last).days
                if age_days < cooldown_days:
                    skipped.append({
                        "lead_id": lead_id,
                        "reason": f"contacted {age_days}d ago; cool-down is {cooldown_days}d",
                    })
                    continue

        doc = {
            "campaign_id": campaign_id,
            "lead_id": lead_id,
            "status": sequence_domain.ACTIVE,
            "current_step": 0,
            # Step 1 is due immediately; the daily new-lead cap paces it.
            "next_touch_at": now,
            "last_message_at": None,
            "stopped_reason": None,
            "stopped_at": None,
            "completed_at": None,
        }
        stamp_create(doc)
        try:
            await db[ENROLLMENTS].insert_one(doc)
            enrolled.append(lead_id)
        except DuplicateKeyError:
            skipped.append({"lead_id": lead_id, "reason": "already enrolled in this campaign"})

    if enrolled:
        await db[CAMPAIGNS].update_one(
            {"_id": object_id(campaign_id, "campaign id")},
            {"$inc": {"enrolled_count": len(enrolled)}},
        )
    return {"campaign_id": campaign_id, "enrolled": len(enrolled),
            "skipped": skipped, "enrolled_lead_ids": enrolled}


async def due_enrollments(campaign_id: str, *, now: str | None = None,
                          limit: int = 200) -> list:
    query = {
        "campaign_id": campaign_id,
        "status": sequence_domain.ACTIVE,
        "next_touch_at": {"$lte": now or now_iso()},
    }
    docs = await db[ENROLLMENTS].find(query).sort("next_touch_at", 1).to_list(limit)
    return serialize_list(docs)


async def get_enrollment(enrollment_id: str) -> dict:
    doc = await db[ENROLLMENTS].find_one({"_id": object_id(enrollment_id, "enrollment id")})
    if not doc:
        raise NotFoundError("Enrollment not found")
    return serialize_doc(doc)


async def stop_enrollment(enrollment_id: str, reason: str) -> dict:
    if reason not in sequence_domain.STOP_REASONS:
        raise ValidationError(f"Unknown stop reason '{reason}'.")
    enrollment = await get_enrollment(enrollment_id)
    if enrollment["status"] != sequence_domain.ACTIVE:
        return enrollment
    await db[ENROLLMENTS].update_one(
        {"_id": object_id(enrollment_id, "enrollment id")},
        {"$set": stamp_update({
            "status": sequence_domain.STOPPED,
            "stopped_reason": reason,
            "stopped_at": now_iso(),
        })},
    )
    await bump_stat(enrollment["campaign_id"], "stopped")
    # Pending drafts for a stopped enrollment must not go out.
    await db[MESSAGES].update_many(
        {"enrollment_id": enrollment_id,
         "status": {"$in": ["awaiting_approval", "approved"]}},
        {"$set": stamp_update({"status": "cancelled", "cancel_reason": reason})},
    )
    return await get_enrollment(enrollment_id)


async def advance_enrollment(enrollment_id: str, *, sent_at: str,
                             steps: list) -> dict:
    """Move an enrollment forward after a successful send."""
    enrollment = await get_enrollment(enrollment_id)
    next_index = enrollment["current_step"] + 1
    due = sequence_domain.next_touch_at(sent_at, steps, next_index)

    patch = {"last_message_at": sent_at}
    if due is None:
        patch.update({
            "status": sequence_domain.COMPLETED,
            "completed_at": now_iso(),
            "next_touch_at": None,
            "current_step": next_index,
        })
        await bump_stat(enrollment["campaign_id"], "completed")
    else:
        patch.update({
            "current_step": next_index,
            "next_touch_at": due.isoformat(),
        })
    await db[ENROLLMENTS].update_one(
        {"_id": object_id(enrollment_id, "enrollment id")},
        {"$set": stamp_update(patch)},
    )
    return await get_enrollment(enrollment_id)


async def enrollment_summary(campaign_id: str) -> dict:
    cursor = db[ENROLLMENTS].aggregate([
        {"$match": {"campaign_id": campaign_id}},
        {"$group": {"_id": {"status": "$status", "reason": "$stopped_reason"},
                    "count": {"$sum": 1}}},
    ])
    rows = await cursor.to_list(50)
    summary = {"active": 0, "completed": 0, "stopped": 0, "stopped_reasons": {}}
    for row in rows:
        status = row["_id"]["status"]
        summary[status] = summary.get(status, 0) + row["count"]
        if status == sequence_domain.STOPPED and row["_id"].get("reason"):
            summary["stopped_reasons"][row["_id"]["reason"]] = row["count"]
    return summary


# --- Messages -----------------------------------------------------------------

async def create_message(*, campaign_id: str, enrollment_id: str, lead_id: str,
                         step_index: int, to_email: str, country_code: str | None,
                         subject: str, body: str, cited_facts: list,
                         status: str, scheduled_for: str | None,
                         generation_meta: dict | None = None) -> dict:
    """Store a drafted message. The unique (enrollment, step) index makes a
    duplicate draft an error rather than a second email."""
    from pymongo.errors import DuplicateKeyError

    doc = {
        "campaign_id": campaign_id,
        "enrollment_id": enrollment_id,
        "lead_id": lead_id,
        "step_index": step_index,
        "channel": "email",
        "to_email": to_email,
        "country_code": country_code,
        "subject": subject,
        "body": body,
        "cited_facts": cited_facts,
        "status": status,
        "scheduled_for": scheduled_for,
        "identity": None,
        "provider_message_id": None,
        # Threading identity, minted at dispatch (the sending identity, and so
        # the Message-ID domain, is not known until pre-flight picks one).
        "email_message_id": None,
        "in_reply_to": None,
        "references": [],
        "simulated": False,
        "sent_at": None,
        "error": None,
        "generation": generation_meta or {},
        "approved_by": None,
        "approved_at": None,
    }
    stamp_create(doc)
    try:
        result = await db[MESSAGES].insert_one(doc)
    except DuplicateKeyError:
        existing = await db[MESSAGES].find_one(
            {"enrollment_id": enrollment_id, "step_index": step_index}
        )
        return {**serialize_doc(existing), "duplicate": True}
    return {**serialize_doc(await db[MESSAGES].find_one({"_id": result.inserted_id})),
            "duplicate": False}


async def get_message(message_id: str) -> dict:
    doc = await db[MESSAGES].find_one({"_id": object_id(message_id, "message id")})
    if not doc:
        raise NotFoundError("Message not found")
    return serialize_doc(doc)


async def message_for_step(enrollment_id: str, step_index: int) -> dict | None:
    doc = await db[MESSAGES].find_one(
        {"enrollment_id": enrollment_id, "step_index": step_index}
    )
    return serialize_doc(doc)


async def list_messages(*, campaign_id: str | None = None, status: str | None = None,
                        limit: int = 50, cursor: str | None = None) -> dict:
    query = {}
    if campaign_id:
        query["campaign_id"] = campaign_id
    if status:
        query["status"] = status
    return await paginate(MESSAGES, query, sort=("created_at", -1),
                          limit=limit, cursor=cursor)


async def update_message(message_id: str, patch: dict) -> dict:
    await db[MESSAGES].update_one(
        {"_id": object_id(message_id, "message id")},
        {"$set": stamp_update(patch)},
    )
    return await get_message(message_id)


async def claim_message_for_send(message_id: str) -> dict | None:
    """Atomically move approved -> sending. The double-send guard.

    Only a message in `approved` can be claimed; a retry that arrives after a
    crash finds `sending` and backs off to needs_review handling instead of
    calling the provider again. find_one_and_update makes the claim itself
    race-proof.
    """
    doc = await db[MESSAGES].find_one_and_update(
        {"_id": object_id(message_id, "message id"), "status": "approved"},
        {"$set": {"status": "sending", "updated_at": now_iso()}},
        return_document=True,
    )
    return serialize_doc(doc)


async def approved_due_messages(*, now: str | None = None, limit: int = 100) -> list:
    """Approved messages whose send time has arrived - the tick's send sweep."""
    query = {
        "status": "approved",
        "$or": [
            {"scheduled_for": None},
            {"scheduled_for": {"$lte": now or now_iso()}},
        ],
    }
    docs = await db[MESSAGES].find(query).sort("scheduled_for", 1).to_list(limit)
    return serialize_list(docs)


async def threading_ancestor(enrollment_id: str, step_index: int) -> dict | None:
    """The most recent earlier step in this enrollment that actually went out.

    The parent of a follow-up is the last message the recipient could have
    seen - so `sent` only. A cancelled or rejected draft never reached them,
    and threading under it would reference an id their client has no record
    of, which some clients render as a broken orphan thread. Simulated sends
    are excluded for exactly the same reason: they are marked `sent`, but no
    mail ever left the building.
    """
    doc = await db[MESSAGES].find_one(
        {
            "enrollment_id": enrollment_id,
            "step_index": {"$lt": step_index},
            "status": "sent",
            "simulated": {"$ne": True},
            "email_message_id": {"$ne": None},
        },
        sort=[("step_index", -1)],
    )
    return serialize_doc(doc)


async def find_by_email_message_id(email_message_id: str) -> dict | None:
    """Match an inbound reply's In-Reply-To/References back to what we sent."""
    if not email_message_id:
        return None
    doc = await db[MESSAGES].find_one({"email_message_id": email_message_id})
    return serialize_doc(doc)


async def find_by_provider_id(provider_message_id: str) -> dict | None:
    if not provider_message_id:
        return None
    doc = await db[MESSAGES].find_one({"provider_message_id": provider_message_id})
    return serialize_doc(doc)

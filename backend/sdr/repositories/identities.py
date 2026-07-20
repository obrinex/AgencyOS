"""Sending identities: mailboxes, their DNS state, warm-up and rate limits.

An identity is a from-address we can send as. It carries the DNS verification
result, where it is in warm-up, its measured bounce and complaint rates, and
its daily allowance.

The rate limiter here is a Mongo counter claimed with a single atomic
`$inc`, not a read-then-write. Under concurrent drains a read-modify-write
races and lets both callers through, which on a warm-up-capped identity means
sending double the allowance on the day it matters most.
"""

from datetime import datetime, timedelta, timezone

from database import db, now_iso, serialize_doc, serialize_list
from sdr.collections import SEND_COUNTERS, SENDING_IDENTITIES
from sdr.domain import warmup
from sdr.domain.normalize import normalize_email
from sdr.errors import NotFoundError, ValidationError
from sdr.repositories.base import object_id, stamp_create, stamp_update

#: Counters expire well after the day they cover; they exist for rate limiting,
#: not analytics, and unbounded growth on a hot collection is its own problem.
COUNTER_RETENTION_DAYS = 7


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _this_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def create_identity(*, identity: str, channel: str = "email",
                          label: str | None = None, daily_cap_target: int = 200,
                          dkim_selector: str | None = None,
                          user_id: str | None = None) -> dict:
    """Register a from-address. Starts paused with no DNS verification.

    Nothing can send from it until DNS passes and it is explicitly activated -
    creating an identity must never be enough to start sending.
    """
    from pymongo.errors import DuplicateKeyError

    normalized = normalize_email(identity) if channel == "email" else identity.strip()
    if not normalized:
        raise ValidationError(f"'{identity}' is not a valid {channel} identity.")

    domain = normalized.split("@")[-1] if "@" in normalized else None

    # Explicit check as well as the unique index. The index is the race
    # backstop, but relying on it alone means the failure only ever appears
    # in an environment where create_indexes() has run - and produces a
    # DuplicateKeyError rather than something an operator can read.
    if await db[SENDING_IDENTITIES].find_one({"identity": normalized}):
        raise ValidationError(f"'{normalized}' is already registered.")

    doc = {
        "identity": normalized,
        "channel": channel,
        "label": label or normalized,
        "domain": domain,
        "dkim_selector": dkim_selector,
        "dns_status": None,
        "dns_checked_at": None,
        "status": warmup.PAUSED,
        "status_reason": "Newly created - verify DNS and activate before sending",
        "warmup_started_at": None,
        "daily_cap_target": max(1, int(daily_cap_target)),
        "sent_7d": 0,
        "bounces_7d": 0,
        "complaints_7d": 0,
        "reputation_score": 1.0,
        "created_by": user_id,
    }
    stamp_create(doc)
    try:
        result = await db[SENDING_IDENTITIES].insert_one(doc)
    except DuplicateKeyError:
        raise ValidationError(f"'{normalized}' is already registered.")
    return serialize_doc(await db[SENDING_IDENTITIES].find_one({"_id": result.inserted_id}))


async def get_identity(identity_id: str) -> dict:
    doc = await db[SENDING_IDENTITIES].find_one(
        {"_id": object_id(identity_id, "identity id")}
    )
    if not doc:
        raise NotFoundError("Sending identity not found")
    return _decorate(serialize_doc(doc))


async def list_identities(channel: str | None = None) -> list:
    query = {"channel": channel} if channel else {}
    docs = await db[SENDING_IDENTITIES].find(query).sort("created_at", 1).to_list(100)
    return [_decorate(row) for row in serialize_list(docs)]


def _decorate(row: dict) -> dict:
    """Add derived warm-up figures. Computed, never stored - a stored cap goes
    stale the moment the clock rolls over."""
    day_index = _warmup_day_index(row.get("warmup_started_at"))
    target = row.get("daily_cap_target", 0)
    row["warmup_day"] = day_index
    row["daily_cap_current"] = warmup.effective_cap(
        day_index=day_index, target=target, status=row.get("status", warmup.PAUSED)
    )
    row["is_warmed"] = warmup.is_warmed(day_index, target)
    return row


def _warmup_day_index(started_at: str | None) -> int:
    if not started_at:
        return 0
    try:
        started = datetime.fromisoformat(started_at)
    except (TypeError, ValueError):
        return 0
    return max(0, (datetime.now(timezone.utc) - started).days)


async def update_dns(identity_id: str, dns_result: dict) -> dict:
    await db[SENDING_IDENTITIES].update_one(
        {"_id": object_id(identity_id, "identity id")},
        {"$set": stamp_update({
            "dns_status": dns_result,
            "dns_checked_at": now_iso(),
        })},
    )
    return await get_identity(identity_id)


async def activate(identity_id: str) -> dict:
    """Begin warm-up. Refuses unless DNS passes.

    This is the gate that stops an unverified domain ever sending. Sending
    without SPF/DKIM/DMARC lands in spam and the reputation damage outlasts
    the campaign.
    """
    from sdr.services import dns_check

    row = await get_identity(identity_id)
    ok, reason = dns_check.ready_to_send(row.get("dns_status"))
    if not ok:
        raise ValidationError(f"Cannot activate: {reason}")

    patch = {
        "status": warmup.WARMING,
        "status_reason": "Warm-up started",
    }
    if not row.get("warmup_started_at"):
        patch["warmup_started_at"] = now_iso()

    await db[SENDING_IDENTITIES].update_one(
        {"_id": object_id(identity_id, "identity id")}, {"$set": stamp_update(patch)}
    )
    return await get_identity(identity_id)


async def pause(identity_id: str, reason: str = "Paused manually") -> dict:
    await db[SENDING_IDENTITIES].update_one(
        {"_id": object_id(identity_id, "identity id")},
        {"$set": stamp_update({"status": warmup.PAUSED, "status_reason": reason})},
    )
    return await get_identity(identity_id)


async def record_outcome(identity: str, *, sent: int = 0, bounced: int = 0,
                         complained: int = 0) -> dict | None:
    """Fold a send result into the identity's rolling counters, then re-evaluate.

    Health is recomputed on every outcome rather than on a schedule, so a
    bounce spike throttles the identity within one message instead of within
    a day.
    """
    normalized = normalize_email(identity) or identity
    doc = await db[SENDING_IDENTITIES].find_one({"identity": normalized})
    if not doc:
        return None

    await db[SENDING_IDENTITIES].update_one(
        {"_id": doc["_id"]},
        {"$inc": {"sent_7d": sent, "bounces_7d": bounced, "complaints_7d": complained}},
    )

    updated = await db[SENDING_IDENTITIES].find_one({"_id": doc["_id"]})
    status, reason = warmup.evaluate_health(
        sent_7d=updated.get("sent_7d", 0),
        bounces_7d=updated.get("bounces_7d", 0),
        complaints_7d=updated.get("complaints_7d", 0),
        current_status=updated.get("status", warmup.WARMING),
    )
    score = warmup.reputation_score(
        sent_7d=updated.get("sent_7d", 0),
        bounces_7d=updated.get("bounces_7d", 0),
        complaints_7d=updated.get("complaints_7d", 0),
    )
    await db[SENDING_IDENTITIES].update_one(
        {"_id": doc["_id"]},
        {"$set": stamp_update({
            "status": status, "status_reason": reason, "reputation_score": score,
        })},
    )
    return _decorate(serialize_doc(await db[SENDING_IDENTITIES].find_one({"_id": doc["_id"]})))


# --- Rate limiting ------------------------------------------------------------

async def claim_send_slot(*, identity: str, recipient_domain: str,
                          identity_cap: int, domain_cap: int) -> tuple:
    """Atomically claim one send against both caps. Returns (ok, reason).

    Claim-then-check rather than check-then-claim: `$inc` with `upsert` is
    atomic, so two concurrent drains cannot both see 199 of 200 and both
    proceed. If the claim overshoots we roll it back, which is safe because
    the counter is only ever compared against a cap.
    """
    day = _today()
    expires = datetime.now(timezone.utc) + timedelta(days=COUNTER_RETENTION_DAYS)

    identity_count = await _increment("identity", identity, day, expires)
    if identity_count > identity_cap:
        await _increment("identity", identity, day, expires, delta=-1)
        return False, (
            f"Daily cap reached for {identity} ({identity_cap} today). "
            "Warm-up raises this over time."
        )

    domain_count = await _increment("recipient_domain", recipient_domain, day, expires)
    if domain_count > domain_cap:
        # Release the identity slot too, or a domain-capped send silently
        # consumes the identity's allowance for the day.
        await _increment("recipient_domain", recipient_domain, day, expires, delta=-1)
        await _increment("identity", identity, day, expires, delta=-1)
        return False, (
            f"Daily cap reached for recipients at {recipient_domain} "
            f"({domain_cap} today)."
        )

    return True, "Slot claimed"


async def _increment(scope: str, key: str, day: str, expires, delta: int = 1) -> int:
    from pymongo import ReturnDocument

    doc = await db[SEND_COUNTERS].find_one_and_update(
        {"scope": scope, "key": key, "day": day},
        {"$inc": {"count": delta}, "$setOnInsert": {"expires_at": expires}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc.get("count", 0)


async def claim_scoped_slot(scope: str, key: str, cap: int) -> tuple:
    """Atomically claim one slot against an arbitrary day-scoped counter.

    Public sibling of the send-slot claim, for callers with their own caps -
    the campaign tick uses scope "new_leads" to pace how many fresh leads
    start a sequence each day. Same claim-then-rollback shape, so two
    concurrent ticks cannot both squeeze past the cap.
    """
    day = _today()
    expires = datetime.now(timezone.utc) + timedelta(days=COUNTER_RETENTION_DAYS)
    count = await _increment(scope, key, day, expires)
    if count > cap:
        await _increment(scope, key, day, expires, delta=-1)
        return False, f"Daily {scope} cap of {cap} reached."
    return True, f"{count}/{cap} today"


async def release_scoped_slot(scope: str, key: str) -> None:
    """Hand back a scoped slot claimed for work that turned out not to exist."""
    day = _today()
    expires = datetime.now(timezone.utc) + timedelta(days=COUNTER_RETENTION_DAYS)
    await _increment(scope, key, day, expires, delta=-1)


async def scoped_usage_today(scope: str, key: str) -> int:
    doc = await db[SEND_COUNTERS].find_one({"scope": scope, "key": key, "day": _today()})
    return doc.get("count", 0) if doc else 0


async def usage_today(identity: str) -> int:
    doc = await db[SEND_COUNTERS].find_one(
        {"scope": "identity", "key": identity, "day": _today()}
    )
    return doc.get("count", 0) if doc else 0


async def org_usage_today() -> int:
    """Total sends today across every identity."""
    cursor = db[SEND_COUNTERS].aggregate([
        {"$match": {"scope": "identity", "day": _today()}},
        {"$group": {"_id": None, "total": {"$sum": "$count"}}},
    ])
    rows = await cursor.to_list(1)
    return rows[0]["total"] if rows else 0


async def org_usage_this_month() -> int:
    """Total sends this calendar month, against the provider's monthly quota.

    Counted from a separate month-scoped counter rather than summing daily
    rows, because daily counters expire after a week - summing them would
    silently under-report and let the monthly cap be blown.
    """
    doc = await db[SEND_COUNTERS].find_one(
        {"scope": "org_month", "key": "all", "day": _this_month()}
    )
    return doc.get("count", 0) if doc else 0


async def claim_monthly_slot(monthly_cap: int | None) -> tuple:
    """Atomically claim against the monthly quota. Returns (ok, reason).

    Kept separate from the daily claim so it can be released independently
    when a later check refuses the send.
    """
    if not monthly_cap:
        return True, "No monthly cap configured"

    # Month counters live longer than daily ones - they must survive the whole
    # month they cover, plus a margin for reporting.
    expires = datetime.now(timezone.utc) + timedelta(days=70)
    count = await _increment("org_month", "all", _this_month(), expires)
    if count > monthly_cap:
        await _increment("org_month", "all", _this_month(), expires, delta=-1)
        return False, (
            f"Monthly send quota reached ({monthly_cap:,} emails). "
            "It resets at the start of next month, or raise the plan limit."
        )
    return True, "Monthly slot claimed"


async def release_monthly_slot() -> None:
    expires = datetime.now(timezone.utc) + timedelta(days=70)
    await _increment("org_month", "all", _this_month(), expires, delta=-1)


async def pick_identity(channel: str = "email") -> dict | None:
    """Choose a healthy identity with allowance remaining.

    Prefers the one with the most headroom, which spreads volume rather than
    exhausting one mailbox before touching the next - concentrated sending is
    itself a spam signal.
    """
    candidates = []
    for row in await list_identities(channel):
        if row["status"] in (warmup.PAUSED, warmup.BLOCKED):
            continue
        if row["daily_cap_current"] <= 0:
            continue
        used = await usage_today(row["identity"])
        headroom = row["daily_cap_current"] - used
        if headroom > 0:
            candidates.append((headroom, row))

    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]

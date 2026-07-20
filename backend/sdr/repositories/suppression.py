"""Suppression list and consent records.

The suppression list is the most consequential collection in the module. An
entry here means "never contact this address again, on any channel, in any
campaign, permanently". Getting a lookup wrong sends mail to someone who
explicitly asked us to stop, which is both a legal problem and the fastest
route to a spam complaint.

Three properties it must have, and does:

1. **Checked before every send**, never cached. Vercel invocations share no
   memory, so a cached list would go stale silently.
2. **Matched at both address and domain level.** Unsubscribing one person does
   not suppress their colleagues, but a domain-level entry ("stop emailing
   anyone at this company") does.
3. **Idempotent.** Unsubscribing twice is not an error - the unique index
   makes a duplicate a no-op rather than a 500 on a public endpoint.
"""

import hashlib
import hmac
import os

from database import db, now_iso, serialize_doc, serialize_list
from sdr.collections import CONSENT, SUPPRESSION
from sdr.domain.normalize import normalize_domain, normalize_email
from sdr.repositories.base import paginate

EMAIL = "email"
DOMAIN = "domain"
PHONE = "phone"

REASONS = (
    "unsubscribe", "bounce", "complaint", "manual",
    "legal", "competitor", "existing_client",
)


async def suppress(*, value: str, value_type: str = EMAIL, reason: str = "manual",
                   source: str | None = None, added_by: str | None = None) -> dict:
    """Add an entry. Idempotent - re-suppressing returns the existing row."""
    from pymongo.errors import DuplicateKeyError

    normalized = _normalize(value, value_type)
    if not normalized:
        from sdr.errors import ValidationError
        raise ValidationError(f"'{value}' is not a valid {value_type}.")

    doc = {
        "value_type": value_type,
        "value_normalized": normalized,
        "value_original": value,
        "reason": reason if reason in REASONS else "manual",
        "source": source,
        "added_by": added_by,
        "created_at": now_iso(),
    }
    try:
        await db[SUPPRESSION].insert_one(doc)
    except DuplicateKeyError:
        pass
    return serialize_doc(await db[SUPPRESSION].find_one({
        "value_type": value_type, "value_normalized": normalized
    }))


def _normalize(value: str, value_type: str) -> str | None:
    if value_type == EMAIL:
        return normalize_email(value)
    if value_type == DOMAIN:
        return normalize_domain(value)
    if value_type == PHONE:
        return (value or "").strip() or None
    return (value or "").strip().lower() or None


async def is_suppressed(*, email: str | None = None, domain: str | None = None,
                        phone: str | None = None) -> dict | None:
    """The hot-path check. Returns the matching entry, or None.

    An email implies its domain, so both are checked in one query - a
    domain-level suppression must catch every address at that company.
    """
    conditions = []

    normalized_email = normalize_email(email)
    if normalized_email:
        conditions.append({"value_type": EMAIL, "value_normalized": normalized_email})
        implied = normalized_email.split("@")[-1]
        if implied:
            conditions.append({"value_type": DOMAIN, "value_normalized": implied})

    normalized_domain = normalize_domain(domain)
    if normalized_domain:
        conditions.append({"value_type": DOMAIN, "value_normalized": normalized_domain})

    if phone:
        conditions.append({"value_type": PHONE, "value_normalized": phone.strip()})

    if not conditions:
        return None
    return serialize_doc(await db[SUPPRESSION].find_one({"$or": conditions}))


async def unsuppress(value: str, value_type: str = EMAIL) -> bool:
    """Remove an entry. Admin-only upstream.

    Deliberately possible - a bounce from a temporarily-down mail server
    should not blocklist a real prospect forever - but every removal is
    audited by the caller.
    """
    normalized = _normalize(value, value_type)
    if not normalized:
        return False
    result = await db[SUPPRESSION].delete_one({
        "value_type": value_type, "value_normalized": normalized
    })
    return result.deleted_count > 0


async def list_suppressions(*, value_type: str | None = None,
                            reason: str | None = None,
                            search: str | None = None,
                            limit: int = 50, cursor: str | None = None) -> dict:
    query = {}
    if value_type:
        query["value_type"] = value_type
    if reason:
        query["reason"] = reason
    if search:
        query["value_normalized"] = {"$regex": search, "$options": "i"}
    return await paginate(SUPPRESSION, query, sort=("created_at", -1),
                          limit=limit, cursor=cursor)


async def counts_by_reason() -> list:
    cursor = db[SUPPRESSION].aggregate([
        {"$group": {"_id": "$reason", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ])
    rows = await cursor.to_list(20)
    return [{"reason": row["_id"], "count": row["count"]} for row in rows]


# --- Consent audit trail ------------------------------------------------------

async def record_consent(*, action: str, value: str, contact_id: str | None = None,
                         channel: str = "email", legal_basis: str | None = None,
                         ip: str | None = None, user_agent: str | None = None,
                         evidence: dict | None = None) -> dict:
    """Append to the consent trail.

    Required by DPDP and GDPR: on request we must be able to show when and how
    someone opted out, not merely that they are on a list now. Append-only for
    that reason - these rows are never updated or deleted.
    """
    doc = {
        "action": action,
        "value_normalized": normalize_email(value) or (value or "").strip().lower(),
        "contact_id": contact_id,
        "channel": channel,
        "legal_basis": legal_basis,
        "ip": ip,
        "user_agent": (user_agent or "")[:300] or None,
        "evidence": evidence or {},
        "created_at": now_iso(),
    }
    result = await db[CONSENT].insert_one(doc)
    return serialize_doc(await db[CONSENT].find_one({"_id": result.inserted_id}))


async def consent_history(value: str) -> list:
    normalized = normalize_email(value) or (value or "").strip().lower()
    docs = await db[CONSENT].find({"value_normalized": normalized}) \
        .sort("created_at", -1).to_list(100)
    return serialize_list(docs)


# --- One-click unsubscribe tokens ---------------------------------------------

def _secret() -> bytes:
    """Signing key for unsubscribe links.

    Reuses JWT_SECRET, which `server.validate_environment()` already requires
    and enforces a minimum length on in production - rather than introducing
    another secret to rotate.
    """
    return os.environ.get("JWT_SECRET", "").encode("utf-8")


def unsubscribe_token(email: str) -> str:
    """Signed, stateless token for the List-Unsubscribe URL.

    Stateless so the link keeps working regardless of database state, and
    signed so it cannot be used to suppress an arbitrary third party by
    editing the address in the URL.
    """
    normalized = normalize_email(email) or ""
    digest = hmac.new(_secret(), normalized.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:32]


def verify_unsubscribe_token(email: str, token: str) -> bool:
    return hmac.compare_digest(unsubscribe_token(email), (token or "").strip())

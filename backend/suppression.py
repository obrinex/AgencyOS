"""The never-contact list and its consent trail.

Extracted from the deleted AI SDR module so that removing the agent system did
not also remove the ability to honour an opt-out.

## Why this survived the removal

Emails already delivered carry a `List-Unsubscribe` header and a footer link
pointing at `/api/public/sdr/unsubscribe?email=...&token=...`. Those messages
are in real inboxes and cannot be recalled. Deleting the code behind that URL
would have turned every one of those links into a 404 - which is a legal
problem under DPDP and GDPR, not merely a broken page.

Three things are preserved exactly, and none of them may drift:

1. **The collection names.** `sdr_suppression` and `sdr_consent_records` are
   kept verbatim. Renaming them would leave every existing opt-out row
   unreadable, which in practice means resurrecting people who already asked
   not to be contacted.

2. **The token derivation.** An unchanged HMAC-SHA256 of the normalised
   address under `JWT_SECRET`, truncated to 32 hex characters. Stateless by
   design, so a link keeps working regardless of database state - and so a
   token minted by the old module still verifies here.

3. **The URL path.** `routers/public.py` still serves `/api/public/sdr/...`
   despite there no longer being an SDR module. The path is part of the
   contract with mail that has already been sent; it is not ours to tidy.

The old module also recorded bounces and complaints from the Resend webhook.
That webhook went with the campaign engine, so those paths no longer feed this
list - a hard bounce will not auto-suppress until a new sending system is
built. Worth knowing before the replacement starts sending.
"""

import hashlib
import hmac
import os
import re
from datetime import datetime, timezone

from database import db, serialize_doc, serialize_list

#: Unchanged from the SDR module. See point 1 above.
SUPPRESSION = "sdr_suppression"
CONSENT = "sdr_consent_records"

EMAIL = "email"
DOMAIN = "domain"
PHONE = "phone"

REASONS = ("unsubscribed", "bounced", "complained", "manual", "legal")


def normalize_email(value: str | None) -> str | None:
    """Lowercase and trim. Does not validate deliverability."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
        return None
    return text


# --- One-click unsubscribe tokens ---------------------------------------------

def _secret() -> bytes:
    """Signing key. Reuses JWT_SECRET, which `server.validate_environment()`
    already requires and length-checks in production."""
    return os.environ.get("JWT_SECRET", "").encode("utf-8")


def unsubscribe_token(email: str) -> str:
    """Signed, stateless token for the List-Unsubscribe URL.

    Signed so the address in the URL cannot be edited to suppress an arbitrary
    third party.
    """
    normalized = normalize_email(email) or ""
    digest = hmac.new(_secret(), normalized.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:32]


def verify_unsubscribe_token(email: str, token: str) -> bool:
    return hmac.compare_digest(unsubscribe_token(email), (token or "").strip())


# --- The list -----------------------------------------------------------------

async def suppress(*, value: str, value_type: str = EMAIL, reason: str = "manual",
                   source: str | None = None, added_by: str | None = None) -> dict | None:
    """Add an entry. Idempotent - re-suppressing returns the existing row."""
    from pymongo.errors import DuplicateKeyError

    normalized = normalize_email(value) if value_type == EMAIL else (value or "").strip().lower()
    if not normalized:
        return None

    doc = {
        "value_type": value_type,
        "value_normalized": normalized,
        "value_original": value,
        "reason": reason if reason in REASONS else "manual",
        "source": source,
        "added_by": added_by,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db[SUPPRESSION].insert_one(doc)
    except DuplicateKeyError:
        pass
    return serialize_doc(await db[SUPPRESSION].find_one({
        "value_type": value_type, "value_normalized": normalized,
    }))


async def is_suppressed(*, email: str | None = None) -> dict | None:
    """The check to run before sending anything to an address.

    An email implies its domain, so both are checked - a domain-level
    suppression must catch every address at that company.
    """
    conditions = []
    normalized = normalize_email(email)
    if normalized:
        conditions.append({"value_type": EMAIL, "value_normalized": normalized})
        implied = normalized.split("@")[-1]
        if implied:
            conditions.append({"value_type": DOMAIN, "value_normalized": implied})
    if not conditions:
        return None
    return serialize_doc(await db[SUPPRESSION].find_one({"$or": conditions}))


async def record_consent(*, action: str, value: str, channel: str = "email",
                         legal_basis: str | None = None, ip: str | None = None,
                         user_agent: str | None = None,
                         evidence: dict | None = None) -> dict:
    """Append to the consent trail.

    Required by DPDP and GDPR: on request we must be able to show when and how
    someone opted out, not merely that they are on a list now. Append-only for
    that reason - these rows are never updated or deleted.
    """
    doc = {
        "action": action,
        "value_normalized": normalize_email(value) or (value or "").strip().lower(),
        "channel": channel,
        "legal_basis": legal_basis,
        "ip": ip,
        "user_agent": (user_agent or "")[:300] or None,
        "evidence": evidence or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[CONSENT].insert_one(doc)
    return serialize_doc(doc)


async def consent_history(value: str) -> list:
    normalized = normalize_email(value) or (value or "").strip().lower()
    docs = await db[CONSENT].find({"value_normalized": normalized}) \
        .sort("created_at", -1).to_list(100)
    return serialize_list(docs)


async def create_suppression_indexes() -> None:
    """Called from `database.create_indexes()`. Idempotent.

    Unique on (type, value) - it is what makes `suppress()` safe to call twice
    and stops duplicate opt-out rows for one address.
    """
    import logging

    try:
        await db[SUPPRESSION].create_index(
            [("value_type", 1), ("value_normalized", 1)], unique=True)
        await db[CONSENT].create_index("value_normalized")
    except Exception as exc:
        logging.getLogger(__name__).error(
            "Could not create suppression indexes: %s", exc)

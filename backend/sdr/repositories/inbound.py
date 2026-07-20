"""Stored inbound replies.

Every reply is persisted before it is acted on, even the ones we cannot match
and the ones that turn out to be machines. Two reasons: an unmatched reply is
a real person waiting on a human, so it has to be visible somewhere rather
than dropped with a 200; and when the classifier gets one wrong, the raw
message is the only way to find out how.

`ingest_key` is the double-process guard. Webhook providers retry, and
processing one reply twice would stop an enrollment, then try to stop it
again — harmless today, but the same path also suppresses addresses and
stamps leads, and those should happen exactly once.
"""

from database import db, now_iso, serialize_doc
from sdr.collections import INBOUND, MESSAGES
from sdr.errors import NotFoundError
from sdr.repositories.base import object_id, paginate, stamp_create, stamp_update


async def record(*, ingest_key: str, from_email: str, to_email: str,
                 subject: str, text_body: str, headers: dict,
                 in_reply_to: str | None, references: str | None,
                 provider: str, received_at: str | None = None) -> dict:
    """Store one inbound message. Returns {..., "duplicate": bool}.

    A duplicate `ingest_key` returns the existing row rather than raising:
    a provider retrying a webhook it already delivered is normal traffic, not
    an error, and the caller decides to skip re-processing on that flag.

    Checked explicitly *before* the insert rather than relying on the unique
    index alone. Index creation in this module is deliberately non-fatal
    (`_safe_index`, after the outage that took production down), which means
    the index may legitimately be absent - so nothing that must be correct can
    depend on it. The index is the backstop for the concurrent race, caught
    below; this query is the actual guard.
    """
    from pymongo.errors import DuplicateKeyError

    if ingest_key:
        existing = await db[INBOUND].find_one({"ingest_key": ingest_key})
        if existing:
            return {**serialize_doc(existing), "duplicate": True}

    doc = {
        "ingest_key": ingest_key,
        "provider": provider,
        "from_email": (from_email or "").strip().lower(),
        "to_email": (to_email or "").strip().lower(),
        "subject": subject or "",
        "text_body": text_body or "",
        "headers": headers or {},
        "in_reply_to": in_reply_to,
        "references": references,
        "received_at": received_at or now_iso(),
        # Filled in by the service once matching and classification run.
        "message_id": None,
        "enrollment_id": None,
        "campaign_id": None,
        "lead_id": None,
        "match_method": None,       # threaded | sender | none
        "category": None,
        "category_confidence": None,
        "category_source": None,    # headers | classifier
        "action_taken": None,
        "needs_human": False,
        "processed_at": None,
    }
    stamp_create(doc)
    try:
        result = await db[INBOUND].insert_one(doc)
    except DuplicateKeyError:
        existing = await db[INBOUND].find_one({"ingest_key": ingest_key})
        return {**serialize_doc(existing), "duplicate": True}
    return {**serialize_doc(await db[INBOUND].find_one({"_id": result.inserted_id})),
            "duplicate": False}


async def get(inbound_id: str) -> dict:
    doc = await db[INBOUND].find_one({"_id": object_id(inbound_id, "inbound id")})
    if not doc:
        raise NotFoundError("Inbound message not found")
    return serialize_doc(doc)


async def update(inbound_id: str, patch: dict) -> dict:
    await db[INBOUND].update_one(
        {"_id": object_id(inbound_id, "inbound id")},
        {"$set": stamp_update(patch)},
    )
    return await get(inbound_id)


async def list_inbound(*, category: str | None = None, lead_id: str | None = None,
                       needs_human: bool | None = None,
                       limit: int = 50, cursor: str | None = None) -> dict:
    query = {}
    if category:
        query["category"] = category
    if lead_id:
        query["lead_id"] = lead_id
    if needs_human is not None:
        query["needs_human"] = needs_human
    return await paginate(INBOUND, query, sort=("received_at", -1),
                          limit=limit, cursor=cursor)


async def latest_message_to(email: str) -> dict | None:
    """The most recent thing we actually sent to this address.

    The fallback when a reply carries no usable threading headers. Weaker than
    a Message-ID match by design — it cannot tell two campaigns apart — so the
    service marks anything matched this way for human eyes.
    """
    if not email:
        return None
    doc = await db[MESSAGES].find_one(
        {
            "to_email": email.strip().lower(),
            "status": {"$in": ["sent", "delivered"]},
            "simulated": {"$ne": True},
        },
        sort=[("sent_at", -1)],
    )
    return serialize_doc(doc)


async def count_unmatched() -> int:
    """Replies nobody could route — surfaced on the dashboard, because each
    one is a person who answered and has not been answered back."""
    return await db[INBOUND].count_documents({"match_method": "none"})

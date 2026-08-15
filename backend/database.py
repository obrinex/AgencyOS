import os
from datetime import datetime, timezone
from bson import ObjectId
from bson.decimal128 import Decimal128
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value):
    """Recursively convert BSON/Mongo types into JSON-encodable values.

    Top-level fields were always fine, but nested dicts/lists (e.g. the
    `before`/`after` snapshots on audit rows, which agents write straight from a
    just-inserted doc) can hide an ObjectId or datetime that FastAPI's encoder
    chokes on and 500s. Recursing here keeps the read path from ever crashing on
    a nested BSON value, and repairs already-stored rows on the way out.
    """
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal128):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def serialize_doc(doc):
    """Convert a Mongo document (with ObjectId _id) into a JSON-safe dict with `id` field."""
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    for key, value in list(doc.items()):
        doc[key] = _json_safe(value)
    return doc


def serialize_list(docs):
    return [serialize_doc(d) for d in docs]


class InvalidIdError(ValueError):
    """A malformed ObjectId string arrived from outside.

    Subclasses `ValueError` deliberately, because that is what this used to
    raise bare. Any caller wrapping it in `except ValueError` to produce its own
    typed error keeps working unchanged - which is not hypothetical: raising
    `HTTPException` here instead broke 28 tests in a module that did exactly
    that. Keep the base class.

    Having a distinct type is what lets `server.py` map it to a 400. Nothing
    caught the bare `ValueError`, and no handler was registered for it, so
    every route taking an id answered a malformed one with a 500 Internal
    Server Error. A caller sending a bad id has made a bad request, and real
    faults were competing with typo'd URLs in the error logs. A blanket
    `ValueError` handler would have been the wrong fix: it would turn genuine
    internal bugs into 400s and hide them.
    """


def to_object_id(id_str: str) -> ObjectId:
    if not ObjectId.is_valid(id_str):
        raise InvalidIdError(f"Invalid id: {id_str!r}")
    return ObjectId(id_str)


async def create_indexes():
    await db.users.create_index("email", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.login_attempts.create_index("identifier")
    await db.leads.create_index([("company", "text"), ("email", "text")])
    await db.leads.create_index("stage")
    await db.clients.create_index("company_name")
    await db.tasks.create_index("assignee_id")
    await db.tasks.create_index("related_id")
    await db.invoices.create_index("invoice_number", unique=True)
    await db.invoices.create_index("client_id")
    await db.notifications.create_index("user_id")
    await db.notes.create_index("user_id")
    await db.google_oauth_states.create_index("expires_at", expireAfterSeconds=0)
    await db.meetings.create_index("google_event_id")
    await db.audit_logs.create_index("created_at")
    await db.counters.create_index("name", unique=True)
    await db.chat_messages.create_index([("client_id", 1), ("created_at", 1)])
    # The CRM board, the dashboard funnel and the bulk-delete preview all query
    # leads by "not deleted", so the filter needs to be indexed alongside stage.
    await db.leads.create_index([("deleted_at", 1), ("stage", 1)])

    # Deferred imports: both modules import `db` from this file.
    from rate_limit import create_rate_limit_indexes
    await create_rate_limit_indexes()

    # The never-contact list. Its indexes outlived the agent layer for the same
    # reason the collection did - see backend/suppression.py.
    from suppression import create_suppression_indexes
    await create_suppression_indexes()

    from routers.founding import create_founding_indexes
    await create_founding_indexes()


async def next_counter(name: str) -> int:
    doc = await db.counters.find_one_and_update(
        {"name": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["seq"]

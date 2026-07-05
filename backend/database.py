import os
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_doc(doc):
    """Convert a Mongo document (with ObjectId _id) into a JSON-safe dict with `id` field."""
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    for key, value in list(doc.items()):
        if isinstance(value, ObjectId):
            doc[key] = str(value)
    return doc


def serialize_list(docs):
    return [serialize_doc(d) for d in docs]


def to_object_id(id_str: str) -> ObjectId:
    if not ObjectId.is_valid(id_str):
        raise ValueError("Invalid id")
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
    await db.audit_logs.create_index("created_at")
    await db.counters.create_index("name", unique=True)


async def next_counter(name: str) -> int:
    doc = await db.counters.find_one_and_update(
        {"name": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["seq"]

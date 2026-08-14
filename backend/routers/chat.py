"""Client ↔ team chat.

One thread per client, spanning all their projects. Both the team (staff) and
the client's portal user post here; attachments reuse the existing files system
(`db.files`), so nothing new is forked for storage.

Messages live in `chat_messages`, keyed by `client_id`. There's no separate
thread document: one thread per client means the client id *is* the thread.

This was previously the surface for the per-client manager agent - draft-for-
review and fully autonomous reply modes. That agent was removed along with the
rest of the agent layer, so what remains is human-to-human. `AGENT` stays as a
sender type because messages it already posted are still in the collection and
must keep rendering; nothing writes it now. A replacement agent can post here
by reusing `_post_message` with `sender_type=AGENT` - the data model never
needed to change for it.
"""
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_utils import require_staff, require_client, require_admin, log_audit
from database import db, serialize_doc, serialize_list, to_object_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

STAFF, CLIENT, AGENT = "staff", "client", "agent"


class ChatMessageCreate(BaseModel):
    body: str = Field(default="", max_length=10000)
    attachment_file_ids: List[str] = Field(default_factory=list, max_length=10)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _resolve_attachments(file_ids: List[str]) -> list:
    """Turn uploaded-file ids into lightweight attachment records the message
    carries inline. Files are uploaded via the existing /api/files/upload."""
    out = []
    for fid in file_ids[:10]:
        try:
            f = await db.files.find_one({"_id": to_object_id(fid)})
        except Exception:
            f = None
        if f:
            out.append({
                "file_id": str(f["_id"]),
                "filename": f.get("filename") or f.get("name") or f.get("original_filename") or "file",
                "size": f.get("size"),
            })
    return out


async def _post_message(*, client_id: str, sender_type: str, sender_id: str,
                        sender_name: str, body: str, file_ids: List[str]) -> dict:
    attachments = await _resolve_attachments(file_ids)
    if not (body or "").strip() and not attachments:
        raise HTTPException(status_code=400, detail="Message needs text or an attachment")

    doc = {
        "client_id": client_id,
        "sender_type": sender_type,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "body": (body or "").strip(),
        "attachments": attachments,
        "created_at": _now(),
        # A message is unread by the side that did NOT send it.
        "read_by_staff": sender_type == STAFF,
        "read_by_client": sender_type == CLIENT,
    }
    res = await db.chat_messages.insert_one(doc)
    return serialize_doc(await db.chat_messages.find_one({"_id": res.inserted_id}))


async def _notify(user_ids: list, *, title: str, message: str, link: str) -> None:
    now = _now()
    for uid in user_ids:
        if uid:
            await db.notifications.insert_one({
                "user_id": str(uid), "type": "chat_message", "title": title,
                "message": message[:200], "link": link, "read": False,
                "created_at": now,
            })


# ---------------- Staff side ----------------

@router.get("/chat/threads")
async def list_threads(user: dict = Depends(require_staff)):
    """Inbox: every client with a conversation, newest first, with unread count."""
    pipeline = [
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$client_id",
            "last_message": {"$first": "$body"},
            "last_at": {"$first": "$created_at"},
            "last_sender": {"$first": "$sender_type"},
            "unread": {"$sum": {"$cond": [
                {"$and": [{"$eq": ["$read_by_staff", False]},
                          {"$ne": ["$sender_type", STAFF]}]}, 1, 0]}},
        }},
        {"$sort": {"last_at": -1}},
    ]
    threads = await db.chat_messages.aggregate(pipeline).to_list(500)
    out = []
    for t in threads:
        cid = t["_id"]
        client = None
        try:
            client = await db.clients.find_one({"_id": to_object_id(cid)})
        except Exception:
            pass
        out.append({
            "client_id": cid,
            "client_name": (client or {}).get("company_name") or "Unknown client",
            "last_message": t.get("last_message") or "(attachment)",
            "last_at": t.get("last_at"),
            "last_sender": t.get("last_sender"),
            "unread": t.get("unread", 0),
        })
    return out


@router.delete("/chat/threads/{client_id}")
async def delete_thread(client_id: str, user: dict = Depends(require_admin)):
    """Permanently delete an entire client conversation (all its messages).
    Admin only. Idempotent - deleting an empty thread is a no-op that still 200s."""
    result = await db.chat_messages.delete_many({"client_id": client_id})
    await log_audit(user["id"], "chat_thread_deleted", "client", client_id)
    return {"message": "Conversation deleted", "deleted": result.deleted_count}


@router.get("/chat/threads/{client_id}/messages")
async def staff_get_messages(client_id: str, user: dict = Depends(require_staff)):
    msgs = await db.chat_messages.find({"client_id": client_id}) \
        .sort("created_at", 1).to_list(1000)
    # Opening the thread marks the client's messages as read by staff.
    await db.chat_messages.update_many(
        {"client_id": client_id, "read_by_staff": False},
        {"$set": {"read_by_staff": True}})
    return serialize_list(msgs)


@router.post("/chat/threads/{client_id}/messages")
async def staff_post_message(client_id: str, payload: ChatMessageCreate,
                             user: dict = Depends(require_staff)):
    client = None
    try:
        client = await db.clients.find_one({"_id": to_object_id(client_id)})
    except Exception:
        pass
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    msg = await _post_message(
        client_id=client_id, sender_type=STAFF, sender_id=user["id"],
        sender_name=user.get("name") or "Team", body=payload.body,
        file_ids=payload.attachment_file_ids)

    # Notify the client's portal user, if they have one.
    if client.get("portal_user_id"):
        await _notify([client["portal_user_id"]],
                      title="New message from your team",
                      message=payload.body or "sent you a file",
                      link="/portal/chat")
    await log_audit(user["id"], "chat_message_sent", "client", client_id)
    return msg


# ---------------- Client portal side ----------------

@router.get("/portal/chat")
async def portal_get_messages(user: dict = Depends(require_client)):
    client_id = user.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="No client on this account")
    msgs = await db.chat_messages.find({"client_id": client_id}) \
        .sort("created_at", 1).to_list(1000)
    await db.chat_messages.update_many(
        {"client_id": client_id, "read_by_client": False},
        {"$set": {"read_by_client": True}})
    return serialize_list(msgs)


@router.post("/portal/chat")
async def portal_post_message(payload: ChatMessageCreate,
                              user: dict = Depends(require_client)):
    client_id = user.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="No client on this account")

    msg = await _post_message(
        client_id=client_id, sender_type=CLIENT, sender_id=user["id"],
        sender_name=user.get("name") or "Client", body=payload.body,
        file_ids=payload.attachment_file_ids)

    # Notify the team (all admins/staff) so someone picks it up.
    staff = await db.users.find({"role": {"$in": ["admin", "staff"]}}).to_list(50)
    await _notify([str(s["_id"]) for s in staff],
                  title="New client message",
                  message=payload.body or "sent a file",
                  link=f"/chat?client={client_id}")
    return msg

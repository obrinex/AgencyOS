from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user

router = APIRouter(prefix="/api/notes", tags=["notes"])

NOTE_COLORS = ["default", "amber", "green", "blue", "red", "purple"]


class NoteCreate(BaseModel):
    title: Optional[str] = ""
    content: str
    color: Optional[str] = "default"


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    color: Optional[str] = None
    pinned: Optional[bool] = None


@router.get("")
async def list_notes(user: dict = Depends(get_current_user)):
    notes = await db.notes.find({"user_id": user["id"]}).sort([("pinned", -1), ("updated_at", -1)]).to_list(500)
    return serialize_list(notes)


@router.post("")
async def create_note(payload: NoteCreate, user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    if doc.get("color") not in NOTE_COLORS:
        doc["color"] = "default"
    doc.update({"user_id": user["id"], "pinned": False, "created_at": now, "updated_at": now})
    res = await db.notes.insert_one(doc)
    note = await db.notes.find_one({"_id": res.inserted_id})
    return serialize_doc(note)


@router.put("/{note_id}")
async def update_note(note_id: str, payload: NoteUpdate, user: dict = Depends(get_current_user)):
    note = await db.notes.find_one({"_id": to_object_id(note_id), "user_id": user["id"]})
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "color" in updates and updates["color"] not in NOTE_COLORS:
        updates.pop("color")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.notes.update_one({"_id": note["_id"]}, {"$set": updates})
    updated = await db.notes.find_one({"_id": note["_id"]})
    return serialize_doc(updated)


@router.delete("/{note_id}")
async def delete_note(note_id: str, user: dict = Depends(get_current_user)):
    result = await db.notes.delete_one({"_id": to_object_id(note_id), "user_id": user["id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"message": "Note deleted"}

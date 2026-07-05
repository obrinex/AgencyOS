from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, require_staff
from automation_engine import run_meeting_automation

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


class MeetingCreate(BaseModel):
    title: str
    lead_id: Optional[str] = None
    client_id: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    location: Optional[str] = "Google Meet"
    attendees: Optional[list] = []
    notes: Optional[str] = None


class MeetingUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    ai_summary: Optional[str] = None


@router.get("")
async def list_meetings(lead_id: Optional[str] = None, client_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if lead_id:
        query["lead_id"] = lead_id
    if client_id:
        query["client_id"] = client_id
    meetings = await db.meetings.find(query).sort("start_time", 1).to_list(500)
    return serialize_list(meetings)


@router.post("")
async def create_meeting(payload: MeetingCreate, user: dict = Depends(require_staff)):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({"status": "scheduled", "ai_summary": None, "created_by": user["id"], "created_at": now})
    res = await db.meetings.insert_one(doc)
    meeting_id = str(res.inserted_id)
    doc["id"] = meeting_id
    await run_meeting_automation(doc, user["id"])
    meeting = await db.meetings.find_one({"_id": res.inserted_id})
    return serialize_doc(meeting)


@router.put("/{meeting_id}")
async def update_meeting(meeting_id: str, payload: MeetingUpdate, user: dict = Depends(require_staff)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    result = await db.meetings.update_one({"_id": to_object_id(meeting_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Meeting not found")
    meeting = await db.meetings.find_one({"_id": to_object_id(meeting_id)})
    return serialize_doc(meeting)


@router.delete("/{meeting_id}")
async def delete_meeting(meeting_id: str, user: dict = Depends(require_staff)):
    await db.meetings.delete_one({"_id": to_object_id(meeting_id)})
    return {"message": "Meeting deleted"}

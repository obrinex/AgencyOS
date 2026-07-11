import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import require_staff
from automation_engine import run_meeting_automation
import google_calendar_utils as gcal

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
    title: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    ai_summary: Optional[str] = None


async def _get_google_tokens(user_id: str):
    u = await db.users.find_one({"_id": to_object_id(user_id)})
    return (u or {}).get("google_tokens")


@router.get("")
async def list_meetings(lead_id: Optional[str] = None, client_id: Optional[str] = None, user: dict = Depends(require_staff)):
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
    doc.update({
        "status": "scheduled", "ai_summary": None, "created_by": user["id"], "created_at": now,
        "source": "internal", "google_event_id": None,
    })
    res = await db.meetings.insert_one(doc)
    doc["id"] = str(res.inserted_id)

    tokens = await _get_google_tokens(user["id"])
    if tokens:
        try:
            service = await gcal.get_calendar_service(tokens)
            created = service.events().insert(calendarId="primary", body=gcal.event_body(doc)).execute()
            await db.meetings.update_one({"_id": res.inserted_id}, {"$set": {"google_event_id": created["id"]}})
        except Exception:
            pass

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
    meeting = await db.meetings.find_one({"_id": to_object_id(meeting_id)})
    if meeting and meeting.get("google_event_id"):
        tokens = await _get_google_tokens(meeting.get("created_by") or user["id"])
        if tokens:
            try:
                service = await gcal.get_calendar_service(tokens)
                service.events().delete(calendarId="primary", eventId=meeting["google_event_id"]).execute()
            except Exception:
                pass
    await db.meetings.delete_one({"_id": to_object_id(meeting_id)})
    return {"message": "Meeting deleted"}


# ---------------- Google Calendar sync ----------------

@router.get("/google/status")
async def google_status(user: dict = Depends(require_staff)):
    tokens = await _get_google_tokens(user["id"])
    return {"configured": gcal.is_configured(), "connected": bool(tokens), "email": (tokens or {}).get("email")}


@router.get("/google/connect")
async def google_connect(user: dict = Depends(require_staff)):
    if not gcal.is_configured():
        raise HTTPException(status_code=400, detail="Google Calendar is not configured on this server")
    state = secrets.token_urlsafe(24)
    await db.google_oauth_states.insert_one({
        "state": state, "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    })
    return {"authorization_url": gcal.build_authorization_url(state)}


@router.get("/google/callback")
async def google_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    frontend = os.environ["FRONTEND_URL"]
    if error or not code or not state:
        return RedirectResponse(f"{frontend}/meetings?google=error")
    state_doc = await db.google_oauth_states.find_one({"state": state})
    if not state_doc:
        return RedirectResponse(f"{frontend}/meetings?google=error")
    await db.google_oauth_states.delete_one({"_id": state_doc["_id"]})
    try:
        tokens = gcal.exchange_code_for_tokens(code)
        tokens["email"] = gcal.get_user_email(tokens["access_token"])
        await db.users.update_one({"_id": to_object_id(state_doc["user_id"])}, {"$set": {"google_tokens": tokens}})
    except Exception:
        return RedirectResponse(f"{frontend}/meetings?google=error")
    return RedirectResponse(f"{frontend}/meetings?google=connected")


@router.post("/google/disconnect")
async def google_disconnect(user: dict = Depends(require_staff)):
    await db.users.update_one({"_id": to_object_id(user["id"])}, {"$unset": {"google_tokens": ""}})
    return {"message": "Google Calendar disconnected"}


@router.post("/google/sync")
async def google_sync(user: dict = Depends(require_staff)):
    tokens = await _get_google_tokens(user["id"])
    if not tokens:
        raise HTTPException(status_code=400, detail="Google Calendar is not connected")

    async def on_refresh(new_token):
        await db.users.update_one({"_id": to_object_id(user["id"])}, {"$set": {"google_tokens.access_token": new_token}})

    service = await gcal.get_calendar_service(tokens, on_refresh)
    now = datetime.now(timezone.utc).isoformat()
    events = service.events().list(
        calendarId="primary", timeMin=now, maxResults=100, singleEvents=True, orderBy="startTime",
    ).execute()

    synced = 0
    for ev in events.get("items", []):
        start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
        end = ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date")
        if not start:
            continue
        doc = {
            "title": ev.get("summary", "(No title)"),
            "start_time": start, "end_time": end,
            "location": ev.get("hangoutLink") or ev.get("location") or "Google Calendar",
            "notes": ev.get("description"),
            "status": "cancelled" if ev.get("status") == "cancelled" else "scheduled",
            "source": "google", "google_event_id": ev["id"],
        }
        existing = await db.meetings.find_one({"google_event_id": ev["id"]})
        if existing:
            await db.meetings.update_one({"_id": existing["_id"]}, {"$set": doc})
        else:
            doc.update({"created_by": user["id"], "created_at": datetime.now(timezone.utc).isoformat(), "attendees": [], "ai_summary": None})
            await db.meetings.insert_one(doc)
        synced += 1
    return {"synced": synced}

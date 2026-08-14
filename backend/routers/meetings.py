import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import require_staff, log_audit
from automation_engine import run_meeting_automation
from email_service import send_meeting_cancelled_email, send_meeting_rescheduled_email
import google_calendar_utils as gcal
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/meetings", tags=["meetings"])


class CancelPayload(BaseModel):
    reason: Optional[str] = None
    notify: bool = True


class ReschedulePayload(BaseModel):
    start_time: str
    end_time: Optional[str] = None
    notify: bool = True


async def _meeting_recipients(meeting: dict) -> list:
    """Everyone who should be told about a change: attendees, then the client's
    primary contact as a fallback.

    Attendees are `{name, email}` objects. A meeting with none falls back to the
    client's contact so a client meeting booked without explicit attendees still
    notifies the right person. De-duplicated by email.
    """
    seen, out = set(), []
    for a in (meeting.get("attendees") or []):
        email = (a or {}).get("email")
        if email and email.lower() not in seen:
            seen.add(email.lower())
            out.append({"name": a.get("name") or "there", "email": email})

    if not out and meeting.get("client_id"):
        try:
            contact = await db.contacts.find_one(
                {"client_id": meeting["client_id"], "email": {"$ne": None}})
            if contact and contact.get("email"):
                out.append({"name": contact.get("name") or "there",
                            "email": contact["email"]})
        except Exception:
            pass
    return out


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


# -- shared cancel / reschedule core -------------------------------------------
#
# The logic is identical whether a staff member triggers it from the calendar or
# an attendee taps a link in their confirmation email. The only difference is who
# the actor is (a user id, or None for a public/self-service action), so it is
# parameterised on that rather than duplicated - the public booking endpoints in
# routers/bookings.py call these too.


async def _maybe_sync_gcal_delete(meeting: dict, actor_id: Optional[str]) -> None:
    """Best-effort removal from Google Calendar. A calendar hiccup must never
    stop the cancellation being recorded and the attendee told."""
    owner = meeting.get("created_by") or actor_id
    if not (meeting.get("google_event_id") and owner):
        return
    tokens = await _get_google_tokens(owner)
    if not tokens:
        return
    try:
        service = await gcal.get_calendar_service(tokens)
        service.events().delete(
            calendarId="primary", eventId=meeting["google_event_id"]).execute()
    except Exception:
        logger.warning("Google Calendar delete failed on cancel of %s", meeting.get("_id"))


async def apply_cancellation(meeting: dict, *, reason: Optional[str], notify: bool,
                             actor_id: Optional[str]) -> dict:
    """Mark a meeting cancelled, drop it from Google Calendar, notify attendees.

    Idempotent: cancelling an already-cancelled meeting is a no-op that returns
    the meeting, so a double-tapped email link does not error or re-email.
    """
    if meeting.get("status") == "cancelled":
        return serialize_doc(meeting)

    await _maybe_sync_gcal_delete(meeting, actor_id)

    await db.meetings.update_one(
        {"_id": meeting["_id"]},
        {"$set": {"status": "cancelled",
                  "cancel_reason": reason,
                  "cancelled_at": datetime.now(timezone.utc).isoformat(),
                  "cancelled_by": actor_id}})

    notified = []
    if notify:
        for r in await _meeting_recipients(meeting):
            try:
                await send_meeting_cancelled_email(
                    r["email"], r["name"], meeting.get("title", "your meeting"),
                    meeting.get("start_time"), reason)
                notified.append(r["email"])
            except Exception as exc:
                logger.error("Cancellation email to %s failed: %s", r["email"], exc)

    await log_audit(actor_id, "cancel_meeting", "meeting", str(meeting["_id"]))
    updated = await db.meetings.find_one({"_id": meeting["_id"]})
    result = serialize_doc(updated)
    result["notified"] = notified
    return result


async def apply_reschedule(meeting: dict, *, start_time: str,
                           end_time: Optional[str], notify: bool,
                           actor_id: Optional[str]) -> dict:
    """Move a meeting to a new time, update Google Calendar, notify attendees
    with the old-and-new time. Rescheduling revives a cancelled meeting."""
    old_start = meeting.get("start_time")
    updates = {"start_time": start_time,
               "status": "scheduled",
               "rescheduled_at": datetime.now(timezone.utc).isoformat(),
               "rescheduled_by": actor_id}
    if end_time is not None:
        updates["end_time"] = end_time

    await db.meetings.update_one({"_id": meeting["_id"]}, {"$set": updates})

    owner = meeting.get("created_by") or actor_id
    if meeting.get("google_event_id") and owner:
        tokens = await _get_google_tokens(owner)
        if tokens:
            try:
                merged = {**meeting, **updates}
                service = await gcal.get_calendar_service(tokens)
                service.events().update(
                    calendarId="primary", eventId=meeting["google_event_id"],
                    body=gcal.event_body(merged)).execute()
            except Exception:
                logger.warning("Google Calendar update failed on reschedule of %s",
                               meeting.get("_id"))

    notified = []
    if notify:
        for r in await _meeting_recipients(meeting):
            try:
                await send_meeting_rescheduled_email(
                    r["email"], r["name"], meeting.get("title", "your meeting"),
                    old_start, start_time)
                notified.append(r["email"])
            except Exception as exc:
                logger.error("Reschedule email to %s failed: %s", r["email"], exc)

    await log_audit(actor_id, "reschedule_meeting", "meeting", str(meeting["_id"]))
    updated = await db.meetings.find_one({"_id": meeting["_id"]})
    result = serialize_doc(updated)
    result["notified"] = notified
    return result


@router.post("/{meeting_id}/cancel")
async def cancel_meeting(meeting_id: str, payload: CancelPayload,
                         user: dict = Depends(require_staff)):
    """Cancel a meeting: mark it cancelled, drop it from Google Calendar, and
    email the attendee(s).

    Distinct from delete - a cancelled meeting stays on the record (so the
    calendar shows what was called off and when), whereas delete removes it
    entirely. Cancelling is the client-facing action; deleting is housekeeping.
    """
    meeting = await db.meetings.find_one({"_id": to_object_id(meeting_id)})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return await apply_cancellation(meeting, reason=payload.reason,
                                    notify=payload.notify, actor_id=user["id"])


@router.post("/{meeting_id}/reschedule")
async def reschedule_meeting(meeting_id: str, payload: ReschedulePayload,
                             user: dict = Depends(require_staff)):
    """Move a meeting to a new time, update Google Calendar, and email the
    attendee(s) the old-and-new time."""
    meeting = await db.meetings.find_one({"_id": to_object_id(meeting_id)})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return await apply_reschedule(meeting, start_time=payload.start_time,
                                  end_time=payload.end_time,
                                  notify=payload.notify, actor_id=user["id"])


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

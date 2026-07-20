import logging
import secrets
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr

from database import db, serialize_doc
from auth_utils import require_staff
from email_service import send_booking_confirmation_email
from whatsapp_service import notify_admin as whatsapp_notify_admin

router = APIRouter(prefix="/api", tags=["bookings"])

DEFAULT_DAYS = {
    "0": {"enabled": True, "start": "10:00", "end": "18:00"},   # Monday
    "1": {"enabled": True, "start": "10:00", "end": "18:00"},
    "2": {"enabled": True, "start": "10:00", "end": "18:00"},
    "3": {"enabled": True, "start": "10:00", "end": "18:00"},
    "4": {"enabled": True, "start": "10:00", "end": "18:00"},   # Friday
    "5": {"enabled": False, "start": "10:00", "end": "14:00"},  # Saturday
    "6": {"enabled": False, "start": "10:00", "end": "14:00"},  # Sunday
}


class BookingSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    title: Optional[str] = None
    description: Optional[str] = None
    slot_minutes: Optional[int] = None
    buffer_minutes: Optional[int] = None
    timezone: Optional[str] = None
    days: Optional[dict] = None
    days_ahead: Optional[int] = None
    location: Optional[str] = None


class BookRequest(BaseModel):
    start_time: str
    name: str
    email: EmailStr
    notes: Optional[str] = None
    #: Signed reference from an SDR outreach email, tying this booking back to
    #: the lead that was invited. Absent for ordinary public bookings.
    ref: Optional[str] = None


async def _get_or_create_settings() -> dict:
    settings = await db.booking_settings.find_one({"key": "main"})
    if not settings:
        doc = {
            "key": "main",
            "enabled": True,
            "slug": secrets.token_urlsafe(8),
            "title": "Intro Call",
            "description": "Book a call with our team.",
            "slot_minutes": 30,
            "buffer_minutes": 0,
            "timezone": "Asia/Kolkata",
            "days": DEFAULT_DAYS,
            "days_ahead": 14,
            "location": "Google Meet / Phone",
        }
        await db.booking_settings.insert_one(doc)
        settings = await db.booking_settings.find_one({"key": "main"})
    return settings


def _tz(settings: dict) -> ZoneInfo:
    try:
        return ZoneInfo(settings.get("timezone") or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("UTC")


async def _slots_for_date(settings: dict, date_str: str) -> list:
    """Compute open slots for a YYYY-MM-DD date in the agency timezone."""
    tz = _tz(settings)
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date, expected YYYY-MM-DD")

    day_cfg = (settings.get("days") or {}).get(str(day.weekday()))
    if not day_cfg or not day_cfg.get("enabled"):
        return []

    slot_min = int(settings.get("slot_minutes") or 30)
    buffer_min = int(settings.get("buffer_minutes") or 0)
    h1, m1 = map(int, day_cfg["start"].split(":"))
    h2, m2 = map(int, day_cfg["end"].split(":"))
    window_start = day.replace(hour=h1, minute=m1, tzinfo=tz)
    window_end = day.replace(hour=h2, minute=m2, tzinfo=tz)

    # Existing meetings that day (with padding for overlaps crossing midnight)
    range_start = (window_start - timedelta(hours=24)).astimezone(dt_timezone.utc).isoformat()
    range_end = (window_end + timedelta(hours=24)).astimezone(dt_timezone.utc).isoformat()
    meetings = await db.meetings.find({
        "status": {"$ne": "cancelled"},
        "start_time": {"$lt": range_end, "$gt": range_start},
    }).to_list(500)

    busy = []
    for m in meetings:
        try:
            b_start = datetime.fromisoformat(m["start_time"].replace("Z", "+00:00"))
            if b_start.tzinfo is None:
                b_start = b_start.replace(tzinfo=dt_timezone.utc)
            if m.get("end_time"):
                b_end = datetime.fromisoformat(m["end_time"].replace("Z", "+00:00"))
                if b_end.tzinfo is None:
                    b_end = b_end.replace(tzinfo=dt_timezone.utc)
            else:
                b_end = b_start + timedelta(minutes=slot_min)
            busy.append((b_start, b_end))
        except (ValueError, KeyError):
            continue

    now = datetime.now(dt_timezone.utc)
    slots = []
    cursor = window_start
    step = timedelta(minutes=slot_min + buffer_min)
    while cursor + timedelta(minutes=slot_min) <= window_end:
        slot_end = cursor + timedelta(minutes=slot_min)
        if cursor > now and not any(bs < slot_end and be > cursor for bs, be in busy):
            slots.append(cursor.isoformat())
        cursor += step
    return slots


# ---------------- Staff settings ----------------

@router.get("/bookings/settings")
async def get_booking_settings(user: dict = Depends(require_staff)):
    settings = await _get_or_create_settings()
    return serialize_doc(settings)


@router.put("/bookings/settings")
async def update_booking_settings(payload: BookingSettingsUpdate, user: dict = Depends(require_staff)):
    await _get_or_create_settings()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "slot_minutes" in updates and not (5 <= updates["slot_minutes"] <= 240):
        raise HTTPException(status_code=400, detail="Slot length must be between 5 and 240 minutes")
    if "timezone" in updates:
        try:
            ZoneInfo(updates["timezone"])
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid timezone")
    await db.booking_settings.update_one({"key": "main"}, {"$set": updates})
    settings = await db.booking_settings.find_one({"key": "main"})
    return serialize_doc(settings)


@router.post("/bookings/settings/regenerate-link")
async def regenerate_booking_link(user: dict = Depends(require_staff)):
    await _get_or_create_settings()
    slug = secrets.token_urlsafe(8)
    await db.booking_settings.update_one({"key": "main"}, {"$set": {"slug": slug}})
    return {"slug": slug}


# ---------------- Public booking ----------------

async def _public_settings(slug: str) -> dict:
    settings = await db.booking_settings.find_one({"slug": slug})
    if not settings or not settings.get("enabled"):
        raise HTTPException(status_code=404, detail="Booking page not found")
    return settings


@router.get("/public/booking/{slug}")
async def public_booking_info(slug: str):
    settings = await _public_settings(slug)
    company = await db.company_settings.find_one({"key": "main"})
    return {
        "title": settings.get("title"),
        "description": settings.get("description"),
        "slot_minutes": settings.get("slot_minutes"),
        "timezone": settings.get("timezone"),
        "days_ahead": settings.get("days_ahead", 14),
        "available_weekdays": [int(k) for k, v in (settings.get("days") or {}).items() if v.get("enabled")],
        "company_name": (company or {}).get("company_name") or "Obrinex",
    }


@router.get("/public/booking/{slug}/slots")
async def public_booking_slots(slug: str, date: str):
    settings = await _public_settings(slug)
    slots = await _slots_for_date(settings, date)
    return {"date": date, "slots": slots}


@router.post("/public/booking/{slug}/book")
async def public_book(slug: str, payload: BookRequest):
    settings = await _public_settings(slug)
    try:
        start = datetime.fromisoformat(payload.start_time)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid start time")
    if start.tzinfo is None:
        raise HTTPException(status_code=400, detail="Start time must include timezone")

    tz = _tz(settings)
    local_start = start.astimezone(tz)
    valid_slots = await _slots_for_date(settings, local_start.strftime("%Y-%m-%d"))
    if start.isoformat() not in valid_slots and local_start.isoformat() not in valid_slots:
        raise HTTPException(status_code=409, detail="That slot is no longer available. Please pick another time.")

    slot_min = int(settings.get("slot_minutes") or 30)
    now = datetime.now(dt_timezone.utc).isoformat()
    doc = {
        "title": f"{settings.get('title', 'Meeting')} — {payload.name}",
        "lead_id": None,
        "client_id": None,
        "start_time": start.astimezone(dt_timezone.utc).isoformat(),
        "end_time": (start + timedelta(minutes=slot_min)).astimezone(dt_timezone.utc).isoformat(),
        "location": settings.get("location") or "To be confirmed",
        "attendees": [{"name": payload.name, "email": payload.email}],
        "notes": payload.notes,
        "status": "scheduled",
        "ai_summary": None,
        "created_by": None,
        "created_at": now,
        "source": "booking",
        "google_event_id": None,
        "booked_by": {"name": payload.name, "email": payload.email},
    }
    res = await db.meetings.insert_one(doc)

    # An SDR-originated booking attaches to its lead: stage moves, sequence
    # stops. Wrapped because a booking is a real commitment in the calendar —
    # failing to attribute it must never lose it.
    attached = None
    if payload.ref:
        try:
            from sdr.services import meetings as sdr_meetings
            attached = await sdr_meetings.attach_booking(str(res.inserted_id), payload.ref)
        except Exception:
            logging.getLogger(__name__).exception(
                "Could not attach booking %s to a lead", res.inserted_id
            )

    admins = await db.users.find({"role": "admin"}).to_list(20)
    local_label = local_start.strftime("%b %d, %Y at %I:%M %p")

    await send_booking_confirmation_email(
        payload.email, payload.name, settings.get("title", "Meeting"),
        f"{local_label} ({settings.get('timezone', '')})",
        settings.get("location") or "To be confirmed",
        (await db.company_settings.find_one({"key": "main"}) or {}).get("company_name") or "Obrinex",
    )
    await whatsapp_notify_admin(
        f"📅 New booking!\n{payload.name} ({payload.email}) booked \"{settings.get('title', 'a meeting')}\"\n🕐 {local_label} ({settings.get('timezone', '')})"
        + (f"\n📝 {payload.notes}" if payload.notes else "")
    )
    for a in admins:
        await db.notifications.insert_one({
            "user_id": str(a["_id"]),
            "type": "meeting_booked",
            "title": "New meeting booked",
            "message": f"{payload.name} ({payload.email}) booked {settings.get('title', 'a meeting')} on {local_label}.",
            "link": "/calendar",
            "read": False,
            "created_at": now,
        })

    return {
        "message": "Booking confirmed",
        "meeting_id": str(res.inserted_id),
        "start_time": doc["start_time"],
        "end_time": doc["end_time"],
        "timezone": settings.get("timezone"),
        "attached_to_lead": bool((attached or {}).get("attached")),
    }

"""Verification: self-service cancel/reschedule from the booking confirmation
email, against real MongoDB.

Acceptance criteria for "add a cancel and reschedule option in the first email":
  - booking mints a manage token and the confirmation email carries the links
  - the manage page can read the meeting by that token, and only that token
  - the attendee can reschedule to a real available slot (validated), and the
    meeting actually moves + a rescheduled email goes out
  - the attendee can cancel, the meeting is marked cancelled + an email goes out
  - a bad token resolves to nothing; an unavailable slot is refused

Emails and WhatsApp are captured, not sent. Everything else is real Mongo.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "velliom_bookingmanage_scratch")

PASS, FAIL = [], []
CONFIRM, CANCELLED, RESCHEDULED = [], [], []


def check(label, condition, detail=""):
    (PASS if condition else FAIL).append(label)
    print(f"  {'PASS' if condition else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")


async def main() -> int:
    from database import db, client
    from fastapi import HTTPException
    import routers.bookings as bookings
    import routers.meetings as meetings

    await client.drop_database(db.name)
    print(f"\n=== scratch db: {db.name} (dropped clean) ===\n")

    # Capture outbound instead of sending.
    async def fake_confirm(to, name, title, when, loc, company, manage_token=None):
        CONFIRM.append({"to": to, "manage_token": manage_token})

    async def fake_cancelled(to, name, title, start, reason):
        CANCELLED.append({"to": to, "reason": reason})

    async def fake_rescheduled(to, name, title, old, new):
        RESCHEDULED.append({"to": to, "old": old, "new": new})

    async def fake_whatsapp(msg):
        return None

    bookings.send_booking_confirmation_email = fake_confirm
    bookings.whatsapp_notify_admin = fake_whatsapp
    meetings.send_meeting_cancelled_email = fake_cancelled
    meetings.send_meeting_rescheduled_email = fake_rescheduled

    # A booking calendar with every weekday open, so any near date has slots.
    all_days = {str(i): {"enabled": True, "start": "09:00", "end": "18:00"}
                for i in range(7)}
    slug = "test-slug-123"
    await db.booking_settings.insert_one({
        "key": "main", "enabled": True, "slug": slug, "title": "Intro Call",
        "description": "x", "slot_minutes": 30, "buffer_minutes": 0,
        "timezone": "Asia/Kolkata", "days": all_days, "days_ahead": 14,
        "location": "Google Meet"})
    await db.company_settings.insert_one({"key": "main", "company_name": "Obrinex"})

    # A date a few days out so there is always a future slot regardless of now.
    target = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d")
    settings = await bookings._public_settings(slug)
    slots = await bookings._slots_for_date(settings, target)
    check("the test calendar has open slots", len(slots) >= 2, str(len(slots)))

    # --- 1. book, and confirm the email carries a manage link ----------------
    print("1. Booking mints a manage token")
    booked = await bookings.public_book(slug, bookings.BookRequest(
        start_time=slots[0], name="Dana", email="dana@example.com"))
    meeting = await db.meetings.find_one({"booked_by.email": "dana@example.com"})
    token = meeting.get("manage_token")
    check("meeting stored a manage token", bool(token))
    check("meeting stored its booking slug", meeting.get("booking_slug") == slug)
    check("confirmation email was sent with that token",
          CONFIRM and CONFIRM[-1]["manage_token"] == token)

    # --- 2. manage page reads the meeting by token ---------------------------
    print("\n2. Manage page reads by token")
    info = await bookings.public_manage_info(token)
    check("returns the meeting title", info["title"] == meeting["title"])
    check("says it can be rescheduled", info["can_reschedule"] is True)
    check("exposes no internal id", "id" not in info and "_id" not in info)
    try:
        await bookings.public_manage_info("not-a-real-token")
        check("a bad token is rejected", False, "no error raised")
    except HTTPException as exc:
        check("a bad token is rejected", exc.status_code == 404, str(exc.status_code))

    # --- 3. reschedule to another real slot ----------------------------------
    print("\n3. Reschedule")
    # Pick a slot on the next day so it can't collide with the current booking.
    target2 = (datetime.now(timezone.utc) + timedelta(days=4)).strftime("%Y-%m-%d")
    slots2 = await bookings._slots_for_date(settings, target2)
    new_slot = slots2[0]
    out = await bookings.public_manage_reschedule(
        token, bookings.PublicRescheduleRequest(start_time=new_slot))
    check("reschedule reports success", out["status"] == "rescheduled")
    moved = await db.meetings.find_one({"manage_token": token})
    check("the meeting actually moved",
          moved["start_time"] == datetime.fromisoformat(new_slot).astimezone(timezone.utc).isoformat())
    check("its status is scheduled", moved["status"] == "scheduled")
    check("a rescheduled email went to the attendee",
          RESCHEDULED and RESCHEDULED[-1]["to"] == "dana@example.com")

    try:
        await bookings.public_manage_reschedule(
            token, bookings.PublicRescheduleRequest(
                start_time="2020-01-01T10:00:00+05:30"))
        check("an unavailable/past slot is refused", False, "no error raised")
    except HTTPException as exc:
        check("an unavailable/past slot is refused", exc.status_code == 409,
              str(exc.status_code))

    # --- 4. cancel -----------------------------------------------------------
    print("\n4. Cancel")
    out = await bookings.public_manage_cancel(token)
    check("cancel reports success", out["status"] == "cancelled")
    done = await db.meetings.find_one({"manage_token": token})
    check("the meeting is marked cancelled", done["status"] == "cancelled")
    check("cancelled by the attendee (no staff actor)", done.get("cancelled_by") is None)
    check("a cancellation email went to the attendee",
          CANCELLED and CANCELLED[-1]["to"] == "dana@example.com")

    # Idempotent: a second tap on the email link must not re-email or error.
    before = len(CANCELLED)
    await bookings.public_manage_cancel(token)
    check("a second cancel is a no-op (no duplicate email)", len(CANCELLED) == before)

    print(f"\n=== {len(PASS)} passed, {len(FAIL)} failed ===")
    for f in FAIL:
        print(f"  FAILED: {f}")
    await client.drop_database(db.name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from database import db, next_counter
from email_service import send_meeting_reminder_email, send_overdue_invoice_email, send_daily_digest_email
from whatsapp_service import notify_admin as whatsapp_notify_admin

logger = logging.getLogger(__name__)

REMINDER_MINUTES = 30
CHECK_INTERVAL_SECONDS = 60
DAILY_CHECK_INTERVAL_SECONDS = 600  # daily jobs re-checked every 10 minutes
AGENCY_TZ = ZoneInfo("Asia/Kolkata")
DIGEST_HOUR = 8  # 8 AM IST


async def _process_due_reminders():
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=REMINDER_MINUTES)
    meetings = await db.meetings.find({
        "status": "scheduled",
        "reminder_sent": {"$ne": True},
        "start_time": {"$gt": now.isoformat(), "$lt": window_end.isoformat()},
    }).to_list(100)

    for m in meetings:
        start_label = m["start_time"][:16].replace("T", " ") + " UTC"
        try:
            start_dt = datetime.fromisoformat(m["start_time"].replace("Z", "+00:00"))
            start_label = start_dt.strftime("%b %d, %I:%M %p UTC")
        except ValueError:
            pass

        # In-app notification for the staff member (or all admins for public bookings)
        recipients = []
        if m.get("created_by"):
            recipients = [m["created_by"]]
        else:
            admins = await db.users.find({"role": "admin"}).to_list(20)
            recipients = [str(a["_id"]) for a in admins]
        for uid in recipients:
            await db.notifications.insert_one({
                "user_id": uid, "type": "meeting_reminder",
                "title": "Meeting in 30 minutes",
                "message": f"{m.get('title', 'Meeting')} starts at {start_label}.",
                "link": "/calendar", "read": False,
                "created_at": now.isoformat(),
            })

        # Email the external attendee if this came through the booking page
        booked_by = m.get("booked_by")
        if booked_by and booked_by.get("email"):
            await send_meeting_reminder_email(
                booked_by["email"], booked_by.get("name", "there"),
                m.get("title", "Your meeting"), start_label,
                m.get("location") or "See confirmation email",
            )

        await db.meetings.update_one({"_id": m["_id"]}, {"$set": {"reminder_sent": True}})
        logger.info(f"Reminder sent for meeting {m['_id']}")


async def reminder_loop():
    logger.info("Meeting reminder loop started")
    while True:
        try:
            await _process_due_reminders()
        except Exception as e:
            logger.error(f"Reminder loop error: {e}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- Daily jobs (overdue chasing, recurring invoices, digest) ----------------

async def _already_ran_today(job: str, today: str) -> bool:
    state = await db.system_state.find_one({"job": job})
    return bool(state and state.get("last_run_date") == today)


async def _mark_ran(job: str, today: str):
    await db.system_state.update_one({"job": job}, {"$set": {"last_run_date": today}}, upsert=True)


async def _invoice_recipient(invoice: dict):
    portal_user = await db.users.find_one({"role": "client", "client_id": invoice["client_id"]})
    if portal_user:
        return portal_user["email"]
    contact = await db.contacts.find_one({"client_id": invoice["client_id"], "email": {"$ne": None}})
    return contact.get("email") if contact else None


async def chase_overdue_invoices():
    """Mark past-due invoices overdue and send escalating reminders (max one per 3 days)."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    invoices = await db.invoices.find({
        "status": {"$in": ["sent", "viewed", "partial", "overdue"]},
        "due_date": {"$lt": now_iso},
    }).to_list(500)

    chased = []
    for inv in invoices:
        if inv["status"] != "overdue":
            await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"status": "overdue"}})
        last = inv.get("last_reminder_at")
        if last:
            try:
                if datetime.fromisoformat(last) > now - timedelta(days=3):
                    continue
            except ValueError:
                pass
        days_overdue = 0
        try:
            days_overdue = (now - datetime.fromisoformat(inv["due_date"].replace("Z", "+00:00"))).days
        except ValueError:
            pass
        level = 1 if days_overdue < 7 else (2 if days_overdue < 14 else 3)
        recipient = await _invoice_recipient(inv)
        if recipient:
            await send_overdue_invoice_email(
                recipient, inv["invoice_number"], inv["total"], inv["due_date"],
                inv.get("currency", "INR"), level,
            )
        await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {
            "last_reminder_at": now_iso,
        }, "$inc": {"reminder_count": 1}})
        chased.append(f"{inv['invoice_number']} ({days_overdue}d overdue, level {level})")

    if chased:
        await whatsapp_notify_admin("💰 Overdue invoice reminders sent:\n" + "\n".join(chased[:10]))
        logger.info(f"Chased {len(chased)} overdue invoice(s)")
    return chased


def _add_interval(dt: datetime, interval: str) -> datetime:
    if interval == "weekly":
        return dt + timedelta(weeks=1)
    if interval == "quarterly":
        return dt + timedelta(days=91)
    if interval == "yearly":
        return dt + timedelta(days=365)
    return dt + timedelta(days=30)  # monthly default


async def generate_recurring_invoices():
    """Clone recurring invoices when their next cycle is due."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    recurring = await db.invoices.find({"is_recurring": True}).to_list(500)
    created = []
    for inv in recurring:
        next_at = inv.get("next_recurrence_at")
        if not next_at:
            try:
                base = datetime.fromisoformat(inv["issue_date"].replace("Z", "+00:00"))
            except ValueError:
                base = now
            next_at = _add_interval(base, inv.get("recurrence_interval") or "monthly").isoformat()
            await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"next_recurrence_at": next_at}})
        if next_at > now_iso:
            continue

        number = await next_counter("invoice")
        new_doc = {k: v for k, v in inv.items() if k != "_id"}
        new_doc.update({
            "invoice_number": f"INV-{number:04d}",
            "status": "draft",
            "is_recurring": False,          # the clone is a normal invoice; the template keeps recurring
            "next_recurrence_at": None,
            "issue_date": now_iso,
            "due_date": (now + timedelta(days=14)).isoformat(),
            "stripe_session_id": None, "paid_at": None,
            "last_reminder_at": None, "reminder_count": 0,
            "created_at": now_iso, "updated_at": now_iso,
            "generated_from": str(inv["_id"]),
        })
        res = await db.invoices.insert_one(new_doc)
        await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {
            "next_recurrence_at": _add_interval(now, inv.get("recurrence_interval") or "monthly").isoformat(),
        }})
        created.append(new_doc["invoice_number"])
        admins = await db.users.find({"role": "admin"}).to_list(20)
        for a in admins:
            await db.notifications.insert_one({
                "user_id": str(a["_id"]), "type": "invoice_generated",
                "title": "Recurring invoice generated",
                "message": f"{new_doc['invoice_number']} was auto-created from a recurring invoice. Review and send it.",
                "link": f"/invoices/{res.inserted_id}", "read": False, "created_at": now_iso,
            })
    if created:
        logger.info(f"Generated recurring invoice(s): {', '.join(created)}")
    return created


async def send_daily_digest():
    now_local = datetime.now(AGENCY_TZ)
    today = now_local.strftime("%Y-%m-%d")
    day_start_utc = now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()
    day_end_utc = now_local.replace(hour=23, minute=59, second=59).astimezone(timezone.utc).isoformat()
    yesterday_utc = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    meetings = await db.meetings.find({"status": "scheduled", "start_time": {"$gte": day_start_utc, "$lte": day_end_utc}}).sort("start_time", 1).to_list(50)
    tasks = await db.tasks.find({"status": {"$nin": ["done"]}, "due_date": {"$gte": day_start_utc, "$lte": day_end_utc}}).to_list(50)
    leads = await db.leads.find({"created_at": {"$gte": yesterday_utc}}).to_list(50)
    overdue = await db.invoices.find({"status": "overdue"}).to_list(50)

    def mt_label(m):
        try:
            t = datetime.fromisoformat(m["start_time"].replace("Z", "+00:00")).astimezone(AGENCY_TZ).strftime("%I:%M %p")
        except ValueError:
            t = "?"
        return f"{t} — {m.get('title', 'Meeting')}"

    digest = {
        "date": now_local.strftime("%A, %b %d"),
        "meetings": [mt_label(m) for m in meetings],
        "tasks": [t.get("title", "Task") for t in tasks],
        "leads": [f"{l.get('company', '?')} ({l.get('source', 'manual')})" for l in leads],
        "overdue": [f"{i['invoice_number']} — {i.get('currency', 'INR')} {i['total']:,.0f}" for i in overdue],
    }

    admins = await db.users.find({"role": "admin"}).to_list(20)
    for a in admins:
        await send_daily_digest_email(a["email"], digest)

    wa_lines = [f"☀️ Daily Brief — {digest['date']}"]
    wa_lines.append(f"📅 Meetings: {len(digest['meetings'])}" + (("\n  " + "\n  ".join(digest["meetings"][:5])) if digest["meetings"] else ""))
    wa_lines.append(f"✅ Tasks due: {len(digest['tasks'])}")
    wa_lines.append(f"🔥 New leads: {len(digest['leads'])}")
    wa_lines.append(f"💰 Overdue invoices: {len(digest['overdue'])}")
    await whatsapp_notify_admin("\n".join(wa_lines))
    logger.info("Daily digest sent")


async def daily_loop():
    logger.info("Daily jobs loop started (overdue chasing, recurring invoices, digest)")
    while True:
        try:
            now_local = datetime.now(AGENCY_TZ)
            today = now_local.strftime("%Y-%m-%d")

            if not await _already_ran_today("overdue_chase", today):
                await chase_overdue_invoices()
                await _mark_ran("overdue_chase", today)

            if not await _already_ran_today("recurring_invoices", today):
                await generate_recurring_invoices()
                await _mark_ran("recurring_invoices", today)

            if now_local.hour >= DIGEST_HOUR and not await _already_ran_today("daily_digest", today):
                await send_daily_digest()
                await _mark_ran("daily_digest", today)
        except Exception as e:
            logger.error(f"Daily loop error: {e}")
        await asyncio.sleep(DAILY_CHECK_INTERVAL_SECONDS)

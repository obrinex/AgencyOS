"""Meetings: proposing times, attaching bookings to leads, no-shows.

**The design decision that matters here:** the agent does not book. It offers.

The obvious build is an agent that reads "Thursday works" and creates the
calendar event. That path has two failure modes with real cost - misparsing a
date, and racing another booking into the same slot - and the app already has
a booking page that cannot do either: it re-validates the slot against live
availability and refuses with a 409 if it went while the email sat unread.

So the agent computes concrete times in the lead's timezone, puts them in a
reply next to a booking link carrying a signed reference, and the existing
public booking flow does the actual writing. When that booking arrives with a
valid reference, this module attaches it to the lead: stage moves, sequence
stops, `meeting_booked_at` is stamped.

The one thing it must never do is keep emailing someone who has booked.
"""

import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone

from database import db, now_iso, serialize_doc
from sdr.collections import ENROLLMENTS
from sdr.domain import meetings as meetings_domain
from sdr.domain import pipeline
from sdr.domain import sequence as sequence_domain
from sdr.config.countries import get_country, get_holidays
from sdr.repositories import campaigns as campaigns_repo
from sdr.repositories import companies as companies_repo
from sdr.repositories import leads as leads_repo
from sdr.repositories.base import object_id

logger = logging.getLogger(__name__)


def _secret() -> bytes:
    return (os.environ.get("JWT_SECRET") or "sdr-dev-secret").encode("utf-8")


def booking_ref(lead_id: str) -> str:
    """Signed, stateless reference tying a booking back to a lead.

    Same posture as the unsubscribe token: stateless so the link survives any
    database state, signed so editing the lead id in a URL cannot attach a
    stranger's booking to someone else's record.
    """
    digest = hmac.new(_secret(), f"booking:{lead_id}".encode("utf-8"), hashlib.sha256)
    return f"{lead_id}.{digest.hexdigest()[:32]}"


def verify_booking_ref(ref: str) -> str | None:
    """Return the lead id if the reference is genuine, else None."""
    if not ref or "." not in ref:
        return None
    lead_id, _, token = ref.rpartition(".")
    expected = booking_ref(lead_id).rpartition(".")[2]
    if hmac.compare_digest(expected, token):
        return lead_id
    return None


async def booking_url(lead_id: str) -> str | None:
    """The public booking page, carrying this lead's reference.

    None when booking is switched off or unconfigured - the caller then omits
    the link rather than emailing a dead URL.
    """
    settings = await db.booking_settings.find_one({"key": "main"})
    if not settings or not settings.get("enabled") or not settings.get("slug"):
        return None
    frontend = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    if not frontend:
        return None
    return f"{frontend}/book/{settings['slug']}?ref={booking_ref(lead_id)}"


# --- Proposing ----------------------------------------------------------------

async def propose_slots(lead_id: str, *, count: int = meetings_domain.DEFAULT_SUGGESTIONS,
                        now=None) -> dict:
    """Times that work for both sides, in the lead's timezone.

    Returns the slots plus the formatted labels an email would use, so the
    caller never has to re-derive the timezone maths and risk disagreeing
    with what was actually offered.
    """
    from routers.bookings import _get_or_create_settings, _slots_for_date

    lead = await leads_repo.get_lead(lead_id)
    company = {}
    if lead.get("sdr_company_id"):
        try:
            company = await companies_repo.get_company(lead["sdr_company_id"])
        except Exception:
            company = {}

    country_code = company.get("country_code")
    country = get_country(country_code)
    # The company's own timezone beats the country default - the US has four,
    # and picking the wrong one moves every proposed time by three hours.
    timezone_name = company.get("timezone")
    holidays = get_holidays(country_code, datetime.now(timezone.utc).year)

    settings = await _get_or_create_settings()
    reference = meetings_domain._parse(now) if now else datetime.now(timezone.utc)
    days_ahead = int(settings.get("days_ahead") or 14)

    agency_slots = []
    for offset in range(days_ahead + 1):
        day = (reference + timedelta(days=offset)).strftime("%Y-%m-%d")
        try:
            agency_slots.extend(await _slots_for_date(settings, day))
        except Exception:
            continue   # one bad day must not kill the whole proposal

    usable = meetings_domain.usable_slots(
        agency_slots, country=country, timezone_name=timezone_name,
        holidays=holidays, now=reference,
        duration_minutes=int(settings.get("slot_minutes") or 30),
    )
    picked = meetings_domain.spread_suggestions(
        usable, count=count, timezone_name=timezone_name
    )

    return {
        "lead_id": lead_id,
        "timezone": timezone_name or "UTC",
        "slots": [slot.isoformat() for slot in picked],
        "labels": [meetings_domain.format_slot(slot, timezone_name) for slot in picked],
        "booking_url": await booking_url(lead_id),
        "agency_slot_count": len(agency_slots),
        "usable_slot_count": len(usable),
    }


# --- Attaching a booking ------------------------------------------------------

async def attach_booking(meeting_id: str, ref: str) -> dict:
    """Tie a public booking to the lead that was invited.

    Called from the public booking endpoint. Deliberately forgiving: a
    booking that cannot be attributed is still a real meeting in the
    calendar, so a bad reference logs and returns rather than raising and
    losing the booking.
    """
    lead_id = verify_booking_ref(ref)
    if not lead_id:
        logger.info("Booking %s carried an unverifiable reference", meeting_id)
        return {"attached": False, "reason": "invalid_ref"}

    try:
        lead = await leads_repo.get_lead(lead_id)
    except Exception:
        return {"attached": False, "reason": "lead_not_found"}

    booked_at = now_iso()
    await db.meetings.update_one(
        {"_id": object_id(meeting_id, "meeting id")},
        {"$set": {"lead_id": lead_id, "source": "sdr_booking"}},
    )
    await db.leads.update_one(
        {"_id": object_id(lead_id, "lead id")},
        {"$set": {"meeting_booked_at": booked_at, "updated_at": booked_at}},
    )

    # Someone who has booked must not receive the next follow-up. This is the
    # same reasoning as a reply stopping a sequence, and it is the failure
    # this whole module exists to avoid.
    stopped = await _stop_sequences(lead_id)

    moved = False
    from_stage = lead.get("stage") or pipeline.PROSPECT
    if pipeline.can_transition(from_stage, pipeline.MEETING_SCHEDULED, "ai"):
        await leads_repo.transition_stage(
            lead_id, pipeline.MEETING_SCHEDULED, actor="ai",
            reason="Booked a meeting from an outreach email",
        )
        moved = True
    else:
        # A lead already won, lost or archived does not get dragged back by a
        # stale link. The meeting still attaches; the pipeline is left alone.
        logger.info("Lead %s in '%s' keeps its stage despite a booking",
                    lead_id, from_stage)

    return {"attached": True, "lead_id": lead_id, "stage_moved": moved,
            "enrollments_stopped": stopped}


async def _stop_sequences(lead_id: str) -> int:
    stopped = 0
    active = await db[ENROLLMENTS].find(
        {"lead_id": lead_id, "status": sequence_domain.ACTIVE}
    ).to_list(20)
    for enrollment in active:
        await campaigns_repo.stop_enrollment(str(enrollment["_id"]), "replied")
        stopped += 1
    return stopped


# --- No-shows -----------------------------------------------------------------

async def sweep_no_shows(*, now=None, limit: int = 200) -> dict:
    """Meetings that came and went with nobody resolving them.

    Moves the lead back to `interested` - a transition the state machine
    already models - so they re-enter normal working rather than sitting in
    `meeting_scheduled` forever looking like a win that already happened.

    Marks the meeting `no_show` rather than deleting it: a lead who no-shows
    twice is a different conversation from one who never booked.
    """
    reference = meetings_domain._parse(now) if now else datetime.now(timezone.utc)
    cutoff = (reference - timedelta(
        minutes=meetings_domain.NO_SHOW_GRACE_MINUTES)).isoformat()

    candidates = await db.meetings.find({
        "status": "scheduled",
        "lead_id": {"$ne": None},
        "start_time": {"$lt": cutoff},
    }).to_list(limit)

    swept, reverted = 0, 0
    for meeting in candidates:
        if not meetings_domain.is_no_show(serialize_doc(meeting), now=reference):
            continue
        await db.meetings.update_one(
            {"_id": meeting["_id"]},
            {"$set": {"status": "no_show", "updated_at": now_iso()}},
        )
        swept += 1

        lead_id = meeting.get("lead_id")
        try:
            lead = await leads_repo.get_lead(lead_id)
        except Exception:
            continue
        if lead.get("stage") != pipeline.MEETING_SCHEDULED:
            continue   # a human already moved them on; leave it
        await leads_repo.transition_stage(
            lead_id, pipeline.INTERESTED, actor="system",
            reason="Meeting time passed with no outcome recorded",
        )
        reverted += 1

    return {"checked": len(candidates), "marked_no_show": swept,
            "leads_reverted": reverted}

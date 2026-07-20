"""Meetings: proposing times, attaching bookings, no-shows.

The thing worth testing hardest is the timezone intersection. A slot that is
open on the agency's calendar but 3am where the lead lives is not an option,
and offering it is invisible until somebody books it and nobody shows up.

Second is `attach_booking` stopping the sequence. A lead who has booked a call
and then receives the next automated follow-up has been told, in effect, that
nobody noticed — the same failure the reply handling exists to prevent, just
arriving through the calendar instead of the inbox.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "sdr_test")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-hmac")

from test_campaign_flow import (  # noqa: E402  - shared fixtures and helpers
    USER, _make_running_campaign, _seed_lead, db, ready, stub_llm,
)

#: A Wednesday, so weekday maths is unambiguous.
BASE = datetime(2026, 8, 5, 6, 0, tzinfo=timezone.utc)


def _india():
    from sdr.config.countries import get_country
    return get_country("IN")


# --- The timezone intersection ------------------------------------------------

def test_a_slot_outside_the_leads_working_day_is_not_offered():
    """The whole point of the module. India's business hours are 10:00–19:00
    local; 03:00 IST is open on nobody's calendar."""
    from sdr.domain import meetings

    # 21:30 UTC on a Wednesday = 03:00 IST Thursday.
    middle_of_the_night = datetime(2026, 8, 5, 21, 30, tzinfo=timezone.utc)
    # 06:30 UTC = 12:00 IST, comfortably inside the day.
    lunchtime = datetime(2026, 8, 6, 6, 30, tzinfo=timezone.utc)

    usable = meetings.usable_slots(
        [middle_of_the_night.isoformat(), lunchtime.isoformat()],
        country=_india(), timezone_name="Asia/Kolkata", now=BASE,
    )

    assert usable == [lunchtime]


def test_a_call_that_would_run_past_closing_is_not_offered():
    """Both ends must fit. A 30-minute call starting at 18:45 against a 19:00
    close is not a real option."""
    from sdr.domain import meetings

    # 13:20 UTC = 18:50 IST. Starts inside the day, ends after it closes.
    straddling = datetime(2026, 8, 6, 13, 20, tzinfo=timezone.utc)
    assert meetings.usable_slots(
        [straddling.isoformat()], country=_india(),
        timezone_name="Asia/Kolkata", now=BASE, duration_minutes=30,
    ) == []


def test_nothing_is_proposed_inside_the_minimum_lead_time():
    """A slot two hours out is usually gone by the time the email is read."""
    from sdr.domain import meetings

    soon = BASE + timedelta(hours=2)
    later = BASE + timedelta(days=1, hours=1)   # 11:30 IST next day
    usable = meetings.usable_slots(
        [soon.isoformat(), later.isoformat()],
        country=_india(), timezone_name="Asia/Kolkata", now=BASE,
    )
    assert soon not in usable


def test_suggestions_are_spread_across_days_not_stacked_on_one():
    """Three times on one afternoon is one option with extra steps."""
    from sdr.domain import meetings

    same_day = [datetime(2026, 8, 6, 5 + h, 0, tzinfo=timezone.utc) for h in range(4)]
    next_day = [datetime(2026, 8, 7, 6, 0, tzinfo=timezone.utc)]
    third_day = [datetime(2026, 8, 10, 6, 0, tzinfo=timezone.utc)]

    picked = meetings.spread_suggestions(
        same_day + next_day + third_day, count=3, timezone_name="Asia/Kolkata"
    )

    assert len(picked) == 3
    days = {p.astimezone(timezone.utc).date() for p in picked}
    assert len(days) == 3


def test_suggestions_top_up_when_there_are_not_enough_days():
    from sdr.domain import meetings

    same_day = [datetime(2026, 8, 6, 5 + h, 0, tzinfo=timezone.utc) for h in range(3)]
    picked = meetings.spread_suggestions(same_day, count=3, timezone_name="UTC")
    assert len(picked) == 3


def test_a_slot_label_always_names_its_timezone():
    """"Thursday 3pm" across two countries is an ambiguity that costs the
    meeting it was meant to arrange."""
    from sdr.domain import meetings

    label = meetings.format_slot(
        datetime(2026, 8, 6, 6, 30, tzinfo=timezone.utc), "Asia/Kolkata"
    )
    assert "Asia/Kolkata" in label
    assert "Thursday" in label
    assert "12:00 PM" in label


# --- The signed reference -----------------------------------------------------

def test_a_booking_reference_cannot_be_edited_to_point_at_another_lead():
    from sdr.services import meetings as meetings_service

    ref = meetings_service.booking_ref("abc123")
    assert meetings_service.verify_booking_ref(ref) == "abc123"

    forged = ref.replace("abc123", "def456", 1)
    assert meetings_service.verify_booking_ref(forged) is None
    assert meetings_service.verify_booking_ref("nonsense") is None
    assert meetings_service.verify_booking_ref("") is None


# --- No-show detection --------------------------------------------------------

def test_only_an_unresolved_scheduled_meeting_counts_as_a_no_show():
    from sdr.domain import meetings

    past = (BASE - timedelta(hours=4)).isoformat()

    assert meetings.is_no_show(
        {"status": "scheduled", "end_time": past}, now=BASE) is True
    # A human already decided; their call stands.
    for status in ("completed", "cancelled", "no_show"):
        assert meetings.is_no_show(
            {"status": status, "end_time": past}, now=BASE) is False
    # Still inside the grace period.
    recent = (BASE - timedelta(minutes=10)).isoformat()
    assert meetings.is_no_show(
        {"status": "scheduled", "end_time": recent}, now=BASE) is False


# --- Attaching a booking ------------------------------------------------------

@pytest.mark.asyncio
async def test_booking_a_meeting_stops_the_sequence_and_moves_the_lead(db, ready, stub_llm):
    """A lead who books and then gets the next follow-up has been told nobody
    noticed."""
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.repositories import leads as leads_repo
    from sdr.services import meetings as meetings_service

    _, lead = await _seed_lead()
    await leads_repo.transition_stage(lead["id"], "contacted", actor="system")
    _, launch = await _make_running_campaign([lead["id"]])

    meeting = await db.meetings.insert_one({
        "title": "Intro call", "lead_id": None, "status": "scheduled",
        "start_time": (BASE + timedelta(days=2)).isoformat(),
        "end_time": (BASE + timedelta(days=2, minutes=30)).isoformat(),
    })

    result = await meetings_service.attach_booking(
        str(meeting.inserted_id), meetings_service.booking_ref(lead["id"])
    )

    assert result["attached"] is True
    assert result["stage_moved"] is True
    assert result["enrollments_stopped"] == 1

    refreshed = await leads_repo.get_lead(lead["id"])
    assert refreshed["stage"] == "meeting_scheduled"
    assert refreshed["meeting_booked_at"]

    enrollment = await campaigns_repo.get_enrollment(launch["enrollment"]["ids"][0]) \
        if launch.get("enrollment", {}).get("ids") else None
    if enrollment:
        assert enrollment["status"] == "stopped"


@pytest.mark.asyncio
async def test_an_unverifiable_reference_never_touches_a_lead(db, ready, stub_llm):
    """A booking is a real commitment in the calendar. A bad reference must
    lose the attribution, not the meeting."""
    from sdr.services import meetings as meetings_service

    meeting = await db.meetings.insert_one({
        "title": "Intro call", "lead_id": None, "status": "scheduled",
        "start_time": BASE.isoformat(),
    })

    result = await meetings_service.attach_booking(
        str(meeting.inserted_id), "someoneelse.deadbeef"
    )
    assert result["attached"] is False
    assert result["reason"] == "invalid_ref"

    # The meeting itself is untouched and still in the calendar.
    stored = await db.meetings.find_one({"_id": meeting.inserted_id})
    assert stored["lead_id"] is None


@pytest.mark.asyncio
async def test_a_stale_link_does_not_drag_a_closed_lead_back(db, ready, stub_llm):
    """`won` is terminal for every actor. A booking link found in an old email
    must not resurrect it."""
    from sdr.repositories import leads as leads_repo
    from sdr.services import meetings as meetings_service

    _, lead = await _seed_lead()
    for stage in ("contacted", "qualified", "interested", "proposal_sent",
                  "negotiation", "won"):
        await leads_repo.transition_stage(lead["id"], stage, actor="user")

    meeting = await db.meetings.insert_one({
        "title": "Intro call", "lead_id": None, "status": "scheduled",
        "start_time": BASE.isoformat(),
    })
    result = await meetings_service.attach_booking(
        str(meeting.inserted_id), meetings_service.booking_ref(lead["id"])
    )

    # Attached for the record, but the pipeline is left alone.
    assert result["attached"] is True
    assert result["stage_moved"] is False
    assert (await leads_repo.get_lead(lead["id"]))["stage"] == "won"


# --- No-show sweep ------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_no_show_returns_the_lead_to_interested(db, ready, stub_llm):
    from sdr.repositories import leads as leads_repo
    from sdr.services import meetings as meetings_service

    _, lead = await _seed_lead()
    for stage in ("contacted", "interested", "meeting_scheduled"):
        await leads_repo.transition_stage(lead["id"], stage, actor="user")

    await db.meetings.insert_one({
        "title": "Intro call", "lead_id": lead["id"], "status": "scheduled",
        "start_time": (BASE - timedelta(hours=4)).isoformat(),
        "end_time": (BASE - timedelta(hours=3, minutes=30)).isoformat(),
    })

    result = await meetings_service.sweep_no_shows(now=BASE)

    assert result["marked_no_show"] == 1
    assert result["leads_reverted"] == 1
    assert (await leads_repo.get_lead(lead["id"]))["stage"] == "interested"


@pytest.mark.asyncio
async def test_the_sweep_leaves_a_lead_a_human_already_moved(db, ready, stub_llm):
    """Someone took the call and moved them to discovery. The bookkeeping must
    not undo that."""
    from sdr.repositories import leads as leads_repo
    from sdr.services import meetings as meetings_service

    _, lead = await _seed_lead()
    for stage in ("contacted", "interested", "meeting_scheduled", "discovery"):
        await leads_repo.transition_stage(lead["id"], stage, actor="user")

    await db.meetings.insert_one({
        "title": "Intro call", "lead_id": lead["id"], "status": "scheduled",
        "start_time": (BASE - timedelta(hours=4)).isoformat(),
        "end_time": (BASE - timedelta(hours=3, minutes=30)).isoformat(),
    })

    result = await meetings_service.sweep_no_shows(now=BASE)

    assert result["marked_no_show"] == 1        # the meeting is still resolved
    assert result["leads_reverted"] == 0        # but the lead is left alone
    assert (await leads_repo.get_lead(lead["id"]))["stage"] == "discovery"


# --- The proposal email -------------------------------------------------------

def test_the_proposal_never_invents_a_time_it_does_not_have():
    """With no overlapping slot it says so and offers the calendar, rather
    than producing a plausible-looking time that exists nowhere."""
    from sdr.agents.meetings.agent import build_proposal

    subject, body = build_proposal(
        first_name="Priya", labels=[], booking_url="https://x.example/book/abc",
        sender_name="Amrit",
    )
    assert subject
    assert "https://x.example/book/abc" in body
    assert "Hi Priya," in body
    # No fabricated day names anywhere in the copy.
    for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
        assert day not in body


def test_the_proposal_lists_the_times_it_was_given():
    from sdr.agents.meetings.agent import build_proposal

    _, body = build_proposal(
        first_name=None,
        labels=["Thursday August 6, 12:00 PM (Asia/Kolkata)",
                "Friday August 7, 3:30 PM (Asia/Kolkata)"],
        booking_url=None, sender_name="Amrit",
    )
    assert "Thursday August 6, 12:00 PM (Asia/Kolkata)" in body
    assert "Friday August 7, 3:30 PM (Asia/Kolkata)" in body
    assert body.startswith("Hi,")


@pytest.mark.asyncio
async def test_a_lead_who_has_not_engaged_gets_no_proposal(db, ready, stub_llm):
    from sdr.agents.base.agent import AgentContext
    from sdr.agents.meetings.agent import MeetingProposalAgent

    _, lead = await _seed_lead()   # stage: prospect

    result = await MeetingProposalAgent().run({"lead_id": lead["id"]}, AgentContext())
    assert result.output["skipped"] is True


# --- The booking endpoint, end to end -----------------------------------------

@pytest.mark.asyncio
async def test_booking_through_the_public_endpoint_attaches_to_the_lead(
        db, ready, monkeypatch, stub_llm):
    """The wiring that makes the whole feature real: a lead clicks the link in
    an outreach email, books, and their sequence stops. Exercised through the
    actual router rather than the service, because the router is where the
    reference is read and where it would silently go missing."""
    import routers.bookings as bookings
    from sdr.repositories import leads as leads_repo
    from sdr.services import meetings as meetings_service

    monkeypatch.setattr(bookings, "db", db)
    # Outbound notifications are someone else's tested code.
    async def noop(*args, **kwargs):
        return None
    monkeypatch.setattr(bookings, "send_booking_confirmation_email", noop)
    monkeypatch.setattr(bookings, "whatsapp_notify_admin", noop)

    _, lead = await _seed_lead()
    await leads_repo.transition_stage(lead["id"], "contacted", actor="system")
    await _make_running_campaign([lead["id"]])

    settings = await bookings._get_or_create_settings()

    # Find a real open slot from the agency's own availability maths.
    slot = None
    for offset in range(1, 15):
        day = (datetime.now(timezone.utc) + timedelta(days=offset)).strftime("%Y-%m-%d")
        found = await bookings._slots_for_date(settings, day)
        if found:
            slot = found[0]
            break
    assert slot, "the default booking settings produced no open slot"

    payload = bookings.BookRequest(
        start_time=slot, name="Priya Kumar", email="owner@kumar1.example",
        notes=None, ref=meetings_service.booking_ref(lead["id"]),
    )
    result = await bookings.public_book(settings["slug"], payload)

    assert result["attached_to_lead"] is True

    refreshed = await leads_repo.get_lead(lead["id"])
    assert refreshed["stage"] == "meeting_scheduled"
    assert refreshed["meeting_booked_at"]

    # And nothing will email them again.
    active = await db["sdr_enrollments"].count_documents(
        {"lead_id": lead["id"], "status": "active"}
    )
    assert active == 0


@pytest.mark.asyncio
async def test_an_ordinary_public_booking_still_works_untouched(
        db, ready, monkeypatch, stub_llm):
    """Most bookings come from the website with no reference at all. The SDR
    hook must not have made those a special case."""
    import routers.bookings as bookings

    monkeypatch.setattr(bookings, "db", db)
    async def noop(*args, **kwargs):
        return None
    monkeypatch.setattr(bookings, "send_booking_confirmation_email", noop)
    monkeypatch.setattr(bookings, "whatsapp_notify_admin", noop)

    settings = await bookings._get_or_create_settings()
    slot = None
    for offset in range(1, 15):
        day = (datetime.now(timezone.utc) + timedelta(days=offset)).strftime("%Y-%m-%d")
        found = await bookings._slots_for_date(settings, day)
        if found:
            slot = found[0]
            break

    result = await bookings.public_book(settings["slug"], bookings.BookRequest(
        start_time=slot, name="Someone", email="someone@example.com",
    ))

    assert result["attached_to_lead"] is False
    assert result["meeting_id"]


# --- Queue health -------------------------------------------------------------

def test_a_stalled_queue_is_stated_rather_than_left_to_be_noticed():
    """If the pinger dies, work accumulates in silence - no error, no failed
    job, just a system that quietly stops."""
    from sdr.services.jobs import queue_health

    assert queue_health(None)["queue_stalled"] is False

    fresh = (BASE - timedelta(minutes=5)).isoformat()
    assert queue_health(fresh, now=BASE.isoformat())["queue_stalled"] is False

    stale = (BASE - timedelta(hours=3)).isoformat()
    result = queue_health(stale, now=BASE.isoformat())
    assert result["queue_stalled"] is True
    assert result["queue_lag_minutes"] == 180

    # Garbage must not crash a stats endpoint.
    assert queue_health("not-a-date")["queue_stalled"] is False

"""Meeting proposal maths: the pure part.

Two timezones have to agree before a slot is worth offering. The agency's
availability lives in `booking_settings` (one global config, agency-local);
the lead's working day comes from their company's country profile. A slot is
only proposable if it sits inside **both**. Offering 8am your time because it
is 3pm theirs is how a meeting gets booked and silently missed.

Nothing here talks to a database or a calendar. The agency's open slots are
passed in already computed - the booking module owns that query, and it is
the only thing that knows what is already booked.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sdr.domain import send_window

#: Don't propose anything sooner than this. A slot two hours out reads as
#: pushy and is usually already gone by the time the email is read.
MIN_LEAD_TIME_HOURS = 12

#: How many to put in an email. Three is the documented sweet spot: one looks
#: like an ultimatum, five reads as a scheduling problem to solve.
DEFAULT_SUGGESTIONS = 3

#: How long after a meeting's end before absence counts as a no-show. Short
#: enough to act on the same day, long enough to survive a late finish.
NO_SHOW_GRACE_MINUTES = 90


def _parse(value):
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed


def usable_slots(agency_slots, *, country: dict, timezone_name: str | None = None,
                 holidays=None, now=None, min_lead_hours: int = MIN_LEAD_TIME_HOURS,
                 duration_minutes: int = 30) -> list:
    """Agency-open slots that are also inside the lead's working day.

    `agency_slots` are ISO strings from the booking module - already filtered
    for what the agency has free. This adds the half nobody else checks: is
    the lead awake, and is it a working day where *they* are.
    """
    reference = _parse(now) if now else datetime.now(ZoneInfo("UTC"))
    earliest = reference + timedelta(hours=min_lead_hours)

    usable = []
    for raw in agency_slots or []:
        try:
            slot = _parse(raw)
        except (ValueError, TypeError):
            continue
        if slot < earliest:
            continue

        # Both ends must land inside the lead's day - a 30-minute call that
        # starts at 17:45 against a 18:00 close is not a real option.
        ok_start, _ = send_window.is_business_hours(
            slot, country, timezone_name=timezone_name, holidays=holidays
        )
        ok_end, _ = send_window.is_business_hours(
            slot + timedelta(minutes=duration_minutes), country,
            timezone_name=timezone_name, holidays=holidays,
        )
        if ok_start and ok_end:
            usable.append(slot)

    return sorted(usable)


def spread_suggestions(slots, *, count: int = DEFAULT_SUGGESTIONS,
                       timezone_name: str | None = None) -> list:
    """Pick `count` slots spread across different days.

    Three times on one afternoon is one option with extra steps. Taking the
    earliest slot from each distinct local day gives a real choice, and falls
    back to filling from what is left when there are not enough days.
    """
    if not slots:
        return []

    try:
        zone = ZoneInfo(timezone_name) if timezone_name else ZoneInfo("UTC")
    except Exception:
        zone = ZoneInfo("UTC")

    by_day = {}
    for slot in sorted(slots):
        key = slot.astimezone(zone).date()
        by_day.setdefault(key, []).append(slot)

    picked = [day_slots[0] for _, day_slots in sorted(by_day.items())][:count]

    if len(picked) < count:
        # Not enough distinct days; top up with the next unused times.
        remaining = [s for s in sorted(slots) if s not in picked]
        picked = sorted(picked + remaining[: count - len(picked)])

    return picked


def format_slot(slot, timezone_name: str | None = None) -> str:
    """A slot as a human would say it, in the reader's own timezone.

    The timezone is named explicitly. "Thursday 3pm" between two countries is
    an ambiguity that costs a missed meeting.
    """
    try:
        zone = ZoneInfo(timezone_name) if timezone_name else ZoneInfo("UTC")
    except Exception:
        zone = ZoneInfo("UTC")
        timezone_name = "UTC"

    local = _parse(slot).astimezone(zone)
    # %-d / %-I are not portable to Windows, so strip zeros by hand.
    day = local.strftime("%A %B ") + str(local.day)
    hour = local.strftime("%I:%M %p").lstrip("0")
    return f"{day}, {hour} ({timezone_name})"


def is_no_show(meeting: dict, *, now=None,
               grace_minutes: int = NO_SHOW_GRACE_MINUTES) -> bool:
    """A scheduled meeting whose time has passed without being resolved.

    Only ever true for a meeting still sitting in `scheduled`. Anything a
    human has already marked - completed, cancelled, no_show - is their call
    and is left alone.
    """
    if (meeting or {}).get("status") != "scheduled":
        return False

    end = meeting.get("end_time") or meeting.get("start_time")
    if not end:
        return False
    try:
        finished = _parse(end)
    except (ValueError, TypeError):
        return False

    reference = _parse(now) if now else datetime.now(ZoneInfo("UTC"))
    return reference >= finished + timedelta(minutes=grace_minutes)

"""Send windows, computed in the recipient's timezone.

Business hours are the recipient's, not ours. A campaign run from Pune
targeting London must land at 09:30 London time, and must not land on a UK
bank holiday. Getting this wrong is not merely rude - a 03:00 arrival reads
as spam to both the reader and the filter.

Timestamps in this codebase are ISO-8601 strings (see the Phase 0 report).
This module parses before comparing rather than relying on string ordering,
because lexicographic comparison across offsets is wrong: "2026-08-01T09:00
+05:30" sorts after "2026-08-01T08:00+00:00" but is two and a half hours
earlier.

Pure module: no I/O and no country literals - the caller passes a resolved
country profile from `sdr/config/countries.py`.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

#: Jitter bounds. A fixed cadence is a strong automation signal to filters,
#: and to anyone reading two of our emails side by side.
JITTER_MIN_SECONDS = 47
JITTER_MAX_SECONDS = 900


def _parse(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _zone(country: dict, override: str | None = None) -> ZoneInfo:
    """Resolve a timezone, falling back to the country's first.

    An unknown zone name falls back to UTC rather than raising: a malformed
    timezone on one lead should delay that lead, not break a whole campaign.
    """
    name = override or (country.get("timezones") or ["UTC"])[0]
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def _hhmm(value: str, fallback: tuple) -> tuple:
    try:
        hour, minute = value.split(":")
        return int(hour), int(minute)
    except (ValueError, AttributeError):
        return fallback


def is_business_hours(when: str | datetime, country: dict, *,
                      timezone_name: str | None = None,
                      holidays: list | None = None) -> tuple:
    """Whether a moment falls inside the recipient's working hours.

    Returns (ok, reason) so a deferral can be logged with a cause.
    """
    zone = _zone(country, timezone_name)
    local = _parse(when).astimezone(zone)

    hours = country.get("business_hours") or {}
    days = hours.get("days", [0, 1, 2, 3, 4])
    if local.weekday() not in days:
        return False, f"{local.strftime('%A')} is not a working day in {country.get('name', 'this market')}"

    if holidays and local.strftime("%m-%d") in holidays:
        return False, f"{local.strftime('%d %B')} is a public holiday"

    start = _hhmm(hours.get("start", "09:00"), (9, 0))
    end = _hhmm(hours.get("end", "17:00"), (17, 0))
    start_minutes = start[0] * 60 + start[1]
    end_minutes = end[0] * 60 + end[1]
    now_minutes = local.hour * 60 + local.minute

    if now_minutes < start_minutes:
        return False, f"{local.strftime('%H:%M')} is before business hours"
    if now_minutes >= end_minutes:
        return False, f"{local.strftime('%H:%M')} is after business hours"
    return True, f"{local.strftime('%a %H:%M')} local time"


def next_send_time(after: str | datetime, country: dict, *,
                   timezone_name: str | None = None,
                   holidays: list | None = None,
                   max_days: int = 14) -> datetime:
    """The next moment inside the recipient's business hours, at or after `after`.

    Walks forward in 15-minute steps rather than solving analytically -
    the calendar has enough special cases (weekends, holidays, markets whose
    working week is not Monday-Friday) that stepping is easier to verify than
    a closed form, and the loop is bounded.
    """
    zone = _zone(country, timezone_name)
    cursor = _parse(after).astimezone(zone)
    limit = cursor + timedelta(days=max_days)

    hours = country.get("business_hours") or {}
    start = _hhmm(hours.get("start", "09:00"), (9, 0))

    while cursor < limit:
        ok, _ = is_business_hours(cursor, country, timezone_name=timezone_name,
                                  holidays=holidays)
        if ok:
            return cursor

        # Jump straight to the next opening rather than stepping through the
        # whole night quarter-hour by quarter-hour.
        opening_today = cursor.replace(hour=start[0], minute=start[1],
                                       second=0, microsecond=0)
        if cursor < opening_today:
            cursor = opening_today
        else:
            cursor = (cursor + timedelta(days=1)).replace(
                hour=start[0], minute=start[1], second=0, microsecond=0
            )

    # Everything within the horizon is closed, which means the calendar is
    # misconfigured. Return the limit so the caller defers rather than
    # silently sending at a bad time.
    return limit


def jitter_seconds(seed: str, *, minimum: int = JITTER_MIN_SECONDS,
                   maximum: int = JITTER_MAX_SECONDS) -> int:
    """Deterministic per-message jitter.

    Derived from a hash rather than a random number so a message scheduled
    twice lands at the same time - re-running a scheduler must not shuffle
    everything, or idempotency is meaningless.
    """
    import hashlib

    digest = hashlib.sha256(str(seed).encode("utf-8")).digest()
    span = max(1, maximum - minimum)
    return minimum + (int.from_bytes(digest[:4], "big") % span)


def schedule(after: str | datetime, country: dict, *, seed: str,
             timezone_name: str | None = None,
             holidays: list | None = None) -> datetime:
    """Next business-hours slot, plus deterministic jitter.

    If jitter pushes past the close of business the result is re-anchored to
    the following window, so jitter can never be the thing that sends an
    email at 18:04.
    """
    base = next_send_time(after, country, timezone_name=timezone_name,
                          holidays=holidays)
    candidate = base + timedelta(seconds=jitter_seconds(seed))

    ok, _ = is_business_hours(candidate, country, timezone_name=timezone_name,
                              holidays=holidays)
    if not ok:
        return next_send_time(candidate, country, timezone_name=timezone_name,
                              holidays=holidays)
    return candidate

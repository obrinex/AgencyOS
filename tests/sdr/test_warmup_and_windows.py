"""Warm-up ramp, reputation thresholds and send-window maths.

All pure. These decide when and how much we send, and getting them wrong
burns a sending domain in a way that takes weeks to recover from.
"""

from datetime import datetime, timezone

import pytest

from sdr.config.countries import get_country
from sdr.domain import send_window, warmup


# --- Warm-up ------------------------------------------------------------------

def test_the_ramp_starts_small_and_increases():
    caps = [warmup.daily_cap(day, 200) for day in range(len(warmup.RAMP_ABSOLUTE))]
    assert caps[0] <= 5
    assert caps == sorted(caps), "the ramp must never step backwards"


def test_the_ramp_never_exceeds_the_target():
    """Raising the target mid-ramp must not cause a jump."""
    for day in range(40):
        assert warmup.daily_cap(day, 50) <= 50


def test_a_fully_warmed_identity_sends_its_target():
    assert warmup.daily_cap(60, 200) == 200
    assert warmup.is_warmed(60, 200)
    assert not warmup.is_warmed(0, 200)


def test_day_zero_of_a_negative_index_sends_nothing():
    assert warmup.daily_cap(-1, 200) == 0


# --- Health -------------------------------------------------------------------

def test_a_tiny_sample_does_not_promote_or_condemn():
    """Two bounces out of three sends is a 67% rate and means nothing."""
    status, reason = warmup.evaluate_health(sent_7d=3, bounces_7d=2, complaints_7d=0)
    assert status == warmup.WARMING
    assert "too few" in reason


def test_clean_sending_becomes_healthy():
    status, _ = warmup.evaluate_health(sent_7d=500, bounces_7d=2, complaints_7d=0)
    assert status == warmup.HEALTHY


def test_a_high_bounce_rate_throttles_then_pauses():
    throttled, _ = warmup.evaluate_health(sent_7d=100, bounces_7d=4, complaints_7d=0)
    assert throttled == warmup.THROTTLED
    paused, _ = warmup.evaluate_health(sent_7d=100, bounces_7d=8, complaints_7d=0)
    assert paused == warmup.PAUSED


def test_complaints_are_judged_an_order_of_magnitude_tighter_than_bounces():
    """0.1% complaints is as serious as 3% bounces."""
    bounce_ok, _ = warmup.evaluate_health(sent_7d=1000, bounces_7d=20, complaints_7d=0)
    complaint_bad, _ = warmup.evaluate_health(sent_7d=1000, bounces_7d=0, complaints_7d=2)
    assert bounce_ok == warmup.HEALTHY
    assert complaint_bad == warmup.THROTTLED


def test_a_blocked_identity_is_never_automatically_restored():
    """Whatever blocked it needs a human before more mail goes out under it."""
    status, _ = warmup.evaluate_health(
        sent_7d=1000, bounces_7d=0, complaints_7d=0, current_status=warmup.BLOCKED
    )
    assert status == warmup.BLOCKED


def test_effective_cap_reflects_status():
    assert warmup.effective_cap(day_index=60, target=200, status=warmup.HEALTHY) == 200
    assert warmup.effective_cap(day_index=60, target=200, status=warmup.PAUSED) == 0
    assert warmup.effective_cap(day_index=60, target=200, status=warmup.BLOCKED) == 0
    throttled = warmup.effective_cap(day_index=60, target=200, status=warmup.THROTTLED)
    assert 0 < throttled < 200


def test_throttling_never_reaches_zero():
    """Zero would be indistinguishable from paused and lose the signal about
    whether reduced volume is recovering."""
    assert warmup.throttled_cap(1) >= 1
    assert warmup.throttled_cap(0) >= 1


def test_reputation_score_degrades_before_a_threshold_trips():
    clean = warmup.reputation_score(sent_7d=1000, bounces_7d=0, complaints_7d=0)
    degrading = warmup.reputation_score(sent_7d=1000, bounces_7d=20, complaints_7d=0)
    assert clean == 1.0
    assert 0.0 < degrading < 1.0


# --- Send windows -------------------------------------------------------------

INDIA = get_country("IN")
US = get_country("US")

def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def test_business_hours_are_judged_in_the_recipients_timezone():
    """14:00 UTC is 19:30 in Kolkata - after hours - but 10:00 in New York."""
    moment = at("2026-08-03T14:00:00+00:00")  # a Monday
    india_ok, _ = send_window.is_business_hours(moment, INDIA)
    us_ok, _ = send_window.is_business_hours(moment, US, timezone_name="America/New_York")
    assert not india_ok
    assert us_ok


def test_weekends_are_refused():
    saturday = at("2026-08-01T06:00:00+00:00")
    ok, reason = send_window.is_business_hours(saturday, US, timezone_name="America/New_York")
    assert not ok
    assert "not a working day" in reason


def test_holidays_are_refused():
    ok, reason = send_window.is_business_hours(
        at("2026-01-26T06:00:00+00:00"), INDIA, holidays=["01-26"]
    )
    assert not ok
    assert "public holiday" in reason


def test_before_and_after_hours_are_refused_with_a_reason():
    early = at("2026-08-03T01:00:00+00:00")  # 06:30 IST
    late = at("2026-08-03T16:00:00+00:00")   # 21:30 IST
    assert "before business hours" in send_window.is_business_hours(early, INDIA)[1]
    assert "after business hours" in send_window.is_business_hours(late, INDIA)[1]


def test_next_send_time_lands_inside_business_hours():
    result = send_window.next_send_time(at("2026-08-03T01:00:00+00:00"), INDIA)
    ok, _ = send_window.is_business_hours(result, INDIA)
    assert ok


def test_next_send_time_skips_a_weekend():
    # 23:00 UTC on Friday is 19:00 in New York - after the 17:00 close, so
    # the next valid slot is Monday morning.
    friday_evening = at("2026-07-31T23:00:00+00:00")
    result = send_window.next_send_time(friday_evening, US, timezone_name="America/New_York")
    assert result.weekday() == 0  # Monday
    assert send_window.is_business_hours(result, US, timezone_name="America/New_York")[0]


def test_next_send_time_skips_a_holiday():
    result = send_window.next_send_time(
        at("2026-01-26T01:00:00+00:00"), INDIA, holidays=["01-26"]
    )
    assert result.strftime("%m-%d") != "01-26"


def test_jitter_is_deterministic_for_a_given_seed():
    """A message scheduled twice must land at the same time, or idempotency
    is meaningless."""
    assert send_window.jitter_seconds("lead-123") == send_window.jitter_seconds("lead-123")
    assert send_window.jitter_seconds("lead-123") != send_window.jitter_seconds("lead-456")


def test_jitter_stays_inside_its_bounds():
    values = [send_window.jitter_seconds(f"lead-{i}") for i in range(200)]
    assert all(send_window.JITTER_MIN_SECONDS <= v <= send_window.JITTER_MAX_SECONDS
               for v in values)
    assert len(set(values)) > 50, "jitter must actually spread sends"


def test_schedule_never_places_a_send_outside_business_hours():
    """Jitter must not be the thing that sends an email at 18:04."""
    for index in range(50):
        result = send_window.schedule(
            at("2026-08-03T13:20:00+00:00"), INDIA, seed=f"lead-{index}"
        )
        ok, reason = send_window.is_business_hours(result, INDIA)
        assert ok, f"seed {index} landed outside hours: {reason}"


def test_an_unknown_timezone_falls_back_rather_than_raising():
    """A malformed timezone on one lead should delay that lead, not break a
    whole campaign."""
    ok, _ = send_window.is_business_hours(
        at("2026-08-03T10:00:00+00:00"), INDIA, timezone_name="Mars/Olympus_Mons"
    )
    assert isinstance(ok, bool)


def test_string_timestamps_are_parsed_not_compared_lexicographically():
    """'+05:30' sorts after '+00:00' but is earlier in real time."""
    ok_ist, _ = send_window.is_business_hours("2026-08-03T09:00:00+05:30", INDIA)
    ok_utc, _ = send_window.is_business_hours("2026-08-03T09:00:00+00:00", INDIA)
    assert not ok_ist          # 09:00 IST is before the 10:00 start
    assert ok_utc              # 09:00 UTC is 14:30 IST, inside hours

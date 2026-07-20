"""Sequence rules and copy checks - the pure layer of the outreach engine.

Stop conditions get the most attention: a sequence that keeps sending after
a reply, an unsubscribe or a closed deal is the failure mode that costs the
agency its name.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sdr.domain import copy_checks, sequence  # noqa: E402


# --- Stop conditions ----------------------------------------------------------

def test_a_reply_stops_everything():
    """The goal state beats every other signal."""
    reason = sequence.evaluate_stop(
        {"replied_at": "2026-07-20T10:00:00+00:00", "stage": "contacted"}
    )
    assert reason == "replied"


def test_suppression_stops_the_sequence():
    assert sequence.evaluate_stop({"stage": "contacted"}, suppressed=True) == "unsubscribed"


@pytest.mark.parametrize("stage", ["won", "lost", "rejected", "archived"])
def test_a_closed_lead_stops_the_sequence(stage):
    assert sequence.evaluate_stop({"stage": stage}) == "lead_closed"


def test_a_stopped_campaign_stops_its_enrollments():
    assert sequence.evaluate_stop({"stage": "contacted"},
                                  campaign_status="stopped") == "campaign_stopped"


def test_a_paused_campaign_holds_rather_than_stops():
    """Pausing must be reversible - stopping the enrollment would lose its place."""
    assert sequence.evaluate_stop({"stage": "contacted"}, campaign_status="paused") is None
    assert sequence.is_on_hold("paused")
    assert not sequence.is_on_hold("running")


def test_an_open_healthy_lead_continues():
    assert sequence.evaluate_stop({"stage": "contacted"}) is None


def test_reply_outranks_a_closed_stage():
    """Priority order is part of the contract: 'replied' is the analytics
    truth even if the operator also closed the lead."""
    reason = sequence.evaluate_stop({"replied_at": "x", "stage": "won"})
    assert reason == "replied"


# --- Sequence validation ------------------------------------------------------

def test_the_shipped_default_sequence_is_valid():
    assert sequence.validate_sequence(sequence.DEFAULT_SEQUENCE) == []


def test_the_default_matches_the_quota_assumption():
    """Quota maths assume 3 touches per lead; the default must agree or the
    30/day figure quietly stops being true."""
    assert len(sequence.DEFAULT_SEQUENCE) == 3


def test_empty_and_oversized_sequences_are_rejected():
    assert sequence.validate_sequence([])
    too_many = [{"delay_days": 0 if i == 0 else 2, "instruction": "Write something useful here."}
                for i in range(6)]
    problems = sequence.validate_sequence(too_many, max_touches=5)
    assert any("exceeds" in p for p in problems)


def test_first_step_must_have_zero_delay():
    steps = [{"delay_days": 2, "instruction": "A perfectly reasonable instruction."}]
    problems = sequence.validate_sequence(steps)
    assert any("Step 1" in p for p in problems)


def test_followups_need_at_least_a_day():
    steps = [
        {"delay_days": 0, "instruction": "A perfectly reasonable instruction."},
        {"delay_days": 0, "instruction": "Another perfectly reasonable one."},
    ]
    problems = sequence.validate_sequence(steps)
    assert any("at least 1 day" in p for p in problems)


def test_all_problems_are_reported_at_once():
    """The UI shows the full list, not one complaint per save attempt."""
    steps = [{"delay_days": 5, "instruction": "hi"}]
    assert len(sequence.validate_sequence(steps)) >= 2


# --- Due computation ----------------------------------------------------------

def test_next_touch_adds_the_step_delay():
    steps = sequence.DEFAULT_SEQUENCE
    due = sequence.next_touch_at("2026-07-20T10:00:00+00:00", steps, 1)
    assert due == datetime.fromisoformat("2026-07-23T10:00:00+00:00")


def test_past_the_last_step_there_is_no_next_touch():
    assert sequence.next_touch_at("2026-07-20T10:00:00+00:00",
                                  sequence.DEFAULT_SEQUENCE, 3) is None


def test_is_due_compares_parsed_time_not_strings():
    enrollment = {"status": "active", "next_touch_at": "2026-07-20T10:00:00+05:30"}
    # 05:30 IST offset means this was due at 04:30 UTC.
    assert sequence.is_due(enrollment, "2026-07-20T05:00:00+00:00")


def test_inactive_enrollments_are_never_due():
    enrollment = {"status": "stopped", "next_touch_at": "2020-01-01T00:00:00+00:00"}
    assert not sequence.is_due(enrollment, "2026-07-20T00:00:00+00:00")


# --- Copy checks --------------------------------------------------------------

CLEAN = dict(
    subject="Your booking process at Kumar Dental",
    body=(
        "Hi - I looked at your site while researching Pune clinics. Patients "
        "can only book by phone, which usually means missed calls become "
        "missed appointments. We build small booking systems for practices "
        "like yours. Would it be useful if I sent a two-line summary of what "
        "that looks like?\n\nAmrit"
    ),
)


def test_clean_copy_passes():
    assert copy_checks.check_copy(**CLEAN) == []


def test_urls_are_blocked():
    """Text-only by design: a URL is an invented resource or a tracking link."""
    problems = copy_checks.check_copy(
        subject=CLEAN["subject"], body=CLEAN["body"] + " See https://example.com"
    )
    assert any("URL" in p for p in problems)


def test_template_placeholders_are_blocked():
    problems = copy_checks.check_copy(subject=CLEAN["subject"],
                                      body="Hi [First Name], quick thought...")
    assert any("placeholder" in p for p in problems)


def test_the_do_not_say_list_is_enforced_case_insensitively():
    problems = copy_checks.check_copy(
        subject=CLEAN["subject"],
        body=CLEAN["body"] + " This is a Game-Changer.",
        do_not_say=["game-changer"],
    )
    assert any("do-not-say" in p for p in problems)


def test_spam_phrases_are_flagged():
    problems = copy_checks.check_copy(subject="Act now - limited time",
                                      body=CLEAN["body"])
    assert any("Spam-trigger" in p for p in problems)


def test_overlong_bodies_and_subjects_are_flagged():
    assert any("words" in p for p in copy_checks.check_copy(
        subject=CLEAN["subject"], body="word " * 300))
    assert any("characters" in p for p in copy_checks.check_copy(
        subject="s" * 120, body=CLEAN["body"]))


def test_every_problem_is_reported_together():
    problems = copy_checks.check_copy(
        subject="ACT NOW!!!",
        body="Hi {name}, click here https://x.com! Guaranteed!!!",
        do_not_say=["guaranteed"],
    )
    assert len(problems) >= 4

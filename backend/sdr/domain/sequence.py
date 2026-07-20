"""Sequence and enrollment logic - the rules of a multi-touch campaign.

An *enrollment* is one lead's journey through one campaign's sequence. This
module owns when the next touch is due, and - more importantly - when to
stop. The stop conditions are the safety-critical part: a sequence that keeps
sending after a reply, an unsubscribe, or a closed deal reads as a bot that
does not listen, which is worse for the agency's name than never writing.

Stop conditions are evaluated *every time* an enrollment is considered, not
only when the state changes, because the thing that changed (a stage move, a
manual reply mark, a suppression) usually happened elsewhere and nothing
notified the enrollment.

Pure module: no I/O. The caller assembles the lead/campaign state.
"""

from datetime import datetime, timedelta

# --- Enrollment lifecycle -----------------------------------------------------

ACTIVE = "active"
COMPLETED = "completed"   # every step sent - the sequence ran its course
STOPPED = "stopped"       # ended early, with a reason

ENROLLMENT_STATUSES = (ACTIVE, COMPLETED, STOPPED)

#: Reasons an enrollment ends early. Closed taxonomy so campaign analytics can
#: group them; free text goes in the note field.
STOP_REASONS = (
    "replied",            # the lead answered - the goal, not a failure
    "unsubscribed",       # suppression hit; permanent
    "bounced",            # address is dead; no point continuing
    "lead_closed",        # stage moved to won/lost/rejected/archived
    "campaign_stopped",   # the whole campaign was stopped
    "compliance",         # no lawful basis to contact this recipient
    "manual",             # an operator pulled this lead out
    "wrong_person",       # they don't own this - re-research the contact,
                          # don't write the company off
)

#: Lead stages that end an enrollment. `won` and `lost` are obvious; `cold`
#: is deliberately NOT here - a lead an operator parked as cold mid-sequence
#: still gets pulled via lead_closed only if they archive it.
CLOSING_STAGES = ("won", "lost", "rejected", "archived")


def evaluate_stop(lead: dict, *, suppressed: bool = False,
                  campaign_status: str = "running") -> str | None:
    """Whether this enrollment must stop now. Returns a STOP_REASON or None.

    Ordered by how definitive the signal is: a reply beats everything (it is
    the *goal*), suppression is permanent, a closed lead is a business
    decision, a paused campaign is temporary and returns None (hold, not
    stop - pausing must be reversible without losing enrollment state).
    """
    if lead.get("replied_at"):
        return "replied"
    if suppressed:
        return "unsubscribed"
    if lead.get("stage") in CLOSING_STAGES:
        return "lead_closed"
    if campaign_status in ("stopped", "archived"):
        return "campaign_stopped"
    return None


def is_on_hold(campaign_status: str) -> bool:
    """Paused campaigns hold their enrollments without stopping them."""
    return campaign_status == "paused"


# --- Sequences ----------------------------------------------------------------
#
# A sequence is an ordered list of steps. Each step carries a *writing
# instruction* for the personalization agent rather than a fixed template -
# the copy is generated per lead, grounded in that lead's research and
# signals. `delay_days` is measured from the previous step's send.

MAX_STEPS = 5          # matches settings.max_touches_per_lead's ceiling
MAX_DELAY_DAYS = 30

#: The shipped default: three touches over eight days. Deliberately short and
#: low-pressure - at 30 new leads/day on a free email plan, restraint is both
#: the deliverability play and the brand play.
DEFAULT_SEQUENCE = [
    {
        "delay_days": 0,
        "goal": "opener",
        "instruction": (
            "Introduce yourself in one short line, then lead with the single "
            "most severe gap detected on their website and what it is likely "
            "costing them. One soft question as the close - no meeting ask yet."
        ),
    },
    {
        "delay_days": 3,
        "goal": "different_angle",
        "instruction": (
            "Do not repeat the first email or apologise for following up. "
            "Pick a DIFFERENT detected gap or a talking point from the "
            "research and make one concrete, specific observation about their "
            "business. Close by offering one clear next step."
        ),
    },
    {
        "delay_days": 5,
        "goal": "breakup",
        "instruction": (
            "Two sentences maximum. Acknowledge they are busy, say you will "
            "not write again, and leave the door open with a single low-"
            "pressure line. No guilt, no 'just bumping this'."
        ),
    },
]


def validate_sequence(steps: list, *, max_touches: int = MAX_STEPS) -> list:
    """Check a sequence definition. Returns a list of problems, empty if fine.

    Returns problems rather than raising so the UI can show all of them at
    once instead of one per save attempt.
    """
    problems = []
    if not steps:
        problems.append("A sequence needs at least one step.")
        return problems
    if len(steps) > max_touches:
        problems.append(
            f"{len(steps)} steps exceeds the maximum of {max_touches} touches "
            "per lead."
        )
    for index, step in enumerate(steps):
        label = f"Step {index + 1}"
        instruction = (step.get("instruction") or "").strip()
        if len(instruction) < 10:
            problems.append(f"{label}: the writing instruction is too short to guide a draft.")
        delay = step.get("delay_days")
        if not isinstance(delay, (int, float)) or delay < 0 or delay > MAX_DELAY_DAYS:
            problems.append(f"{label}: delay_days must be between 0 and {MAX_DELAY_DAYS}.")
        if index == 0 and delay not in (0, None):
            # The first touch is paced by the daily new-lead cap, not a delay.
            problems.append("Step 1: the first touch's delay must be 0 - pacing is handled by the daily new-lead cap.")
        if index > 0 and (not isinstance(delay, (int, float)) or delay < 1):
            problems.append(f"{label}: follow-ups need at least 1 day of delay.")
    return problems


def next_touch_at(previous_sent_at: str | datetime, steps: list,
                  next_step_index: int) -> datetime | None:
    """When the next step becomes due, or None if the sequence is finished.

    Parsed-then-added rather than string math - timestamps in this codebase
    are ISO strings and only UTC ones compare lexicographically.
    """
    if next_step_index >= len(steps):
        return None
    base = (previous_sent_at if isinstance(previous_sent_at, datetime)
            else datetime.fromisoformat(previous_sent_at))
    delay = steps[next_step_index].get("delay_days") or 0
    return base + timedelta(days=delay)


def is_due(enrollment: dict, now: str | datetime) -> bool:
    """Whether an active enrollment's next touch is due."""
    if enrollment.get("status") != ACTIVE:
        return False
    due_at = enrollment.get("next_touch_at")
    if not due_at:
        return False
    now_dt = now if isinstance(now, datetime) else datetime.fromisoformat(now)
    due_dt = due_at if isinstance(due_at, datetime) else datetime.fromisoformat(due_at)
    return due_dt <= now_dt


def is_final_step(steps: list, step_index: int) -> bool:
    return step_index >= len(steps) - 1

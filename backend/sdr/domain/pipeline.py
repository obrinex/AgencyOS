"""Lead pipeline state machine.

The eleven stages below are the ones already stored in `leads.stage` and
rendered by the frontend's STAGE_CONFIG (crm.py:15-16). Renaming any of them
would invalidate every existing lead document and break CRMPipeline.jsx, so
the SDR module adopts them as-is and adds only the two the spec genuinely
needs: `interested` (a reply showed intent, but no meeting yet) and
`archived` (removed from the working set without claiming an outcome).

Pure module: no I/O, no imports outside the standard library.
"""

# --- Stages ------------------------------------------------------------------

PROSPECT = "prospect"
CONTACTED = "contacted"
QUALIFIED = "qualified"
INTERESTED = "interested"
DISCOVERY = "discovery"
MEETING_SCHEDULED = "meeting_scheduled"
PROPOSAL_SENT = "proposal_sent"
NEGOTIATION = "negotiation"
WON = "won"
LOST = "lost"
REJECTED = "rejected"
COLD = "cold"
ARCHIVED = "archived"

STAGES = [
    PROSPECT, CONTACTED, QUALIFIED, INTERESTED, DISCOVERY, MEETING_SCHEDULED,
    PROPOSAL_SENT, NEGOTIATION, WON, LOST, REJECTED, COLD, ARCHIVED,
]

#: Stages that count as live pipeline for forecasting and work queues.
OPEN_STAGES = [
    PROSPECT, CONTACTED, QUALIFIED, INTERESTED, DISCOVERY,
    MEETING_SCHEDULED, PROPOSAL_SENT, NEGOTIATION,
]

#: Nothing may leave these except a deliberate human restore.
TERMINAL_STAGES = [WON]

#: Closed but not terminal - a lost or cold lead can be re-engaged later.
CLOSED_STAGES = [WON, LOST, REJECTED, COLD, ARCHIVED]

#: Every stage a lead can reach without a human override.
_TRANSITIONS = {
    PROSPECT: {QUALIFIED, CONTACTED, REJECTED, COLD, ARCHIVED},
    QUALIFIED: {CONTACTED, DISCOVERY, REJECTED, COLD, ARCHIVED},
    # Self-transition is legal and meaningful: it is how a follow-up touch
    # re-stamps stage_entered_at without pretending progress was made.
    CONTACTED: {CONTACTED, INTERESTED, DISCOVERY, MEETING_SCHEDULED, LOST, COLD, ARCHIVED},
    INTERESTED: {DISCOVERY, MEETING_SCHEDULED, PROPOSAL_SENT, NEGOTIATION, LOST, COLD, ARCHIVED},
    DISCOVERY: {MEETING_SCHEDULED, PROPOSAL_SENT, INTERESTED, LOST, ARCHIVED},
    # A no-show drops back to `interested` for re-engagement rather than
    # burning the lead outright.
    MEETING_SCHEDULED: {DISCOVERY, PROPOSAL_SENT, NEGOTIATION, INTERESTED, LOST, ARCHIVED},
    PROPOSAL_SENT: {NEGOTIATION, WON, LOST, ARCHIVED},
    # Back to proposal_sent covers a revised proposal during negotiation.
    NEGOTIATION: {WON, LOST, PROPOSAL_SENT, ARCHIVED},
    WON: set(),
    LOST: {COLD, ARCHIVED},
    REJECTED: {COLD, ARCHIVED},
    COLD: {PROSPECT, QUALIFIED, CONTACTED, ARCHIVED},
    ARCHIVED: {PROSPECT},
}

#: Reasons a lead can leave the pipeline without a win. Kept as a closed
#: taxonomy so funnel analytics can group them; free text goes in the note.
LOST_REASONS = [
    "no_response", "not_interested", "no_budget", "bad_timing",
    "chose_competitor", "not_a_fit", "unsubscribed", "invalid_contact",
    "duplicate", "other",
]

#: Who caused a transition. Recorded on every move for the audit trail.
ACTORS = ["ai", "user", "system"]


def is_valid_stage(stage: str) -> bool:
    return stage in STAGES


def is_open(stage: str) -> bool:
    return stage in OPEN_STAGES


def is_terminal(stage: str) -> bool:
    return stage in TERMINAL_STAGES


def allowed_transitions(from_stage: str) -> set:
    """Stages reachable from `from_stage` without a human override."""
    return set(_TRANSITIONS.get(from_stage, set()))


def can_transition(from_stage: str, to_stage: str, actor: str = "system") -> bool:
    """Whether this move is permitted.

    A human may override the graph to correct a mistake - the spec requires
    every automatic transition to be reversible by a person. Agents and system
    jobs get no such latitude: they follow the graph exactly. Nobody, human
    included, may move a lead out of a terminal stage, because `won` has
    already created a client, project and draft invoice downstream.
    """
    if not is_valid_stage(from_stage) or not is_valid_stage(to_stage):
        return False
    if from_stage in TERMINAL_STAGES:
        return False
    if to_stage in allowed_transitions(from_stage):
        return True
    return actor == "user" and to_stage not in TERMINAL_STAGES


def is_override(from_stage: str, to_stage: str) -> bool:
    """True when the move is only legal because a human asked for it.

    Services use this to flag the resulting activity entry, so an audit can
    distinguish 'the machine followed its rules' from 'someone intervened'.
    """
    return (
        is_valid_stage(from_stage)
        and is_valid_stage(to_stage)
        and from_stage not in TERMINAL_STAGES
        and to_stage not in allowed_transitions(from_stage)
    )


def validate_transition(from_stage: str, to_stage: str, actor: str = "system") -> None:
    """Raise if the move is illegal. Callers that prefer a bool use can_transition."""
    from sdr.errors import IllegalTransitionError, ValidationError

    if not is_valid_stage(from_stage):
        raise ValidationError(f"Unknown stage '{from_stage}'.")
    if not is_valid_stage(to_stage):
        raise ValidationError(f"Unknown stage '{to_stage}'.")
    if actor not in ACTORS:
        raise ValidationError(f"Unknown actor '{actor}'.")
    if not can_transition(from_stage, to_stage, actor):
        raise IllegalTransitionError(from_stage, to_stage)


def requires_reason(to_stage: str) -> bool:
    """Stages that must not be entered without an explanation."""
    return to_stage in (LOST, REJECTED)


def time_in_stage_days(stage_entered_at: str, now_iso_str: str) -> float | None:
    """Days between two ISO-8601 UTC timestamps, for funnel analytics.

    Returns None rather than raising on unparseable input - a malformed
    timestamp on one lead should never break a whole dashboard aggregate.
    """
    from datetime import datetime

    try:
        entered = datetime.fromisoformat(stage_entered_at)
        now = datetime.fromisoformat(now_iso_str)
    except (TypeError, ValueError):
        return None
    return (now - entered).total_seconds() / 86400.0

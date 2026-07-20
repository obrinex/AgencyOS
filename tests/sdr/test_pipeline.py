"""Lead pipeline state machine.

Covers every legal and illegal transition, per the spec's testing table.
"""

import pytest

from sdr.domain import pipeline as p
from sdr.errors import IllegalTransitionError, ValidationError


def test_every_stage_has_a_transition_entry():
    """A stage missing from the graph would silently become a dead end."""
    for stage in p.STAGES:
        assert stage in p._TRANSITIONS, f"{stage} has no transitions defined"


def test_transitions_only_target_known_stages():
    for stage, targets in p._TRANSITIONS.items():
        for target in targets:
            assert p.is_valid_stage(target), f"{stage} -> unknown stage {target}"


def test_existing_crm_stages_are_all_preserved():
    """The eleven stages already stored in leads.stage must remain valid.

    Dropping one would orphan every lead sitting in it and break the CRM
    pipeline board, which reads the same field.
    """
    existing = [
        "prospect", "contacted", "qualified", "discovery", "meeting_scheduled",
        "proposal_sent", "negotiation", "won", "lost", "rejected", "cold",
    ]
    for stage in existing:
        assert p.is_valid_stage(stage)


# --- Legal transitions --------------------------------------------------------

@pytest.mark.parametrize("from_stage,to_stage", [
    (p.PROSPECT, p.QUALIFIED),
    (p.PROSPECT, p.CONTACTED),
    (p.QUALIFIED, p.CONTACTED),
    (p.CONTACTED, p.INTERESTED),
    (p.CONTACTED, p.CONTACTED),          # follow-up touch
    (p.INTERESTED, p.MEETING_SCHEDULED),
    (p.MEETING_SCHEDULED, p.PROPOSAL_SENT),
    (p.MEETING_SCHEDULED, p.INTERESTED),  # no-show re-engagement
    (p.PROPOSAL_SENT, p.NEGOTIATION),
    (p.PROPOSAL_SENT, p.WON),
    (p.NEGOTIATION, p.WON),
    (p.NEGOTIATION, p.PROPOSAL_SENT),     # revised proposal
    (p.LOST, p.COLD),
    (p.COLD, p.PROSPECT),                 # re-engagement
    (p.ARCHIVED, p.PROSPECT),             # restore
])
def test_legal_transitions(from_stage, to_stage):
    assert p.can_transition(from_stage, to_stage, actor="ai")
    p.validate_transition(from_stage, to_stage, actor="ai")


def test_every_open_stage_can_be_archived():
    for stage in p.OPEN_STAGES:
        assert p.can_transition(stage, p.ARCHIVED, actor="ai"), stage


# --- Illegal transitions ------------------------------------------------------

@pytest.mark.parametrize("from_stage,to_stage", [
    (p.PROSPECT, p.WON),              # cannot skip the entire funnel
    (p.PROSPECT, p.PROPOSAL_SENT),
    (p.CONTACTED, p.WON),
    (p.QUALIFIED, p.NEGOTIATION),
    (p.WON, p.LOST),                  # terminal
    (p.WON, p.NEGOTIATION),
    (p.WON, p.ARCHIVED),
])
def test_illegal_transitions_for_agents(from_stage, to_stage):
    assert not p.can_transition(from_stage, to_stage, actor="ai")
    with pytest.raises(IllegalTransitionError):
        p.validate_transition(from_stage, to_stage, actor="ai")


def test_won_is_terminal_even_for_humans():
    """`won` fires run_won_automation, creating a client, project and invoice.

    Reversing it in the SDR module would leave those downstream records
    orphaned, so nobody may move a lead out of it here.
    """
    for stage in p.STAGES:
        assert not p.can_transition(p.WON, stage, actor="user"), stage


def test_unknown_stages_are_rejected():
    assert not p.can_transition("nonsense", p.WON)
    assert not p.can_transition(p.PROSPECT, "nonsense")
    with pytest.raises(ValidationError):
        p.validate_transition("nonsense", p.PROSPECT)
    with pytest.raises(ValidationError):
        p.validate_transition(p.PROSPECT, "nonsense")


def test_unknown_actor_is_rejected():
    with pytest.raises(ValidationError):
        p.validate_transition(p.PROSPECT, p.QUALIFIED, actor="robot")


# --- Human override -----------------------------------------------------------

def test_human_may_override_the_graph():
    """The spec requires every automatic transition to be human-reversible."""
    assert not p.can_transition(p.PROSPECT, p.NEGOTIATION, actor="ai")
    assert p.can_transition(p.PROSPECT, p.NEGOTIATION, actor="user")


def test_human_override_may_not_reach_a_terminal_stage():
    """A human can correct a stage, but not fabricate a win.

    Reaching `won` must go through the pipeline so the downstream automation
    fires with the right preconditions.
    """
    assert not p.can_transition(p.PROSPECT, p.WON, actor="user")


def test_is_override_flags_only_off_graph_moves():
    assert p.is_override(p.PROSPECT, p.NEGOTIATION)
    assert not p.is_override(p.PROSPECT, p.QUALIFIED)
    assert not p.is_override(p.WON, p.LOST)  # forbidden outright, not an override


# --- Helpers ------------------------------------------------------------------

def test_open_and_closed_stages_partition_cleanly():
    assert not set(p.OPEN_STAGES) & set(p.CLOSED_STAGES)
    assert set(p.OPEN_STAGES) | set(p.CLOSED_STAGES) == set(p.STAGES)


def test_requires_reason():
    assert p.requires_reason(p.LOST)
    assert p.requires_reason(p.REJECTED)
    assert not p.requires_reason(p.WON)


def test_time_in_stage_days():
    days = p.time_in_stage_days("2026-07-01T00:00:00+00:00", "2026-07-11T00:00:00+00:00")
    assert days == pytest.approx(10.0)


def test_time_in_stage_returns_none_on_bad_input():
    """One malformed timestamp must not break a whole dashboard aggregate."""
    assert p.time_in_stage_days("not-a-date", "2026-07-11T00:00:00+00:00") is None
    assert p.time_in_stage_days(None, "2026-07-11T00:00:00+00:00") is None

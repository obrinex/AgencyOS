"""The lead pipeline's stage vocabulary. One definition, imported everywhere.

Before this file the same list existed five times, and no two copies agreed:

  - `routers/crm.py`              11 stages - what PATCH /leads/{id}/stage accepted
  - `routers/dashboard.py`         8 stages - the dashboard funnel
  - `velliom/verbs/reads.py`       8 stages - the agent's funnel + write validation
  - `sdr/domain/pipeline.py`      13 stages - the SDR state machine
  - `frontend/lib/statusConfig.js`12 stages - the board's columns

The disagreements were not cosmetic. The frontend offered an `interested`
column that the CRM's own PATCH endpoint rejected with a 400, so dragging a
card there failed; the SDR engine set `archived` on leads that then vanished
from a board still counting them in its header; and Velliom refused `cold`
outright. Three subsystems could each write a stage the other two would not
accept, on rows in a single shared collection.

Adding a stage now means adding it here, plus a label in `statusConfig.js`
(the board renders columns from that map, so a stage with no entry there is
silently dropped from the UI) and a transition rule in `sdr/domain/pipeline.py`
if the SDR engine should be able to reach it on its own.

Pure module: no imports, no I/O. Everything else may import it freely.
"""

# --- The stages ---------------------------------------------------------------

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

#: Every stage a lead may legally hold. Order matters: `statusConfig.js` holds
#: the same keys in the same order and the board renders one column per key, so
#: this is also the left-to-right order of the pipeline board. A test asserts
#: the two stay in step.
STAGES = [
    PROSPECT, CONTACTED, QUALIFIED, INTERESTED, DISCOVERY, MEETING_SCHEDULED,
    PROPOSAL_SENT, NEGOTIATION, WON, LOST, REJECTED, COLD, ARCHIVED,
]

#: The forward funnel, for conversion reporting. Ends at `won` because a funnel
#: chart plots progress toward a sale; the closed-without-a-sale stages are
#: counted separately rather than drawn as a final bar.
FUNNEL_ORDER = [
    PROSPECT, CONTACTED, QUALIFIED, INTERESTED, DISCOVERY, MEETING_SCHEDULED,
    PROPOSAL_SENT, NEGOTIATION, WON,
]

#: Live pipeline: still workable, no outcome claimed yet.
OPEN_STAGES = [
    PROSPECT, CONTACTED, QUALIFIED, INTERESTED, DISCOVERY, MEETING_SCHEDULED,
    PROPOSAL_SENT, NEGOTIATION,
]

#: Closed without a sale. `archived` sits here too - it claims no outcome, but
#: the lead has left the working set, so counting it as open would overstate
#: the pipeline.
CLOSED_LOST = (LOST, REJECTED, COLD, ARCHIVED)

#: Stages nothing may leave - not an agent, not a job, not a person clicking in
#: the dashboard. `won` has already produced a client, a project and a draft
#: invoice through `run_won_automation`; moving back out strands those records,
#: and moving in again mints a second set of them.
TERMINAL_STAGES = (WON,)

#: Stages a lead may be *created* in. Creating one directly as `won` would skip
#: the won automation entirely, leaving a win with no client behind it.
CREATABLE_STAGES = [s for s in STAGES if s not in TERMINAL_STAGES]


def is_valid(stage: str) -> bool:
    return stage in STAGES


def is_terminal(stage: str) -> bool:
    return stage in TERMINAL_STAGES


def joined(stages=None) -> str:
    """Comma-separated list, for error messages that tell the caller its options."""
    return ", ".join(stages if stages is not None else STAGES)

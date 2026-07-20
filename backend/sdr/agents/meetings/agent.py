"""The meeting proposal agent.

**Deliberately not an LLM agent.** Every other outreach message in this module
goes through a model, so the exception needs justifying: this message consists
almost entirely of specific times and a URL, and those are exactly the two
things a model is worst at. A hallucinated time is a missed meeting; a
hallucinated link is a dead end with no error message. There is nothing here
worth a model's judgement and quite a lot worth its errors.

So the times come from `services/meetings.propose_slots` (deterministic,
timezone-correct on both sides) and the copy is a template. It reads slightly
plainer than the cold emails. That is an acceptable trade for a message whose
entire job is to be unambiguous.

The agent drafts; it does not send. The draft lands in the same approval queue
as everything else, because a message proposing a real commitment on a real
calendar is not the place to skip the human.
"""

import logging

from sdr.agents.base.agent import Agent, AgentContext
from sdr.domain import pipeline
from sdr.errors import ValidationError
from sdr.repositories import leads as leads_repo
from sdr.services import meetings as meetings_service

logger = logging.getLogger(__name__)


def build_proposal(*, first_name: str | None, labels: list,
                   booking_url: str | None, sender_name: str) -> tuple:
    """The proposal email. Returns (subject, body).

    Times are listed as given - already formatted in the lead's own timezone
    with the zone named, because "Thursday 3pm" across two countries is an
    ambiguity that costs the meeting it was meant to arrange.
    """
    greeting = f"Hi {first_name}," if first_name else "Hi,"

    if labels:
        times = "\n".join(f"- {label}" for label in labels)
        offer = f"Any of these work on my side:\n\n{times}\n"
        if booking_url:
            offer += (
                f"\nIf none of those fit, you can pick any time that does here:\n"
                f"{booking_url}\n"
            )
    elif booking_url:
        # No overlapping slot inside both working days. Say so plainly rather
        # than inventing a time that does not exist.
        offer = (
            f"Rather than guess at a time across timezones, here is my calendar "
            f"— grab whatever suits:\n{booking_url}\n"
        )
    else:
        offer = "What does your week look like? Happy to work around you.\n"

    body = (
        f"{greeting}\n\n"
        f"Glad this is worth a conversation.\n\n"
        f"{offer}\n"
        f"Either way, 20 minutes is plenty.\n\n"
        f"{sender_name}"
    )
    return "Times for a quick call", body


class MeetingProposalAgent(Agent):
    key = "meeting_proposal"
    version = "1.0.0"
    description = "Proposes call times in the lead's timezone and drafts the reply."
    category = "sales"
    surface = "AI SDR → Meetings"
    queue = "personalization"
    cost_ceiling_usd = 0.001   # no LLM; the ceiling machinery still runs
    timeout_ms = 30_000

    async def execute(self, payload: dict, ctx: AgentContext) -> dict:
        lead_id = payload.get("lead_id")
        if not lead_id:
            raise ValidationError("lead_id is required")

        lead = await leads_repo.get_lead(lead_id)

        # Only for leads who have actually shown interest. Proposing a call to
        # someone who has not answered is the cold-email equivalent of asking
        # to move in on a first date.
        stage = lead.get("stage") or pipeline.PROSPECT
        if not pipeline.can_transition(stage, pipeline.MEETING_SCHEDULED, "ai"):
            return {"skipped": True,
                    "reason": f"a lead in '{stage}' cannot book a meeting"}

        if lead.get("meeting_booked_at"):
            return {"skipped": True, "reason": "this lead already booked"}

        proposal = await meetings_service.propose_slots(lead_id)

        if not proposal["slots"] and not proposal["booking_url"]:
            # Nothing to offer and no way to self-serve. Flagged rather than
            # sending an email that asks a question it cannot answer.
            ctx.flag("no_bookable_slots", {
                "agency_slots": proposal["agency_slot_count"],
                "usable_slots": proposal["usable_slot_count"],
            })

        if proposal["agency_slot_count"] and not proposal["usable_slot_count"]:
            # The agency is free but never while the lead is at work. A real
            # configuration problem, and invisible unless it is said out loud.
            ctx.flag("no_timezone_overlap", {
                "lead_timezone": proposal["timezone"],
                "agency_slots": proposal["agency_slot_count"],
            })

        subject, body = build_proposal(
            first_name=(lead.get("contact_name") or "").split(" ")[0] or None,
            labels=proposal["labels"],
            booking_url=proposal["booking_url"],
            sender_name=payload.get("sender_name") or "Amrit",
        )

        return {
            "lead_id": lead_id,
            "subject": subject,
            "body": body,
            "slots": proposal["slots"],
            "labels": proposal["labels"],
            "timezone": proposal["timezone"],
            "booking_url": proposal["booking_url"],
        }

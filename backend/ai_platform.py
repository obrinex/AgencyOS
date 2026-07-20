"""Platform-wide AI agent registry and run recording.

The agent runtime was built inside the SDR module, but nothing about it is
sales-specific: run recording, cost ceilings, guardrails, retries and the
free-provider fallback chain are useful to any AI feature in this app. This
module is the platform-level view over all of it.

Two kinds of thing appear in the monitor:

1. **Agents** - full `Agent` subclasses run by the job queue, with schemas,
   guardrails and retries. Currently the five sales agents.
2. **Assistants** - the host app's pre-existing AI endpoints (`routers/ai.py`,
   `routers/emails.py`, `routers/leadfinder.py`). These are not agents and are
   not being rewritten as such; they are simply instrumented so their runs,
   costs and failures show up alongside everything else.

That second category is the point. An "AI monitor" that only knows about the
newest module is not a monitor - it is a module page. Recording the existing
features costs one decorator each and makes the view genuinely complete.

Implementation note: the agent code still lives under `sdr/agents/`. Moving it
to a top-level package is the right eventual shape but is a large rename
against a live deployment, so it is deferred - see ADR 0005. Categories and
this facade give the correct model now; the directory catches up later.
"""

import logging
import time
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# --- Categories ---------------------------------------------------------------
#
# What the AI is being used *for*, independent of which module implements it.
# The monitor groups by these.

CATEGORIES = {
    "sales": {
        "label": "Sales & outreach",
        "description": "Finding, researching, scoring and contacting prospects.",
    },
    "content": {
        "label": "Content & writing",
        "description": "Drafting emails, proposals and client-facing copy.",
    },
    "delivery": {
        "label": "Delivery & projects",
        "description": "Summarising meetings, briefs and project context.",
    },
    "support": {
        "label": "Support",
        "description": "Answering questions and handling inbound tickets.",
    },
    "insight": {
        "label": "Insight & analysis",
        "description": "Reporting, analytics and the CRM assistant.",
    },
}

DEFAULT_CATEGORY = "insight"


# --- Assistants: the host app's existing AI features ---------------------------
#
# Declared rather than discovered, so the catalogue states what exists even
# before any of them has been run.

ASSISTANTS = [
    {
        "key": "crm_assistant",
        "label": "CRM assistant",
        "category": "insight",
        "description": "Answers questions about leads, clients and invoices in chat.",
        "surface": "AI Assistant panel",
        "endpoint": "/api/ai/chat",
    },
    {
        "key": "email_generator",
        "label": "Email writer",
        "category": "content",
        "description": "Drafts an email from an instruction and a tone.",
        "surface": "Emails page",
        "endpoint": "/api/ai/generate-email",
    },
    {
        "key": "proposal_generator",
        "label": "Proposal writer",
        "category": "content",
        "description": "Drafts a proposal from a brief.",
        "surface": "Proposals page",
        "endpoint": "/api/ai/generate-proposal",
    },
    {
        "key": "meeting_summarizer",
        "label": "Meeting summariser",
        "category": "delivery",
        "description": "Turns meeting notes into a summary and action items.",
        "surface": "Calendar",
        "endpoint": "/api/ai/summarize-meeting",
    },
    {
        "key": "lead_reply_drafter",
        "label": "Lead reply drafter",
        "category": "sales",
        "description": "Drafts a reply to a lead from their CRM history.",
        "surface": "Lead detail",
        "endpoint": "/api/ai/leads/{id}/draft-reply",
    },
    {
        "key": "leadfinder_pitch",
        "label": "Lead Finder pitch writer",
        "category": "sales",
        "description": "Writes a cold pitch for a business found via OpenStreetMap.",
        "surface": "AI Lead Finder",
        "endpoint": "/api/leadfinder/analyze",
    },
]

ASSISTANTS_BY_KEY = {a["key"]: a for a in ASSISTANTS}


@asynccontextmanager
async def record_assistant(key: str, *, user_id: str | None = None,
                           entity_type: str | None = None,
                           entity_id: str | None = None,
                           payload: dict | None = None):
    """Record one assistant invocation into the same run log as the agents.

    Deliberately forgiving: monitoring must never be able to break the feature
    it monitors. Every failure path here is swallowed and logged, so a problem
    writing the run cannot turn a working AI feature into a 500.

        async with record_assistant("email_generator", user_id=user["id"]) as run:
            result = await do_the_work()
            run.tokens(prompt_tokens, completion_tokens)
    """
    from sdr.repositories import agent_runs as runs_repo

    meta = ASSISTANTS_BY_KEY.get(key, {})
    started = time.monotonic()

    class _Recorder:
        def __init__(self):
            self.input_tokens = 0
            self.output_tokens = 0
            self.model = None
            self.provider = None

        def tokens(self, prompt: int = 0, completion: int = 0):
            self.input_tokens += int(prompt or 0)
            self.output_tokens += int(completion or 0)

        def used(self, model: str | None = None, provider: str | None = None):
            self.model = model or self.model
            self.provider = provider or self.provider

    recorder = _Recorder()
    run_id = None
    try:
        run_id = await runs_repo.start_run(
            agent_key=key,
            version=meta.get("version", "host"),
            trigger="manual",
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
        )
    except Exception as exc:
        logger.warning("Could not open a run record for %s: %s", key, exc)

    try:
        yield recorder
    except Exception as exc:
        if run_id:
            try:
                from sdr.agents.base.cost import estimate_cost
                await runs_repo.finish_run(
                    run_id, status="failed",
                    model_used=recorder.model, provider_used=recorder.provider,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    error_type=type(exc).__name__, error_message=str(exc),
                    cost={
                        "input_tokens": recorder.input_tokens,
                        "output_tokens": recorder.output_tokens,
                        "cost_usd_estimated": estimate_cost(
                            recorder.input_tokens, recorder.output_tokens
                        ),
                        "llm_calls": 1,
                    },
                )
            except Exception:
                logger.exception("Could not close the failed run record for %s", key)
        raise
    else:
        if run_id:
            try:
                from sdr.agents.base.cost import estimate_cost
                await runs_repo.finish_run(
                    run_id, status="succeeded",
                    model_used=recorder.model, provider_used=recorder.provider,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    cost={
                        "input_tokens": recorder.input_tokens,
                        "output_tokens": recorder.output_tokens,
                        "cost_usd_estimated": estimate_cost(
                            recorder.input_tokens, recorder.output_tokens
                        ),
                        "llm_calls": 1,
                    },
                )
            except Exception:
                logger.exception("Could not close the run record for %s", key)


# --- The combined catalogue ---------------------------------------------------

def catalogue() -> list:
    """Every AI capability in the app, agents and assistants together."""
    from sdr.agents import registry as agent_registry

    entries = []
    for agent in agent_registry.describe():
        entries.append({
            "key": agent["key"],
            "label": agent["key"].replace("_", " ").title(),
            "kind": "agent",
            "category": agent.get("category", DEFAULT_CATEGORY),
            "description": agent["description"],
            "version": agent["version"],
            "queue": agent.get("queue"),
            "cost_ceiling_usd": agent.get("cost_ceiling_usd"),
            "surface": agent.get("surface"),
        })

    for assistant in ASSISTANTS:
        entries.append({
            "key": assistant["key"],
            "label": assistant["label"],
            "kind": "assistant",
            "category": assistant["category"],
            "description": assistant["description"],
            "version": "host",
            "queue": None,
            "cost_ceiling_usd": None,
            "surface": assistant["surface"],
            "endpoint": assistant["endpoint"],
        })

    entries.sort(key=lambda e: (e["category"], e["kind"] != "agent", e["key"]))
    return entries


def grouped_catalogue() -> list:
    """The catalogue arranged by category, for the monitor's layout."""
    entries = catalogue()
    groups = []
    for key, meta in CATEGORIES.items():
        members = [entry for entry in entries if entry["category"] == key]
        if members:
            groups.append({
                "category": key,
                "label": meta["label"],
                "description": meta["description"],
                "items": members,
            })
    return groups

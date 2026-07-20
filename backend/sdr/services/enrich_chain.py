"""The research chain: enrich -> audit -> research -> score -> qualify.

Chaining matters because each step needs the previous one's output. Scoring a
lead before its audit has run produces a score of near zero for the
opportunity component, then never revisits it - the lead looks worthless
forever because of ordering, not merit.

Two ways to run it:

- `enqueue_chain()` queues each step with a `run_after` stagger. Correct for
  bulk work, survives redeploys, and every step is independently retryable.
- `run_chain_now()` runs the steps inline. For the "process this lead" button,
  where the operator is watching. Time-boxed, because the whole chain has to
  fit inside one 60-second invocation.

Both propagate one `correlation_id` across every step, so the full journey of
a lead is one query in the run inspector.
"""

import logging

from sdr.agents import registry as agent_registry
from sdr.agents.base.agent import AgentContext
from sdr.errors import NotFoundError, SDRError
from sdr.repositories import leads as leads_repo
from sdr.services import jobs as jobs_service

logger = logging.getLogger(__name__)


class _Null:
    """Fallback so a deferred step for an unregistered agent still queues
    onto a valid queue name rather than raising."""
    queue = "default"

#: Ordered, with the payload key each step expects. Enrichment and audit work
#: on the company; scoring and qualification on the lead.
CHAIN = (
    ("lead_enrichment", "company_id"),
    ("website_audit", "company_id"),
    ("company_research", "company_id"),
    ("lead_scoring", "lead_id"),
    ("lead_qualification", "lead_id"),
)

#: Seconds between queued steps. Enough that a step usually finds its
#: predecessor's output in place, without serialising the whole batch.
STEP_STAGGER_SECONDS = 90

#: Hard ceiling for the inline path. Vercel kills the request at 60s; this
#: leaves margin to queue the remaining steps and serialise a response.
#:
#: A step is only started if its **worst case** fits in the remaining time -
#: `elapsed + step.timeout_ms <= ceiling`. Checking elapsed alone is not
#: enough, and measuring that was the lesson: a live run finished in 64s with
#: nothing deferred, because each step began under budget and then overran.
#: Reserving the timeout is conservative in the common case and correct in
#: the bad one, which is the right way round for something a request ceiling
#: will otherwise kill mid-write.
INLINE_BUDGET_SECONDS = 50.0

#: Deterministic, sub-second in practice, and the reason the operator clicked
#: the button. Always run, even when the budget is spent - stopping before
#: them leaves the lead analysed but unranked, the least useful state to
#: stop in.
ALWAYS_INLINE = ("lead_scoring", "lead_qualification")


async def enqueue_chain(lead_ids: list, *, batch_key: str = "chain",
                        user_id: str | None = None,
                        skip: tuple = ()) -> dict:
    """Queue the full chain for many leads.

    Idempotency keys include the step and the batch, so re-running a batch
    queues nothing and a partially-completed batch resumes cleanly.
    """
    from datetime import datetime, timedelta, timezone

    queued, skipped = 0, 0
    now = datetime.now(timezone.utc)

    for lead_id in lead_ids:
        try:
            lead = await leads_repo.get_lead(lead_id)
        except (NotFoundError, SDRError):
            skipped += 1
            continue

        company_id = lead.get("sdr_company_id")
        entity_ids = {"lead_id": lead_id, "company_id": company_id}

        jobs = []
        for index, (agent_key, entity_field) in enumerate(CHAIN):
            if agent_key in skip:
                continue
            entity_id = entity_ids.get(entity_field)
            if not entity_id:
                # A lead with no linked company cannot be enriched or audited.
                # Scoring still works, so skip the step rather than the lead.
                continue
            agent = agent_registry.get_agent(agent_key)
            if not agent:
                continue
            jobs.append({
                "agent_key": agent_key,
                "queue": agent.queue,
                "payload": {entity_field: entity_id},
                "idempotency_key": f"{agent_key}:{entity_id}:{batch_key}",
                "run_after": (now + timedelta(seconds=index * STEP_STAGGER_SECONDS)).isoformat(),
                # Later steps first in priority so a partially drained queue
                # finishes leads it started rather than starting more.
                "priority": len(CHAIN) - index,
                "correlation_id": None,
                "user_id": user_id,
            })

        result = await jobs_service.enqueue_many(jobs)
        queued += result["created"]

    return {"leads": len(lead_ids), "jobs_queued": queued, "leads_skipped": skipped}


async def run_chain_now(lead_id: str, *, user: dict | None = None,
                        skip: tuple = (),
                        budget_seconds: float = INLINE_BUDGET_SECONDS) -> dict:
    """Run the chain inline for one lead. Returns a per-step report.

    A failing step does not abort the chain: an audit that cannot reach the
    site should not stop the lead being scored on what we do know. The report
    records what happened at each step so a partial result is legible rather
    than mysterious.

    **Time-boxed, and it has to be.** Five agents in sequence - two of which
    make LLM calls and two of which fetch a website - do not reliably fit
    inside Vercel's 60-second request ceiling. Measured against a real site,
    enrichment alone can consume its full 40s timeout. Without a budget the
    request is killed mid-chain and the caller gets no report at all, which is
    strictly worse than a partial one.

    Steps that do not fit are reported as `deferred` and queued instead, so
    the work still happens - just not while the operator waits.
    """
    import time

    started = time.monotonic()
    lead = await leads_repo.get_lead(lead_id)
    company_id = lead.get("sdr_company_id")
    entity_ids = {"lead_id": lead_id, "company_id": company_id}

    correlation_id = None
    steps = []
    deferred = []

    for agent_key, entity_field in CHAIN:
        if agent_key in skip:
            steps.append({"agent": agent_key, "status": "skipped", "reason": "excluded"})
            continue

        # Only start a step whose worst case still fits. Anything that does
        # not is queued, so the request returns a usable report instead of
        # being killed mid-chain.
        agent = agent_registry.get_agent(agent_key)
        elapsed = time.monotonic() - started
        worst_case = ((agent.timeout_ms / 1000) if agent else 0)
        if agent_key not in ALWAYS_INLINE and elapsed + worst_case > budget_seconds:
            entity_id = entity_ids.get(entity_field)
            if entity_id:
                deferred.append({
                    "agent_key": agent_key,
                    "queue": (agent or _Null).queue,
                    "payload": {entity_field: entity_id},
                    "idempotency_key": f"{agent_key}:{entity_id}:deferred",
                    "user_id": (user or {}).get("id"),
                })
            steps.append({
                "agent": agent_key, "status": "deferred",
                "reason": (
                    f"would not fit the {budget_seconds:.0f}s request budget "
                    f"({elapsed:.0f}s spent, needs up to {worst_case:.0f}s); queued instead"
                ),
            })
            continue

        entity_id = entity_ids.get(entity_field)
        if not entity_id:
            steps.append({
                "agent": agent_key, "status": "skipped",
                "reason": f"lead has no {entity_field}",
            })
            continue

        if not agent:
            steps.append({"agent": agent_key, "status": "skipped", "reason": "not registered"})
            continue

        ctx = AgentContext(user=user, trigger="manual", correlation_id=correlation_id)
        try:
            result = await agent.run({entity_field: entity_id}, ctx)
            correlation_id = correlation_id or ctx.correlation_id
            steps.append({
                "agent": agent_key, "status": "succeeded",
                "run_id": result.run_id, "output": result.output,
            })
        except SDRError as exc:
            correlation_id = correlation_id or ctx.correlation_id
            logger.warning("Chain step %s failed for lead %s: %s", agent_key, lead_id, exc)
            steps.append({
                "agent": agent_key, "status": "failed",
                "run_id": ctx.run_id, "error": exc.message,
            })
        except Exception as exc:
            correlation_id = correlation_id or ctx.correlation_id
            logger.exception("Chain step %s crashed for lead %s", agent_key, lead_id)
            steps.append({
                "agent": agent_key, "status": "failed",
                "run_id": ctx.run_id, "error": str(exc)[:300],
            })

    if deferred:
        await jobs_service.enqueue_many(deferred)

    final = await leads_repo.get_lead(lead_id)
    return {
        "lead_id": lead_id,
        "correlation_id": correlation_id,
        "steps": steps,
        "deferred_to_queue": len(deferred),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "score": final.get("score"),
        "score_breakdown": final.get("score_breakdown"),
        "qualification_status": final.get("qualification_status"),
        "stage": final.get("stage"),
    }

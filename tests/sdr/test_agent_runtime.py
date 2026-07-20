"""The agent runner and the job queue, against an in-memory database.

Uses fake agents rather than the real one so the runner's guarantees - run
recording, output validation, timeouts, cost ceilings, retry and dead-letter -
are tested in isolation from any model. The point of these tests is that an
agent author *cannot* skip them, so they assert on the runner, not the agent.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "sdr_test")


@pytest_asyncio.fixture
async def db(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    database = client["sdr_test"]

    import database as database_module
    monkeypatch.setattr(database_module, "db", database)

    from sdr.repositories import agent_runs, base, companies, leads, overview, settings
    from sdr.services import discovery, jobs
    for module in (agent_runs, base, companies, leads, overview, settings, discovery, jobs):
        if hasattr(module, "db"):
            monkeypatch.setattr(module, "db", database)
    return database


# --- Fakes --------------------------------------------------------------------

class Out(BaseModel):
    value: str


class OkAgent:
    """Built by composing the real Agent runner with a trivial execute()."""


def make_agent(execute, **overrides):
    from sdr.agents.base.agent import Agent

    class _Fake(Agent):
        key = overrides.get("key", "fake_agent")
        version = "1.0.0"
        description = "test"
        output_schema = Out
        queue = overrides.get("queue", "default")
        cost_ceiling_usd = overrides.get("cost_ceiling_usd", 1.0)
        timeout_ms = overrides.get("timeout_ms", 5000)

        async def execute(self, payload, ctx):
            return await execute(payload, ctx)

    return _Fake()


# --- Run recording ------------------------------------------------------------

@pytest.mark.asyncio
async def test_successful_run_is_recorded_with_cost_and_duration(db):
    from sdr.agents.base.agent import AgentContext
    from sdr.repositories import agent_runs

    async def work(payload, ctx):
        ctx.tracker.record(100, 50)
        return {"value": "done"}

    agent = make_agent(work)
    result = await agent.run({"company_id": "c1"}, AgentContext(trigger="manual"))

    run = await agent_runs.get_run(result.run_id)
    assert run["status"] == "succeeded"
    assert run["agent_key"] == "fake_agent"
    assert run["entity_type"] == "company"
    assert run["entity_id"] == "c1"
    assert run["input_tokens"] == 100
    assert run["cost_usd_estimated"] > 0
    assert run["duration_ms"] is not None
    assert run["finished_at"]


@pytest.mark.asyncio
async def test_a_failing_run_is_still_recorded(db):
    """The whole point of the spine: a failure that leaves no row is
    indistinguishable from work that never happened."""
    from sdr.agents.base.agent import AgentContext
    from sdr.errors import ProviderError
    from sdr.repositories import agent_runs

    async def work(payload, ctx):
        raise ProviderError("upstream exploded")

    agent = make_agent(work)
    ctx = AgentContext()
    with pytest.raises(ProviderError):
        await agent.run({}, ctx)

    run = await agent_runs.get_run(ctx.run_id)
    assert run["status"] == "failed"
    assert run["error_type"] == "ProviderError"
    assert "upstream exploded" in run["error_message"]


@pytest.mark.asyncio
async def test_an_unexpected_crash_is_recorded_too(db):
    from sdr.agents.base.agent import AgentContext
    from sdr.repositories import agent_runs

    async def work(payload, ctx):
        return 1 / 0

    agent = make_agent(work)
    ctx = AgentContext()
    with pytest.raises(ZeroDivisionError):
        await agent.run({}, ctx)

    run = await agent_runs.get_run(ctx.run_id)
    assert run["status"] == "failed"
    assert run["error_type"] == "ZeroDivisionError"


@pytest.mark.asyncio
async def test_run_input_is_redacted_before_storage(db):
    """sdr_agent_runs must not become a second copy of the contact database."""
    from sdr.agents.base.agent import AgentContext
    from sdr.repositories import agent_runs

    agent = make_agent(lambda p, c: _ok())
    result = await agent.run({"email": "someone@acme.in", "api_key": "nvapi-secret"},
                             AgentContext())
    run = await agent_runs.get_run(result.run_id)
    assert run["input"]["api_key"] == "[redacted]"
    assert "someone@acme.in" not in str(run["input"])


async def _ok():
    return {"value": "ok"}


@pytest.mark.asyncio
async def test_timeout_aborts_and_records(db):
    from sdr.agents.base.agent import AgentContext
    from sdr.errors import AgentTimeoutError
    from sdr.repositories import agent_runs

    async def slow(payload, ctx):
        await asyncio.sleep(2)
        return {"value": "never"}

    agent = make_agent(slow, timeout_ms=100)
    ctx = AgentContext()
    with pytest.raises(AgentTimeoutError):
        await agent.run({}, ctx)

    run = await agent_runs.get_run(ctx.run_id)
    assert run["status"] == "failed"
    assert run["error_type"] == "AgentTimeoutError"


@pytest.mark.asyncio
async def test_cost_ceiling_aborts_the_run(db):
    from sdr.agents.base.agent import AgentContext
    from sdr.errors import CostCeilingError

    async def expensive(payload, ctx):
        ctx.tracker.record(10_000_000, 10_000_000)
        return {"value": "too late"}

    agent = make_agent(expensive, cost_ceiling_usd=0.0001)
    with pytest.raises(CostCeilingError):
        await agent.run({}, AgentContext())


@pytest.mark.asyncio
async def test_input_schema_is_enforced(db):
    from sdr.agents.base.agent import Agent, AgentContext
    from sdr.errors import ValidationError

    class In(BaseModel):
        company_id: str

    class _Agent(Agent):
        key = "strict"
        input_schema = In
        output_schema = Out

        async def execute(self, payload, ctx):
            return {"value": "ok"}

    with pytest.raises(ValidationError):
        await _Agent().run({"wrong": "shape"}, AgentContext())


@pytest.mark.asyncio
async def test_correlation_id_defaults_to_the_run_id_and_propagates(db):
    """Correlation is what makes a lead's whole journey reconstructable."""
    from sdr.agents.base.agent import AgentContext
    from sdr.repositories import agent_runs

    agent = make_agent(lambda p, c: _ok())

    first_ctx = AgentContext()
    first = await agent.run({"lead_id": "L1"}, first_ctx)
    root = (await agent_runs.get_run(first.run_id))["correlation_id"]
    assert root == first.run_id

    second = await agent.run({"lead_id": "L1"}, AgentContext(correlation_id=root))
    trace = await agent_runs.get_trace(root)
    assert {run["id"] for run in trace} == {first.run_id, second.run_id}


@pytest.mark.asyncio
async def test_guardrail_flags_are_persisted(db):
    from sdr.agents.base.agent import AgentContext
    from sdr.repositories import agent_runs

    async def flagging(payload, ctx):
        ctx.flag("prompt_injection_attempt", ["ignore previous instructions"])
        return {"value": "ok"}

    result = await make_agent(flagging).run({}, AgentContext())
    run = await agent_runs.get_run(result.run_id)
    assert run["guardrail_flags"][0]["kind"] == "prompt_injection_attempt"


@pytest.mark.asyncio
async def test_agent_stats_and_daily_spend(db):
    from sdr.agents.base.agent import AgentContext
    from sdr.errors import ProviderError
    from sdr.repositories import agent_runs

    async def work(payload, ctx):
        ctx.tracker.record(1000, 500)
        return {"value": "ok"}

    agent = make_agent(work)
    await agent.run({}, AgentContext())
    await agent.run({}, AgentContext())

    failing = make_agent(_boom)
    with pytest.raises(ProviderError):
        await failing.run({}, AgentContext())

    stats = await agent_runs.agent_stats(hours=24)
    row = next(s for s in stats if s["agent_key"] == "fake_agent")
    assert row["total"] == 3
    assert row["succeeded"] == 2
    assert row["failed"] == 1
    assert row["success_rate"] == pytest.approx(2 / 3, abs=0.01)
    assert await agent_runs.daily_spend_usd() > 0


async def _boom(payload, ctx):
    from sdr.errors import ProviderError
    raise ProviderError("nope")


# --- Job queue ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_enqueue_and_claim(db):
    from sdr.services import jobs

    await jobs.enqueue(agent_key="fake_agent", payload={"company_id": "c1"})
    claimed = await jobs.claim_next()
    assert claimed["agent_key"] == "fake_agent"
    assert claimed["status"] == "running"
    assert claimed["attempt"] == 1
    assert claimed["locked_until"]


@pytest.mark.asyncio
async def test_a_claimed_job_is_not_claimed_twice(db):
    """The invariant that stops one email being sent twice."""
    from sdr.services import jobs

    await jobs.enqueue(agent_key="fake_agent", payload={})
    assert await jobs.claim_next() is not None
    assert await jobs.claim_next() is None


@pytest.mark.asyncio
async def test_idempotency_key_blocks_a_duplicate_enqueue(db):
    from sdr.services import jobs

    first = await jobs.enqueue(agent_key="a", payload={}, idempotency_key="k1")
    second = await jobs.enqueue(agent_key="a", payload={}, idempotency_key="k1")
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["id"] == first["id"]


@pytest.mark.asyncio
async def test_rerunning_a_batch_enqueues_nothing_the_second_time(db):
    from sdr.services import jobs

    batch = [
        {"agent_key": "lead_enrichment", "payload": {"company_id": cid},
         "idempotency_key": f"lead_enrichment:{cid}:b1"}
        for cid in ("c1", "c2", "c3")
    ]
    assert (await jobs.enqueue_many(batch))["created"] == 3
    assert (await jobs.enqueue_many(batch))["duplicates"] == 3


@pytest.mark.asyncio
async def test_future_jobs_are_not_claimed_early(db):
    from datetime import datetime, timedelta, timezone
    from sdr.services import jobs

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    await jobs.enqueue(agent_key="a", payload={}, run_after=future)
    assert await jobs.claim_next() is None


@pytest.mark.asyncio
async def test_expired_lease_is_reclaimed(db):
    """On serverless a dying invocation gets no chance to clean up, so a
    job stuck in `running` forever is the default failure without this."""
    from datetime import datetime, timedelta, timezone
    from sdr.services import jobs

    await jobs.enqueue(agent_key="a", payload={})
    claimed = await jobs.claim_next()

    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    await db[_jobs_collection()].update_one(
        {"status": "running"}, {"$set": {"locked_until": stale}}
    )
    reclaimed = await jobs.claim_next()
    assert reclaimed is not None
    assert reclaimed["id"] == claimed["id"]
    assert reclaimed["attempt"] == 2


@pytest.mark.asyncio
async def test_priority_jumps_the_queue(db):
    from sdr.services import jobs

    await jobs.enqueue(agent_key="low", payload={}, priority=0)
    await jobs.enqueue(agent_key="high", payload={}, priority=10)
    assert (await jobs.claim_next())["agent_key"] == "high"


@pytest.mark.asyncio
async def test_retryable_failure_requeues_with_a_future_run_after(db):
    from sdr.errors import ProviderError
    from sdr.services import jobs

    await jobs.enqueue(agent_key="a", payload={}, queue="enrichment")
    claimed = await jobs.claim_next()

    status = await jobs.fail(claimed["id"], error=ProviderError("flaky"))
    assert status == "queued"
    # Backed off, so an immediate claim finds nothing.
    assert await jobs.claim_next() is None


@pytest.mark.asyncio
async def test_non_retryable_failure_dead_letters_immediately(db):
    from sdr.errors import ValidationError
    from sdr.services import jobs

    await jobs.enqueue(agent_key="a", payload={}, queue="enrichment")
    claimed = await jobs.claim_next()
    assert await jobs.fail(claimed["id"], error=ValidationError("bad input")) == "dead_letter"


@pytest.mark.asyncio
async def test_retries_exhaust_into_the_dead_letter_queue(db):
    from sdr.errors import ProviderError
    from sdr.services import jobs

    await jobs.enqueue(agent_key="a", payload={}, queue="send")  # 3 attempts
    for _ in range(3):
        # Fast-forward past the backoff rather than sleeping through it.
        await db[_jobs_collection()].update_one(
            {"status": {"$in": ["queued", "running"]}},
            {"$set": {"run_after": "2020-01-01T00:00:00+00:00",
                      "locked_until": None, "status": "queued"}},
        )
        claimed = await jobs.claim_next()
        status = await jobs.fail(claimed["id"], error=ProviderError("still failing"))

    assert status == "dead_letter"
    assert len(await jobs.dead_letters()) == 1


def _jobs_collection():
    from sdr.collections import JOBS
    return JOBS


@pytest.mark.asyncio
async def test_replay_resets_the_attempt_budget(db):
    """An operator replaying has usually fixed the cause, so it deserves a
    full retry budget rather than dead-lettering again immediately."""
    from sdr.errors import ValidationError
    from sdr.services import jobs

    await jobs.enqueue(agent_key="a", payload={}, queue="enrichment")
    claimed = await jobs.claim_next()
    await jobs.fail(claimed["id"], error=ValidationError("bad"))

    replayed = await jobs.replay(claimed["id"])
    assert replayed["status"] == "queued"
    assert replayed["attempt"] == 0
    assert await jobs.claim_next() is not None


@pytest.mark.asyncio
async def test_only_failed_jobs_can_be_replayed(db):
    from sdr.errors import ValidationError
    from sdr.services import jobs

    job = await jobs.enqueue(agent_key="a", payload={})
    with pytest.raises(ValidationError):
        await jobs.replay(job["id"])


# --- Draining -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_drain_runs_queued_jobs_and_reports(db, monkeypatch):
    from sdr.agents import registry
    from sdr.services import jobs

    agent = make_agent(lambda p, c: _ok(), key="drainable")
    monkeypatch.setattr(registry, "_AGENTS", {"drainable": agent})

    for i in range(3):
        await jobs.enqueue(agent_key="drainable", payload={"company_id": f"c{i}"})

    report = await jobs.drain()
    assert report["processed"] == 3
    assert report["succeeded"] == 3
    assert (await jobs.stats())["queued"] == 0


@pytest.mark.asyncio
async def test_one_poisonous_job_does_not_abort_the_drain(db, monkeypatch):
    """Otherwise a single bad record blocks the queue indefinitely."""
    from sdr.agents import registry
    from sdr.services import jobs

    async def sometimes(payload, ctx):
        if payload.get("company_id") == "bad":
            raise ValueError("poison")
        return {"value": "ok"}

    agent = make_agent(sometimes, key="mixed")
    monkeypatch.setattr(registry, "_AGENTS", {"mixed": agent})

    for cid in ("good1", "bad", "good2"):
        await jobs.enqueue(agent_key="mixed", payload={"company_id": cid})

    report = await jobs.drain()
    assert report["processed"] == 3
    assert report["succeeded"] == 2
    assert report["failed"] == 1


@pytest.mark.asyncio
async def test_unregistered_agent_dead_letters_with_a_clear_reason(db, monkeypatch):
    from sdr.agents import registry
    from sdr.services import jobs

    monkeypatch.setattr(registry, "_AGENTS", {})
    await jobs.enqueue(agent_key="does_not_exist", payload={})

    report = await jobs.drain()
    assert report["results"][0]["status"] == "no_such_agent"
    dead = await jobs.dead_letters()
    assert "No agent registered" in dead[0]["last_error"]["message"]


@pytest.mark.asyncio
async def test_drain_stops_at_its_time_budget(db, monkeypatch):
    """It has to return before the 60-second serverless ceiling kills it
    mid-write."""
    from sdr.agents import registry
    from sdr.services import jobs

    async def slow(payload, ctx):
        await asyncio.sleep(0.05)
        return {"value": "ok"}

    monkeypatch.setattr(registry, "_AGENTS", {"slow": make_agent(slow, key="slow")})
    for i in range(30):
        await jobs.enqueue(agent_key="slow", payload={"company_id": f"c{i}"})

    report = await jobs.drain(budget_seconds=0.2)
    assert report["processed"] < 30
    assert (await jobs.stats())["queued"] > 0  # the rest survive for next time


@pytest.mark.asyncio
async def test_drained_jobs_link_to_their_agent_run(db, monkeypatch):
    from sdr.agents import registry
    from sdr.services import jobs

    monkeypatch.setattr(registry, "_AGENTS", {"linked": make_agent(lambda p, c: _ok(), key="linked")})
    await jobs.enqueue(agent_key="linked", payload={})
    await jobs.drain()

    job = (await jobs.list_jobs(status="succeeded"))["items"][0]
    assert len(job["run_ids"]) == 1


@pytest.mark.asyncio
async def test_stats_expose_the_oldest_queued_job(db):
    """The number that actually tells you the external pinger has died."""
    from sdr.services import jobs

    await jobs.enqueue(agent_key="a", payload={})
    stats = await jobs.stats()
    assert stats["queued"] == 1
    assert stats["oldest_queued_at"] is not None

"""The inline chain's time budget.

Found the hard way: running the real chain against a live site, enrichment
consumed its full 40-second timeout, and five agents in sequence cannot fit
inside Vercel's 60-second request ceiling. Without a budget the request is
killed mid-chain and the caller gets nothing back - strictly worse than a
partial report.
"""

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

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

    from sdr.agents.scoring import agent as scoring_agent
    from sdr.repositories import (
        agent_runs, audits, base, companies, leads, overview, settings,
    )
    from sdr.services import discovery, enrich_chain, jobs
    for module in (agent_runs, audits, base, companies, leads, overview,
                   settings, discovery, enrich_chain, jobs, scoring_agent):
        if hasattr(module, "db"):
            monkeypatch.setattr(module, "db", database)
    return database


async def _seed():
    from sdr.repositories import companies as companies_repo
    from sdr.repositories import leads as leads_repo

    await companies_repo.upsert_many([{
        "name": "Slow Clinic", "domain": "slow.example", "city": "Pune",
        "country_code": "IN", "industry": "dental",
        "primary_email": "hi@slow.example", "discovery_source": "csv_import",
    }])
    company = (await companies_repo.list_companies())["items"][0]
    return company, await leads_repo.create_from_company(company)


@pytest.mark.asyncio
async def test_a_step_whose_worst_case_does_not_fit_is_deferred(db):
    """Reserving each step's timeout, not just checking elapsed time.

    Measured against a live site, the elapsed-only version let every step
    start under budget and still finished at 64s - past the request ceiling
    it existed to respect.
    """
    from sdr.services import enrich_chain, jobs

    _, lead = await _seed()
    # Smaller than any agent's timeout, so nothing optional can fit.
    result = await enrich_chain.run_chain_now(lead["id"], budget_seconds=1)

    by_agent = {step["agent"]: step for step in result["steps"]}
    assert by_agent["lead_enrichment"]["status"] == "deferred"
    assert by_agent["website_audit"]["status"] == "deferred"
    assert by_agent["company_research"]["status"] == "deferred"
    assert "needs up to" in by_agent["lead_enrichment"]["reason"]
    assert result["deferred_to_queue"] == 3

    # Deferred, not dropped.
    assert (await jobs.stats())["queued"] == 3


@pytest.mark.asyncio
async def test_a_slow_step_defers_what_follows(db, monkeypatch):
    import asyncio

    from sdr.agents.enrichment.agent import EnrichmentAgent
    from sdr.services import enrich_chain

    async def slow_enrichment(self, payload, ctx):
        await asyncio.sleep(0.3)
        return {"company_id": payload["company_id"], "enrichment_status": "partial"}

    monkeypatch.setattr(EnrichmentAgent, "execute", slow_enrichment)
    monkeypatch.setattr(EnrichmentAgent, "timeout_ms", 400)

    _, lead = await _seed()
    result = await enrich_chain.run_chain_now(lead["id"], budget_seconds=0.5)

    by_agent = {step["agent"]: step for step in result["steps"]}
    assert by_agent["lead_enrichment"]["status"] == "succeeded"
    assert by_agent["website_audit"]["status"] == "deferred"
    assert by_agent["company_research"]["status"] == "deferred"


@pytest.mark.asyncio
async def test_scoring_always_runs_even_over_budget(db, monkeypatch):
    """Stopping after the audit but before the score leaves the lead in the
    least useful possible state - analysed, but unranked and unqualified."""
    import asyncio

    from sdr.agents.enrichment.agent import EnrichmentAgent
    from sdr.repositories import leads as leads_repo
    from sdr.services import enrich_chain

    async def slow_enrichment(self, payload, ctx):
        await asyncio.sleep(0.3)
        return {"company_id": payload["company_id"]}

    monkeypatch.setattr(EnrichmentAgent, "execute", slow_enrichment)

    _, lead = await _seed()
    result = await enrich_chain.run_chain_now(lead["id"], budget_seconds=1)

    by_agent = {step["agent"]: step for step in result["steps"]}
    assert by_agent["lead_scoring"]["status"] == "succeeded"
    assert by_agent["lead_qualification"]["status"] == "succeeded"

    final = await leads_repo.get_lead(lead["id"])
    assert final["score"] > 0
    assert final["qualification_status"] in ("qualified", "needs_review", "unqualified")


@pytest.mark.asyncio
async def test_a_generous_budget_runs_everything_inline(db, monkeypatch):
    from sdr.agents.enrichment.agent import EnrichmentAgent
    from sdr.agents.research.agent import CompanyResearchAgent, ResearchOutput
    from sdr.services import enrich_chain, safe_fetch

    async def quick(self, payload, ctx):
        return {"company_id": payload["company_id"]}

    async def fake_fetch(url, **kwargs):
        return safe_fetch.SafeResponse(
            url=url, status_code=200, headers={}, text="<html><body>x</body></html>",
            elapsed_ms=50, redirects=[], tls=True,
        )

    async def fake_research(self, system, user, ctx, schema=None):
        ctx.tracker.record(100, 50)
        return ResearchOutput(summary="A clinic.", confidence=0.5, evidence=[])

    monkeypatch.setattr(EnrichmentAgent, "execute", quick)
    monkeypatch.setattr("sdr.agents.website_audit.agent.safe_fetch.fetch", fake_fetch)
    monkeypatch.setattr(CompanyResearchAgent, "complete_validated", fake_research)

    _, lead = await _seed()
    # Larger than the sum of every step's timeout, so worst-case reservation
    # never defers. 30s would not do it: enrichment alone reserves 40s.
    result = await enrich_chain.run_chain_now(lead["id"], budget_seconds=200)

    assert result["deferred_to_queue"] == 0
    assert all(step["status"] == "succeeded" for step in result["steps"])
    assert result["elapsed_ms"] >= 0


@pytest.mark.asyncio
async def test_deferred_work_is_idempotent_against_a_second_attempt(db, monkeypatch):
    """Clicking Process twice must not queue the same deferred work twice."""
    import asyncio

    from sdr.agents.enrichment.agent import EnrichmentAgent
    from sdr.services import enrich_chain, jobs

    async def slow(self, payload, ctx):
        await asyncio.sleep(0.3)
        return {"company_id": payload["company_id"]}

    monkeypatch.setattr(EnrichmentAgent, "execute", slow)

    _, lead = await _seed()
    await enrich_chain.run_chain_now(lead["id"], budget_seconds=0.1)
    queued_after_first = (await jobs.stats())["queued"]

    await enrich_chain.run_chain_now(lead["id"], budget_seconds=0.1)
    assert (await jobs.stats())["queued"] == queued_after_first

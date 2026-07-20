"""The Phase 4 gate: discovery -> audit -> signals -> score -> qualified.

The whole point is that the score at the end is *explainable*. A number with
no breakdown cannot be argued with, and a rep who cannot argue with it will
ignore it. So these tests assert on the reasoning, not just the value.

HTTP and the model are stubbed; everything else - detection, the signal
registry, ROI, scoring, qualification, the state machine, the run recorder -
is the real implementation.
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

NEGLECTED_SITE = """
<html><head><title>Kumar Dental</title></head>
<body><h1>Kumar Dental</h1><p>Call us on 020 1234 5678.</p></body></html>
"""

MODERN_SITE = """
<html><head>
  <title>Bright Smile Dental - Pune Implants and Orthodontics</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Family dental clinic in Pune offering implants and orthodontics since 2015.">
  <link rel="canonical" href="https://bright.example/">
  <script type="application/ld+json">{"@type":"Dentist"}</script>
  <script src="https://embed.tawk.to/a/default"></script>
  <script src="https://assets.calendly.com/assets/external/widget.js"></script>
  <script src="https://js.hs-scripts.com/1.js"></script>
  <script src="https://www.googletagmanager.com/gtag/js?id=G-A"></script>
</head><body>
  <h1>Bright Smile Dental</h1>
  <a href="tel:+912012345678">Call</a><a href="https://wa.me/91201234">WhatsApp</a>
  <form action="/contact"><input type="email" name="email"><textarea></textarea></form>
  <img src="a.jpg" alt="Reception">
</body></html>
"""


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


@pytest.fixture
def stub_network(monkeypatch):
    """Serve a fixture page per domain, and a deterministic research result."""
    from sdr.agents.enrichment.agent import EnrichmentAgent
    from sdr.agents.research.agent import CompanyResearchAgent, ResearchOutput
    from sdr.services import safe_fetch

    pages = {
        "kumardental.example": NEGLECTED_SITE,
        "bright.example": MODERN_SITE,
    }

    async def fake_fetch(url, **kwargs):
        host = url.split("://", 1)[-1].split("/")[0]
        if host not in pages:
            from sdr.errors import ValidationError
            raise ValidationError(f"Could not fetch {url}: simulated DNS failure")
        return safe_fetch.SafeResponse(
            url=url, status_code=200, headers={"server": "nginx"},
            text=pages[host], elapsed_ms=350, redirects=[], tls=True,
        )

    monkeypatch.setattr(safe_fetch, "fetch", fake_fetch)
    monkeypatch.setattr(
        "sdr.agents.website_audit.agent.safe_fetch.fetch", fake_fetch
    )

    async def no_enrich_llm(self, company, page_text, ctx):
        from sdr.agents.base.llm import LLMNotConfiguredError
        raise LLMNotConfiguredError("no model in tests")

    monkeypatch.setattr(EnrichmentAgent, "_infer", no_enrich_llm)

    async def fake_research(self, system, user, ctx, schema=None):
        ctx.tracker.record(500, 150)
        # Cites a signal that genuinely exists for the neglected site.
        return ResearchOutput(
            summary="Kumar Dental is a dental practice in Pune.",
            target_customer="Local families seeking routine dental care",
            pitch_angle="No online booking, so every appointment costs staff time.",
            lead_signal_key="manual_appointment_booking",
            talking_points=["Kumar Dental", "Pune"],
            evidence=["Kumar Dental", "Pune"],
            confidence=0.75,
        )

    monkeypatch.setattr(CompanyResearchAgent, "complete_validated", fake_research)


async def _seed_lead(domain: str, name: str, *, country="IN", industry="dental",
                     email="owner@example.com"):
    from sdr.repositories import companies as companies_repo
    from sdr.repositories import leads as leads_repo

    await companies_repo.upsert_many([{
        "name": name, "domain": domain, "city": "Pune", "country_code": country,
        "industry": industry, "primary_email": email,
        "google_review_count": 212, "google_rating": 4.6,
        "discovery_source": "csv_import",
    }])
    # Look the company up by domain rather than taking the newest: several
    # seeded in the same test share a created_at to the microsecond, so
    # position is not a stable identifier.
    listed = (await companies_repo.list_companies(limit=200))["items"]
    company = next(c for c in listed if c["domain"] == domain)
    lead = await leads_repo.create_from_company(company)
    return company, lead


# --- The gate -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_lead_flows_all_the_way_to_qualified_with_an_explainable_score(
    db, stub_network
):
    from sdr.repositories import audits as audits_repo
    from sdr.repositories import leads as leads_repo
    from sdr.services import enrich_chain

    company, lead = await _seed_lead("kumardental.example", "Kumar Dental")
    assert lead["stage"] == "prospect"
    assert lead["score"] == 0

    result = await enrich_chain.run_chain_now(lead["id"])

    # Every step ran and is individually accounted for.
    by_agent = {step["agent"]: step for step in result["steps"]}
    assert set(by_agent) == {
        "lead_enrichment", "website_audit", "company_research",
        "lead_scoring", "lead_qualification",
    }
    assert by_agent["website_audit"]["status"] == "succeeded"
    assert by_agent["lead_scoring"]["status"] == "succeeded"
    assert by_agent["lead_qualification"]["status"] == "succeeded"

    # The audit found the gaps a neglected site actually has.
    signals = await audits_repo.signals_for(company["id"])
    keys = {row["signal_key"] for row in signals}
    assert "no_chatbot" in keys
    assert "manual_appointment_booking" in keys
    assert "not_mobile_friendly" in keys
    assert "no_analytics" in keys

    # Severity ordering holds, so the pitch leads with the worst gap.
    ranks = [
        __import__("sdr.domain.signals", fromlist=["SEVERITY_RANK"]).SEVERITY_RANK[row["severity"]]
        for row in signals
    ]
    assert ranks == sorted(ranks, reverse=True)

    # The lead is scored, qualified, and advanced.
    final = await leads_repo.get_lead(lead["id"])
    assert final["score"] > 0
    assert final["qualification_status"] == "qualified"
    assert final["stage"] == "qualified"
    assert result["stage"] == "qualified"

    # ...and the score explains itself, which is the actual deliverable.
    breakdown = final["score_breakdown"]
    assert set(breakdown) == {
        "icp_fit", "opportunity", "reachability", "intent", "data_quality"
    }
    for component, detail in breakdown.items():
        assert detail["reasons"], f"{component} gave no reason"
        assert "points" in detail and "weight" in detail
    assert sum(d["points"] for d in breakdown.values()) == pytest.approx(final["score"], abs=1)

    # The opportunity component is non-zero *because* the audit ran first -
    # this is the ordering the chain exists to guarantee.
    assert breakdown["opportunity"]["raw"] > 0
    assert "gaps detected" in breakdown["opportunity"]["reasons"][0]


@pytest.mark.asyncio
async def test_the_whole_journey_is_one_correlation_trace(db, stub_network):
    """'Why did this lead end up qualified' must be answerable in one query."""
    from sdr.repositories import agent_runs
    from sdr.services import enrich_chain

    _, lead = await _seed_lead("kumardental.example", "Kumar Dental")
    result = await enrich_chain.run_chain_now(lead["id"])

    trace = await agent_runs.get_trace(result["correlation_id"])
    assert len(trace) == 5
    assert [run["agent_key"] for run in trace] == [
        "lead_enrichment", "website_audit", "company_research",
        "lead_scoring", "lead_qualification",
    ]
    assert all(run["status"] == "succeeded" for run in trace)


@pytest.mark.asyncio
async def test_a_well_equipped_prospect_scores_lower_than_a_neglected_one(db, stub_network):
    """The scoring has to be directionally right, or the ranking is noise:
    a business with no gaps is a worse prospect for an automation agency."""
    from sdr.repositories import leads as leads_repo
    from sdr.services import enrich_chain

    _, neglected = await _seed_lead("kumardental.example", "Kumar Dental")
    await enrich_chain.run_chain_now(neglected["id"])
    neglected_final = await leads_repo.get_lead(neglected["id"])

    from sdr.repositories import companies as companies_repo
    await companies_repo.upsert_many([{
        "name": "Bright Smile Dental", "domain": "bright.example", "city": "Pune",
        "country_code": "IN", "industry": "dental", "primary_email": "hi@bright.example",
        "google_review_count": 212, "discovery_source": "csv_import",
    }])
    modern_company = next(
        c for c in (await companies_repo.list_companies())["items"]
        if c["domain"] == "bright.example"
    )
    modern = await leads_repo.create_from_company(modern_company)
    await enrich_chain.run_chain_now(modern["id"])
    modern_final = await leads_repo.get_lead(modern["id"])

    assert neglected_final["score"] > modern_final["score"]
    assert (neglected_final["score_breakdown"]["opportunity"]["raw"]
            > modern_final["score_breakdown"]["opportunity"]["raw"])


# --- Hard rules beat scores ---------------------------------------------------

@pytest.mark.asyncio
async def test_an_unlisted_country_is_disqualified_however_good_the_fit(db, stub_network):
    """No compliance profile means no lawful basis. That beats any score."""
    from sdr.repositories import leads as leads_repo
    from sdr.services import enrich_chain

    _, lead = await _seed_lead("kumardental.example", "Kumar Dental", country="ZZ")
    await enrich_chain.run_chain_now(lead["id"])

    final = await leads_repo.get_lead(lead["id"])
    assert final["qualification_status"] == "disqualified"
    assert "compliance" in final["disqualification_reason"]
    assert final["stage"] == "prospect"  # never advanced


@pytest.mark.asyncio
async def test_a_suppressed_domain_is_disqualified(db, stub_network):
    """An opt-out is permanent and applies across every channel."""
    from sdr.collections import SUPPRESSION
    from sdr.repositories import leads as leads_repo
    from sdr.services import enrich_chain

    _, lead = await _seed_lead("kumardental.example", "Kumar Dental")
    await db[SUPPRESSION].insert_one({
        "value_type": "domain", "value_normalized": "kumardental.example",
        "reason": "unsubscribe",
    })

    await enrich_chain.run_chain_now(lead["id"])
    final = await leads_repo.get_lead(lead["id"])
    assert final["qualification_status"] == "disqualified"
    assert "suppressed" in final["disqualification_reason"]


@pytest.mark.asyncio
async def test_a_lead_with_no_contact_route_is_disqualified(db, stub_network):
    from sdr.repositories import leads as leads_repo
    from sdr.services import enrich_chain

    _, lead = await _seed_lead("kumardental.example", "Kumar Dental", email=None)
    await db.leads.update_one({}, {"$set": {"email": None, "phone": None}})

    await enrich_chain.run_chain_now(lead["id"])
    final = await leads_repo.get_lead(lead["id"])
    assert final["qualification_status"] == "disqualified"
    assert "no contact route" in final["disqualification_reason"]


# --- Degradation --------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_unreachable_site_still_gets_scored(db, stub_network):
    """A failed audit must not stop the lead being scored on what we do know,
    or one dead domain removes the lead from the pipeline entirely."""
    from sdr.repositories import audits as audits_repo
    from sdr.repositories import leads as leads_repo
    from sdr.services import enrich_chain

    company, lead = await _seed_lead("dead-domain.example", "Ghost Clinic")
    result = await enrich_chain.run_chain_now(lead["id"])

    audit_step = next(s for s in result["steps"] if s["agent"] == "website_audit")
    # The *job* succeeded; the *audit* is recorded as failed. Distinct things.
    assert audit_step["status"] == "succeeded"
    assert audit_step["output"]["status"] == "failed"

    stored = await audits_repo.latest_audit(company["id"])
    assert stored["status"] == "failed"
    assert "simulated DNS failure" in stored["error"]

    final = await leads_repo.get_lead(lead["id"])
    assert final["score"] > 0  # scored on reachability and data quality alone
    assert final["score_breakdown"]["opportunity"]["raw"] == 0


@pytest.mark.asyncio
async def test_a_company_with_no_website_records_a_skipped_audit(db, stub_network):
    from sdr.agents.base.agent import AgentContext
    from sdr.agents.website_audit import WebsiteAuditAgent
    from sdr.repositories import companies as companies_repo

    await companies_repo.upsert_many([{
        "name": "No Site Clinic", "city": "Pune", "country_code": "IN",
        "industry": "dental", "discovery_source": "csv_import",
    }])
    company = (await companies_repo.list_companies())["items"][0]

    result = await WebsiteAuditAgent().run({"company_id": company["id"]}, AgentContext())
    assert result.output["status"] == "skipped"
    assert result.output["reason"] == "no website"


@pytest.mark.asyncio
async def test_every_audit_records_what_it_could_not_measure(db, stub_network):
    """An audit that silently omits Core Web Vitals reads like a clean bill
    of health on performance."""
    from sdr.domain import detect
    from sdr.repositories import audits as audits_repo
    from sdr.services import enrich_chain

    company, lead = await _seed_lead("kumardental.example", "Kumar Dental")
    await enrich_chain.run_chain_now(lead["id"])

    audit = await audits_repo.latest_audit(company["id"])
    assert set(audit["unmeasured"]) == set(detect.UNMEASURED_FACTS)


# --- Research grounding -------------------------------------------------------

@pytest.mark.asyncio
async def test_research_writes_a_pitch_angle_tied_to_a_real_signal(db, stub_network):
    from sdr.repositories import companies as companies_repo
    from sdr.services import enrich_chain

    company, lead = await _seed_lead("kumardental.example", "Kumar Dental")
    await enrich_chain.run_chain_now(lead["id"])

    stored = await companies_repo.get_company(company["id"])
    assert stored["pitch_angle"]
    assert stored["lead_signal_key"] == "manual_appointment_booking"


@pytest.mark.asyncio
async def test_a_pitch_citing_a_signal_we_never_detected_is_rejected(db, stub_network, monkeypatch):
    """The failure that matters: a claim about a gap the prospect does not
    have, sent to them in an email."""
    from sdr.agents.research.agent import CompanyResearchAgent, ResearchOutput
    from sdr.repositories import agent_runs, companies as companies_repo
    from sdr.services import enrich_chain

    async def invents_a_gap(self, system, user, ctx, schema=None):
        ctx.tracker.record(400, 100)
        return ResearchOutput(
            summary="Kumar Dental is a dental practice in Pune.",
            pitch_angle="Your reviews go unanswered.",
            lead_signal_key="high_review_volume_no_response",  # never detected
            evidence=["Kumar Dental"],
            confidence=0.9,
        )

    monkeypatch.setattr(CompanyResearchAgent, "complete_validated", invents_a_gap)

    company, lead = await _seed_lead("kumardental.example", "Kumar Dental")
    result = await enrich_chain.run_chain_now(lead["id"])

    research = next(s for s in result["steps"] if s["agent"] == "company_research")
    assert research["output"]["pitch_signal_valid"] is False
    assert research["output"]["pitch_angle"] is None

    stored = await companies_repo.get_company(company["id"])
    assert not stored.get("pitch_angle")

    run = await agent_runs.get_run(research["run_id"])
    assert any(flag["kind"] == "invalid_pitch_signal" for flag in run["guardrail_flags"])


# --- Batch path ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_processing_queues_the_chain_and_is_idempotent(db, stub_network):
    from sdr.services import enrich_chain, jobs

    lead_ids = []
    for index in range(5):
        _, lead = await _seed_lead(f"clinic{index}.example", f"Clinic {index}")
        lead_ids.append(lead["id"])

    first = await enrich_chain.enqueue_chain(lead_ids, batch_key="b1")
    assert first["jobs_queued"] == 5 * len(enrich_chain.CHAIN)

    second = await enrich_chain.enqueue_chain(lead_ids, batch_key="b1")
    assert second["jobs_queued"] == 0

    stats = await jobs.stats()
    assert stats["queued"] == 5 * len(enrich_chain.CHAIN)

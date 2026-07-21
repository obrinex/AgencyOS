"""The whole thing, once, with nobody helping it along.

Every other test in this directory proves one seam. This proves the seams
join: a business is discovered from a map, nobody touches it, and some ticks
later there is an approved email scheduled into that business's own working
hours - with a real contact address that was read off their website rather
than supplied by a spreadsheet.

It exists because five bugs shipped in a single day, and every one of them
lived *between* components that each had passing tests: the audit emitted no
signal for "no website", so scoring read a zero it could not explain; the tick
never researched anything, so a campaign found no qualified leads; ROI figures
were relabelled into rupees without being converted. Each component was fine.
The journey was not.

The LLM and the network are stubbed. Everything else - tick, queue, agents,
chain, pre-flight, scoring, qualification, scheduling - is the real thing.
"""

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "sdr_test")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-hmac")

from test_campaign_flow import (  # noqa: E402  - shared fixtures
    USER, db, ready,
)


@pytest.fixture
def stub_llm(monkeypatch):
    """The copywriter, citing only facts about *this* business.

    The shared fixture in test_campaign_flow cites Pune. This practice is in
    Asansol, and the grounding guard rejected the draft outright - which is
    the guard doing its job. Cold email that invents a location is exactly
    what it exists to stop.
    """
    from sdr.agents.outreach.agent import DraftOutput, PersonalizationAgent

    async def fake_draft(self, *, system, user, ctx, schema=None):
        ctx.tracker.record(320, 130)
        return DraftOutput(
            subject="Booking at Kumar Dental Care",
            body=(
                "Hi - I was looking at Asansol dental practices and noticed "
                "Kumar Dental Care takes bookings by phone only. After-hours "
                "enquiries usually go unanswered when that is the case. Worth "
                "a short conversation?\n\nAmrit"
            ),
            cited_facts=["Kumar Dental Care", "Asansol"],
        )

    monkeypatch.setattr(PersonalizationAgent, "complete_validated", fake_draft)

#: A real-looking small business homepage: the contact address is present, and
#: so is a web designer's, which must not be picked up instead.
HOMEPAGE = """
<html><head><title>Kumar Dental — Asansol</title></head>
<body>
  <h1>Kumar Dental Care</h1>
  <p>Family dentistry in Asansol since 1998. Call 0341 2200000 to book.</p>
  <p>Email us: <a href="mailto:info@kumardental.in">info@kumardental.in</a></p>
  <footer>Site by <a href="mailto:hello@brightpixel.co">Bright Pixel</a></footer>
</body></html>
"""


class _Response:
    """Shape returned by services.safe_fetch.fetch."""
    status_code = 200
    text = HOMEPAGE
    headers = {"content-type": "text/html"}
    elapsed_ms = 240
    tls = {"valid": True}
    url = "https://kumardental.in"


@pytest.fixture
def offline(monkeypatch):
    """No network anywhere: the audit's fetch, and enrichment's own client."""
    import httpx

    from sdr.services import safe_fetch

    async def fake_fetch(url, **kwargs):
        return _Response()

    monkeypatch.setattr(safe_fetch, "fetch", fake_fetch)

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kwargs):
            return httpx.Response(
                200, text=HOMEPAGE,
                headers={"content-type": "text/html; charset=utf-8"},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(httpx, "AsyncClient", _Client)


@pytest.fixture
def stub_research(monkeypatch):
    """The research agent's model call, grounded in the page above."""
    from sdr.agents.research.agent import CompanyResearchAgent

    async def fake(self, *, system, user, ctx, schema=None):
        ctx.tracker.record(200, 90)
        model = schema or self.output_schema
        return model.model_validate({
            "summary": "Family dental practice in Asansol, established 1998.",
            "pitch_angle": "Patients can only book by phone, so after-hours "
                           "enquiries are lost.",
            "talking_points": ["Booking is phone-only", "No website chat"],
            "evidence": ["Kumar Dental Care", "Asansol"],
            "confidence": 0.8,
        })

    monkeypatch.setattr(CompanyResearchAgent, "complete_validated", fake)


@pytest.fixture
def stub_enrichment(monkeypatch):
    """Enrichment's model call. Deliberately returns no contact details -
    the email must come from the page, not the model."""
    from sdr.agents.enrichment.agent import EnrichmentAgent

    async def fake(self, *, system, user, ctx, schema=None):
        ctx.tracker.record(250, 100)
        model = schema or self.output_schema
        return model.model_validate({
            "fields": {"industry": "dental",
                       "description": "Family dental practice in Asansol."},
            "confidence": 0.8,
            "evidence": ["Kumar Dental Care", "Asansol"],
        })

    monkeypatch.setattr(EnrichmentAgent, "complete_validated", fake)


async def _drain_until_quiet(database, max_rounds: int = 15) -> int:
    """Tick and drain until the queue stops producing work.

    The chain staggers its steps 90 seconds apart so a real deployment does
    not fire five agents at one company simultaneously. A test runs in
    milliseconds, so each round pulls every queued job's `run_after` into the
    past first - otherwise the loop sees an empty *due* queue, concludes the
    work is finished, and passes while nothing has actually run.

    That is exactly how this test failed on its first outing.
    """
    from sdr.collections import JOBS
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    rounds = 0
    for _ in range(max_rounds):
        await campaigns_service.tick()
        await database[JOBS].update_many(
            {"status": "queued"},
            {"$set": {"run_after": "2020-01-01T00:00:00+00:00"}},
        )
        result = await jobs.drain()
        rounds += 1
        if not result.get("processed"):
            break
    return rounds


@pytest.mark.asyncio
async def test_a_business_on_a_map_becomes_an_approved_email(
        db, ready, offline, stub_llm, stub_research, stub_enrichment):
    from sdr.collections import COMPANIES
    from sdr.domain import sequence as sequence_domain
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.repositories import companies as companies_repo
    from sdr.repositories import leads as leads_repo
    from sdr.services import campaigns as campaigns_service

    # 1. Discovery. Exactly what the OSM provider writes: a name, a place, a
    #    website. No email address - that is the point.
    await companies_repo.upsert_many([{
        "name": "Kumar Dental Care",
        "domain": "kumardental.in",
        "city": "Asansol",
        "country_code": "IN",
        "industry": "dental",
        "discovery_source": "osm_overpass",
    }])
    company = (await companies_repo.list_companies(limit=10))["items"][0]
    assert not company.get("primary_email"), "discovery does not supply an email"

    lead = await leads_repo.create_from_company(company)
    assert not lead.get("score_version"), "a fresh lead is unscored"

    # 2. Nobody touches it. The tick finds it and runs the whole chain.
    await _drain_until_quiet(db)

    lead = await leads_repo.get_lead(lead["id"])
    company = await companies_repo.get_company(company["id"])

    # The email was read off the page, and it is the practice's own - not the
    # web designer's address sitting in the same footer.
    assert company["primary_email"] == "info@kumardental.in"

    # It was scored, and the score is a real number rather than the 20 that
    # every lead used to get.
    assert lead.get("score_version"), "the lead was never scored"
    assert lead["score"] > 20, f"score {lead['score']} looks like the old floor"
    assert lead["qualification_status"] == "qualified", (
        f"expected qualified, got {lead['qualification_status']}: "
        f"{lead.get('disqualification_reason')}"
    )

    # 3. A campaign, launched against whatever qualified.
    campaign = await campaigns_repo.create_campaign(
        name="Asansol dental", sequence_steps=sequence_domain.DEFAULT_SEQUENCE,
        approval_mode="manual", user=USER, max_touches=3,
    )
    launch = await campaigns_service.launch_campaign(
        campaign["id"], lead_ids=[lead["id"]], user=USER
    )
    assert launch["enrollment"]["enrolled"] == 1, (
        f"the qualified lead was not enrolled: {launch['enrollment']}"
    )

    # 4. Ticks again. A draft appears without anyone asking for one.
    await _drain_until_quiet(db)

    drafts = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"]
    assert len(drafts) == 1, f"expected one draft, got {len(drafts)}"
    draft = drafts[0]
    assert draft["to_email"] == "info@kumardental.in"
    assert draft["subject"] and draft["body"]
    # Every claim traceable to something the system actually found.
    assert draft["cited_facts"]

    # 5. A human approves. That is the only human step in the whole journey.
    approved = await campaigns_service.approve_message(draft["id"], user=USER)
    assert approved["status"] == "approved"
    assert approved["scheduled_for"], "an approved message must be scheduled"

    # 6. It sends - simulated, because that is the shipped default.
    from bson import ObjectId

    from sdr.collections import MESSAGES
    await db[MESSAGES].update_one(
        {"_id": ObjectId(draft["id"])},
        {"$set": {"scheduled_for": "2020-01-01T00:00:00+00:00"}},
    )
    await _drain_until_quiet(db)

    sent = await campaigns_repo.get_message(draft["id"])
    assert sent["status"] == "sent", f"still {sent['status']}: {sent.get('error')}"
    assert sent["simulated"] is True
    # Threading identity was minted, so a reply can be matched to it later.
    assert sent["email_message_id"], "no Message-ID was recorded"

    # And the enrollment moved on rather than stalling on step one.
    enrollment = await campaigns_repo.get_enrollment(sent["enrollment_id"])
    assert enrollment["current_step"] == 1


@pytest.mark.asyncio
async def test_a_business_with_no_website_is_scored_but_not_emailed(
        db, ready, offline, stub_llm, stub_research, stub_enrichment):
    """The other half of the truth, and the one that reads as a failure.

    A business with no site is the best prospect an automation agency can
    have, and it cannot be emailed - there is no page to read an address off.
    It must score for the opportunity it is, and still be refused for email,
    with a reason a human can act on.
    """
    from sdr.repositories import companies as companies_repo
    from sdr.repositories import leads as leads_repo

    await companies_repo.upsert_many([{
        "name": "Shree Clinic", "city": "Asansol", "country_code": "IN",
        "industry": "dental", "discovery_source": "osm_overpass",
    }])
    company = next(c for c in (await companies_repo.list_companies(limit=20))["items"]
                   if c["name"] == "Shree Clinic")
    lead = await leads_repo.create_from_company(company)

    await _drain_until_quiet(db)

    lead = await leads_repo.get_lead(lead["id"])
    assert lead.get("score_version"), "it should still be scored"
    assert lead["qualification_status"] != "qualified"
    reason = (lead.get("disqualification_reason") or "").lower()
    assert "contact" in reason or "route" in reason, (
        f"the reason should name the missing contact route, got: {reason}"
    )

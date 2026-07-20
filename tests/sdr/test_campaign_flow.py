"""The outreach engine, end to end against an in-memory database.

The scenarios that matter most are the ones where NOT sending is the correct
outcome: a reply arriving between approval and dispatch, a crashed send whose
outcome is unknown, a bounce webhook, the daily new-lead cap. The LLM is
stubbed; everything else - tick, queue, agents, pre-flight, counters - is the
real implementation.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "sdr_test")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-hmac")

#: Monday 14:30 IST - inside Indian business hours.
INSIDE_HOURS = datetime.fromisoformat("2026-08-03T09:00:00+00:00")

GOOD_DNS = {
    "overall": "pass",
    "checks": {k: {"status": "pass", "detail": "ok"} for k in ("mx", "spf", "dkim", "dmarc")},
}

USER = {"id": "u-test", "role": "admin"}


@pytest_asyncio.fixture
async def db(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    database = client["sdr_test"]

    import database as database_module
    monkeypatch.setattr(database_module, "db", database)

    import sdr.agents.outreach.agent as outreach_agent
    from sdr.repositories import (
        agent_runs, audits, base, campaigns, companies, identities,
        inbound as inbound_repo, leads, settings, suppression,
    )
    from sdr.services import campaigns as campaigns_service
    from sdr.services import discovery, jobs, preflight
    from sdr.services import inbound as inbound_service
    from sdr.services import meetings as meetings_service
    for module in (agent_runs, audits, base, campaigns, companies, identities,
                   inbound_repo, leads, settings, suppression, campaigns_service,
                   discovery, jobs, preflight, inbound_service, meetings_service,
                   outreach_agent):
        if hasattr(module, "db"):
            monkeypatch.setattr(module, "db", database)
    return database


@pytest_asyncio.fixture
async def ready(db, monkeypatch):
    """Module on, email channel on, healthy warmed identity, frozen clock."""
    from bson import ObjectId
    from sdr.collections import SENDING_IDENTITIES
    from sdr.domain import warmup
    from sdr.repositories import identities as identities_repo
    from sdr.repositories import settings as settings_repo
    from sdr.services import preflight

    await settings_repo.update_settings({
        "module_enabled": True,
        "channels": {"email": True},
        "daily_send_cap": 100,
        "monthly_send_cap": 3000,
        "per_domain_daily_cap": 100,
        "daily_new_leads_cap": 30,
        "cooldown_days_between_campaigns": 30,
    })
    identity = await identities_repo.create_identity(
        identity="hello@sender.example", label="Amrit at Obrinex",
        daily_cap_target=200, dkim_selector="resend",
    )
    await identities_repo.update_dns(identity["id"], GOOD_DNS)
    await db[SENDING_IDENTITIES].update_one(
        {"_id": ObjectId(identity["id"])},
        {"$set": {"status": warmup.HEALTHY,
                  "warmup_started_at": "2026-01-01T00:00:00+00:00"}},
    )

    # Freeze pre-flight's clock inside business hours so tests do not depend
    # on when they are run.
    real_check = preflight.check

    async def frozen_check(**kwargs):
        kwargs.setdefault("now", INSIDE_HOURS)
        return await real_check(**kwargs)

    monkeypatch.setattr(preflight, "check", frozen_check)
    return identity


@pytest.fixture
def stub_llm(monkeypatch):
    """A deterministic, grounded, check-passing draft."""
    from sdr.agents.outreach.agent import DraftOutput, PersonalizationAgent

    async def fake_draft(self, *, system, user, ctx, schema=None):
        ctx.tracker.record(300, 120)
        return DraftOutput(
            subject="Your booking process at Kumar Dental",
            body=(
                "Hi - I looked at your site while researching Pune clinics. "
                "Patients can only book by phone, which usually means missed "
                "calls become missed appointments. Would a two-line summary "
                "of how we fix that be useful?\n\nAmrit"
            ),
            cited_facts=["Kumar Dental", "Pune"],
        )

    monkeypatch.setattr(PersonalizationAgent, "complete_validated", fake_draft)


async def _seed_lead(index: int = 1):
    from sdr.repositories import companies as companies_repo
    from sdr.repositories import leads as leads_repo

    await companies_repo.upsert_many([{
        "name": f"Kumar Dental {index}", "domain": f"kumar{index}.example",
        "city": "Pune", "country_code": "IN",
        "primary_email": f"owner@kumar{index}.example", "industry": "dental",
        "discovery_source": "csv_import",
    }])
    listed = (await companies_repo.list_companies(limit=200))["items"]
    company = next(c for c in listed if c["domain"] == f"kumar{index}.example")
    lead = await leads_repo.create_from_company(company)
    return company, lead


async def _make_running_campaign(lead_ids, approval_mode="manual"):
    from sdr.domain import sequence as sequence_domain
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import campaigns as campaigns_service

    campaign = await campaigns_repo.create_campaign(
        name="Pilot", sequence_steps=sequence_domain.DEFAULT_SEQUENCE,
        approval_mode=approval_mode, user=USER, max_touches=5,
    )
    result = await campaigns_service.launch_campaign(
        campaign["id"], lead_ids=lead_ids, user=USER
    )
    return result["campaign"], result


async def _force_due(db, message_id: str):
    """Backdate a message's schedule so the sweep picks it up now."""
    from bson import ObjectId
    from sdr.collections import MESSAGES
    await db[MESSAGES].update_one(
        {"_id": ObjectId(message_id)},
        {"$set": {"scheduled_for": "2020-01-01T00:00:00+00:00"}},
    )


# --- The full journey ---------------------------------------------------------

@pytest.mark.asyncio
async def test_the_full_flow_draft_approve_send_advance(db, ready, stub_llm):
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    _, lead = await _seed_lead()
    campaign, launch = await _make_running_campaign([lead["id"]])
    assert launch["enrollment"]["enrolled"] == 1
    assert campaign["status"] == "running"

    # Tick 1: the due step-1 enrollment becomes a personalization job.
    report = await campaigns_service.tick()
    assert report["personalization_queued"] == 1
    drained = await jobs.drain()
    assert drained["succeeded"] == 1

    # A draft now waits for a human; nothing is sendable yet.
    pending = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"]
    assert len(pending) == 1
    draft = pending[0]
    assert draft["subject"]
    assert draft["cited_facts"] == ["Kumar Dental", "Pune"]

    # Re-ticking while a draft exists queues nothing - idempotency.
    report2 = await campaigns_service.tick()
    assert report2["personalization_queued"] == 0

    # Approve, force it due, tick sweeps it into a send job.
    approved = await campaigns_service.approve_message(draft["id"], user=USER)
    assert approved["status"] == "approved"
    assert approved["approved_by"] == "u-test"
    await _force_due(db, draft["id"])

    report3 = await campaigns_service.tick()
    assert report3["sends_queued"] == 1
    drained2 = await jobs.drain()
    assert drained2["succeeded"] == 1

    # Sent - simulated, because that is the shipped default.
    sent = await campaigns_repo.get_message(draft["id"])
    assert sent["status"] == "sent"
    assert sent["simulated"] is True
    assert sent["identity"] == "hello@sender.example"

    # The enrollment advanced: step 2 due three days after the send.
    enrollment = (await campaigns_repo.due_enrollments(campaign["id"], now="2099-01-01T00:00:00+00:00"))[0]
    assert enrollment["current_step"] == 1
    assert enrollment["next_touch_at"] > sent["sent_at"]

    stats = (await campaigns_repo.get_campaign(campaign["id"]))["stats"]
    assert stats["sent"] == 1


@pytest.mark.asyncio
async def test_simulate_mode_consumes_no_allowance(db, ready, stub_llm):
    """Rehearsals must not burn quota or warm-up counters."""
    from sdr.repositories import identities as identities_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs
    from sdr.repositories import campaigns as campaigns_repo

    _, lead = await _seed_lead()
    await _make_running_campaign([lead["id"]])
    await campaigns_service.tick()
    await jobs.drain()
    draft = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]
    await campaigns_service.approve_message(draft["id"], user=USER)
    await _force_due(db, draft["id"])
    await campaigns_service.tick()
    await jobs.drain()

    assert (await campaigns_repo.get_message(draft["id"]))["status"] == "sent"
    assert await identities_repo.usage_today("hello@sender.example") == 0
    assert await identities_repo.org_usage_this_month() == 0


@pytest.mark.asyncio
async def test_auto_mode_skips_the_approval_queue(db, ready, stub_llm):
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    _, lead = await _seed_lead()
    await _make_running_campaign([lead["id"]], approval_mode="auto")
    await campaigns_service.tick()
    await jobs.drain()

    messages = (await campaigns_repo.list_messages())["items"]
    assert len(messages) == 1
    assert messages[0]["status"] == "approved"
    assert messages[0]["scheduled_for"]  # windowed at generation


# --- Stop-condition safety ----------------------------------------------------

@pytest.mark.asyncio
async def test_mark_replied_stops_the_sequence_and_cancels_drafts(db, ready, stub_llm):
    """The most important property in the file: a reply means silence."""
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    _, lead = await _seed_lead()
    campaign, _ = await _make_running_campaign([lead["id"]])
    await campaigns_service.tick()
    await jobs.drain()
    draft = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]

    result = await campaigns_service.mark_lead_replied(lead["id"], user=USER)
    assert result["enrollments_stopped"] == 1

    # The pending draft died with the enrollment.
    assert (await campaigns_repo.get_message(draft["id"]))["status"] == "cancelled"
    summary = await campaigns_repo.enrollment_summary(campaign["id"])
    assert summary["stopped_reasons"] == {"replied": 1}

    # And nothing new is ever queued for it.
    report = await campaigns_service.tick()
    assert report["personalization_queued"] == 0


@pytest.mark.asyncio
async def test_a_reply_between_approval_and_send_still_stops_the_email(db, ready, stub_llm):
    """The world moves after approval; the send agent must notice."""
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    _, lead = await _seed_lead()
    await _make_running_campaign([lead["id"]])
    await campaigns_service.tick()
    await jobs.drain()
    draft = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]
    await campaigns_service.approve_message(draft["id"], user=USER)
    await _force_due(db, draft["id"])
    await campaigns_service.tick()

    # The reply lands after the send job is queued but before it runs.
    await campaigns_service.mark_lead_replied(lead["id"], user=USER)
    await jobs.drain()

    final = await campaigns_repo.get_message(draft["id"])
    assert final["status"] == "cancelled"
    assert final["simulated"] is False  # nothing was dispatched, even virtually


@pytest.mark.asyncio
async def test_suppressed_leads_are_skipped_at_enrollment(db, ready):
    from sdr.repositories import suppression as suppression_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.errors import ValidationError

    _, lead = await _seed_lead()
    await suppression_repo.suppress(value=lead["email"], reason="unsubscribe")

    campaign = await campaigns_repo.create_campaign(
        name="X", sequence_steps=__import__("sdr.domain.sequence", fromlist=["DEFAULT_SEQUENCE"]).DEFAULT_SEQUENCE,
        approval_mode="manual", user=USER, max_touches=5,
    )
    with pytest.raises(ValidationError) as exc:
        await campaigns_service.launch_campaign(campaign["id"], lead_ids=[lead["id"]], user=USER)
    assert "suppressed" in str(exc.value)


@pytest.mark.asyncio
async def test_one_lead_cannot_be_in_two_active_sequences(db, ready):
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.domain import sequence as sequence_domain

    _, lead = await _seed_lead()
    await _make_running_campaign([lead["id"]])

    second = await campaigns_repo.create_campaign(
        name="Second", sequence_steps=sequence_domain.DEFAULT_SEQUENCE,
        approval_mode="manual", user=USER, max_touches=5,
    )
    report = await campaigns_repo.enroll_leads(second["id"], [lead["id"]], cooldown_days=30)
    assert report["enrolled"] == 0
    assert "active sequence" in report["skipped"][0]["reason"]


# --- Pacing -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_daily_new_lead_cap_paces_step_one(db, ready, monkeypatch, stub_llm):
    from sdr.repositories import settings as settings_repo
    from sdr.services import campaigns as campaigns_service

    await settings_repo.update_settings({"daily_new_leads_cap": 2})

    lead_ids = []
    for index in range(1, 5):
        _, lead = await _seed_lead(index)
        lead_ids.append(lead["id"])
    await _make_running_campaign(lead_ids)

    report = await campaigns_service.tick()
    # Two started today; the other two wait for tomorrow's slots.
    assert report["personalization_queued"] == 2
    assert report["new_lead_slots_exhausted"] is True


# --- Send-agent safety --------------------------------------------------------

@pytest.mark.asyncio
async def test_a_crashed_send_parks_in_needs_review_and_never_redials(db, ready, monkeypatch):
    """A message stuck in `sending` means a previous attempt died mid-call.
    The retry must not guess."""
    from bson import ObjectId
    from sdr.agents.base.agent import AgentContext
    from sdr.agents.outreach.agent import OutreachSendAgent
    from sdr.collections import MESSAGES
    from sdr.errors import ValidationError
    from sdr.providers import email_resend
    from sdr.repositories import campaigns as campaigns_repo

    _, lead = await _seed_lead()
    campaign, _ = await _make_running_campaign([lead["id"]])
    enrollment = (await campaigns_repo.due_enrollments(campaign["id"]))[0]
    message = await campaigns_repo.create_message(
        campaign_id=campaign["id"], enrollment_id=enrollment["id"],
        lead_id=lead["id"], step_index=0, to_email=lead["email"],
        country_code="IN", subject="s", body="b", cited_facts=[],
        status="approved", scheduled_for=None,
    )
    await db[MESSAGES].update_one(
        {"_id": ObjectId(message["id"])}, {"$set": {"status": "sending"}}
    )

    provider_calls = []

    async def spy(**kwargs):
        provider_calls.append(kwargs)

    monkeypatch.setattr(email_resend, "send", spy)

    with pytest.raises(ValidationError):
        await OutreachSendAgent().run({"message_id": message["id"]}, AgentContext())

    assert provider_calls == []  # the provider was never touched
    assert (await campaigns_repo.get_message(message["id"]))["status"] == "needs_review"


@pytest.mark.asyncio
async def test_a_rate_limited_live_send_releases_and_requeues(db, ready, monkeypatch, stub_llm):
    from sdr.agents.base.agent import AgentContext
    from sdr.agents.outreach.agent import OutreachSendAgent
    from sdr.errors import RateLimitError
    from sdr.providers import email_resend
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.repositories import identities as identities_repo
    from sdr.repositories import settings as settings_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    await settings_repo.update_settings({"send_mode": "live"})

    _, lead = await _seed_lead()
    await _make_running_campaign([lead["id"]])
    await campaigns_service.tick()
    await jobs.drain()
    draft = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]
    await campaigns_service.approve_message(draft["id"], user=USER)
    await _force_due(db, draft["id"])

    async def refuse(**kwargs):
        raise RateLimitError("429 from Resend")

    monkeypatch.setattr(email_resend, "send", refuse)

    with pytest.raises(RateLimitError):
        await OutreachSendAgent().run({"message_id": draft["id"]}, AgentContext())

    message = await campaigns_repo.get_message(draft["id"])
    assert message["status"] == "approved"          # back in the pool
    assert message["send_attempt"] == 1             # job key rotates
    # A definite refusal released every claim.
    assert await identities_repo.usage_today("hello@sender.example") == 0
    assert await identities_repo.org_usage_this_month() == 0


@pytest.mark.asyncio
async def test_an_ambiguous_live_failure_keeps_the_claim_and_asks_a_human(db, ready, monkeypatch, stub_llm):
    from sdr.agents.base.agent import AgentContext
    from sdr.agents.outreach.agent import OutreachSendAgent
    from sdr.errors import ProviderError, ValidationError
    from sdr.providers import email_resend
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.repositories import identities as identities_repo
    from sdr.repositories import settings as settings_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    await settings_repo.update_settings({"send_mode": "live"})

    _, lead = await _seed_lead()
    await _make_running_campaign([lead["id"]])
    await campaigns_service.tick()
    await jobs.drain()
    draft = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]
    await campaigns_service.approve_message(draft["id"], user=USER)
    await _force_due(db, draft["id"])

    async def timeout(**kwargs):
        raise ProviderError("connection reset by peer")

    monkeypatch.setattr(email_resend, "send", timeout)

    with pytest.raises(ValidationError):
        await OutreachSendAgent().run({"message_id": draft["id"]}, AgentContext())

    message = await campaigns_repo.get_message(draft["id"])
    assert message["status"] == "needs_review"
    assert "Resend" in message["error"]
    # Possibly-sent: the allowance stays consumed, conservatively.
    assert await identities_repo.usage_today("hello@sender.example") == 1


@pytest.mark.asyncio
async def test_a_live_send_dispatches_with_footer_and_headers(db, ready, monkeypatch, stub_llm):
    from sdr.agents.base.agent import AgentContext
    from sdr.agents.outreach.agent import OutreachSendAgent
    from sdr.providers import email_resend
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.repositories import settings as settings_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    await settings_repo.update_settings({"send_mode": "live"})

    _, lead = await _seed_lead()
    campaign, _ = await _make_running_campaign([lead["id"]])
    await campaigns_service.tick()
    await jobs.drain()
    draft = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]
    await campaigns_service.approve_message(draft["id"], user=USER)
    await _force_due(db, draft["id"])

    captured = {}

    async def capture(**kwargs):
        captured.update(kwargs)
        return {"provider_message_id": "re_abc123"}

    monkeypatch.setattr(email_resend, "send", capture)

    result = await OutreachSendAgent().run({"message_id": draft["id"]}, AgentContext())
    assert result.output["sent"] is True

    # The dispatched body carries the legal frame the human never edits.
    assert "Unsubscribe (one click, permanent):" in captured["text_body"]
    assert "/api/public/sdr/unsubscribe?email=" in captured["text_body"]
    assert captured["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert captured["from_identity"] == "hello@sender.example"

    message = await campaigns_repo.get_message(draft["id"])
    assert message["status"] == "sent"
    assert message["provider_message_id"] == "re_abc123"
    assert message["simulated"] is False


# --- Rejection and regeneration -----------------------------------------------

@pytest.mark.asyncio
async def test_reject_and_regenerate_produces_a_fresh_draft(db, ready, stub_llm):
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    _, lead = await _seed_lead()
    await _make_running_campaign([lead["id"]])
    await campaigns_service.tick()
    await jobs.drain()
    draft = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]

    result = await campaigns_service.reject_message(draft["id"], user=USER, regenerate=True)
    assert result["regenerating"] is True

    # The regen counter rotates the job key, so a new draft is producible
    # even though the old personalization job completed.
    report = await campaigns_service.tick()
    assert report["personalization_queued"] == 1
    await jobs.drain()
    fresh = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"]
    assert len(fresh) == 1
    assert fresh[0]["id"] != draft["id"]


@pytest.mark.asyncio
async def test_reject_and_stop_ends_the_sequence(db, ready, stub_llm):
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    _, lead = await _seed_lead()
    campaign, _ = await _make_running_campaign([lead["id"]])
    await campaigns_service.tick()
    await jobs.drain()
    draft = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]

    await campaigns_service.reject_message(draft["id"], user=USER, regenerate=False)
    summary = await campaigns_repo.enrollment_summary(campaign["id"])
    assert summary["stopped_reasons"] == {"manual": 1}


@pytest.mark.asyncio
async def test_edited_approval_reruns_the_copy_checks(db, ready, stub_llm):
    """An operator's edit can fail hygiene as easily as a model's draft."""
    from sdr.errors import ValidationError
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    _, lead = await _seed_lead()
    await _make_running_campaign([lead["id"]])
    await campaigns_service.tick()
    await jobs.drain()
    draft = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]

    with pytest.raises(ValidationError) as exc:
        await campaigns_service.approve_message(
            draft["id"], user=USER,
            body="Click here https://tracking.example/x to see our deck!",
        )
    assert "URL" in str(exc.value)


# --- Webhooks -----------------------------------------------------------------

def _sign(secret_b64: str, svix_id: str, timestamp: str, body: bytes) -> str:
    import base64
    import hashlib
    import hmac as hmac_mod

    key = base64.b64decode(secret_b64)
    signed = f"{svix_id}.{timestamp}.".encode() + body
    return "v1," + base64.b64encode(
        hmac_mod.new(key, signed, hashlib.sha256).digest()
    ).decode()


class _FakeRequest:
    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers

    async def body(self):
        return self._body


@pytest.mark.asyncio
async def test_a_bounce_webhook_suppresses_and_stops(db, ready, monkeypatch, stub_llm):
    import base64
    import json as json_mod
    import time as time_mod

    from routers.public import resend_webhook
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.repositories import suppression as suppression_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    # A sent live message to bounce.
    from sdr.repositories import settings as settings_repo
    from sdr.providers import email_resend
    await settings_repo.update_settings({"send_mode": "live"})
    _, lead = await _seed_lead()
    campaign, _ = await _make_running_campaign([lead["id"]])
    await campaigns_service.tick()
    await jobs.drain()
    draft = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]
    await campaigns_service.approve_message(draft["id"], user=USER)
    await _force_due(db, draft["id"])

    async def ok(**kwargs):
        return {"provider_message_id": "re_bounce_1"}
    monkeypatch.setattr(email_resend, "send", ok)
    from sdr.agents.base.agent import AgentContext
    from sdr.agents.outreach.agent import OutreachSendAgent
    await OutreachSendAgent().run({"message_id": draft["id"]}, AgentContext())

    secret_b64 = base64.b64encode(b"webhook-test-secret-32-bytes-xx").decode()
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", f"whsec_{secret_b64}")

    body = json_mod.dumps({
        "type": "email.bounced",
        "data": {"email_id": "re_bounce_1"},
    }).encode()
    timestamp = str(int(time_mod.time()))
    request = _FakeRequest(body, {
        "svix-id": "msg_1", "svix-timestamp": timestamp,
        "svix-signature": _sign(secret_b64, "msg_1", timestamp, body),
    })

    result = await resend_webhook(request)
    assert result["matched"] is True

    message = await campaigns_repo.get_message(draft["id"])
    assert message["status"] == "bounced"
    assert await suppression_repo.is_suppressed(email=lead["email"])
    summary = await campaigns_repo.enrollment_summary(campaign["id"])
    assert summary["stopped_reasons"] == {"bounced": 1}


@pytest.mark.asyncio
async def test_forged_and_stale_webhooks_are_refused(db, monkeypatch):
    import base64
    import time as time_mod

    from fastapi import HTTPException
    from routers.public import resend_webhook

    secret_b64 = base64.b64encode(b"webhook-test-secret-32-bytes-xx").decode()
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", f"whsec_{secret_b64}")

    body = b'{"type":"email.complained","data":{"email_id":"x"}}'
    now = str(int(time_mod.time()))

    with pytest.raises(HTTPException) as forged:
        await resend_webhook(_FakeRequest(body, {
            "svix-id": "m", "svix-timestamp": now, "svix-signature": "v1,forged",
        }))
    assert forged.value.status_code == 401

    stale_time = str(int(time_mod.time()) - 3600)
    with pytest.raises(HTTPException) as stale:
        await resend_webhook(_FakeRequest(body, {
            "svix-id": "m", "svix-timestamp": stale_time,
            "svix-signature": _sign(secret_b64, "m", stale_time, body),
        }))
    assert stale.value.status_code == 401


@pytest.mark.asyncio
async def test_an_unconfigured_webhook_secret_fails_closed(db, monkeypatch):
    from fastapi import HTTPException
    from routers.public import resend_webhook

    monkeypatch.delenv("RESEND_WEBHOOK_SECRET", raising=False)
    with pytest.raises(HTTPException) as exc:
        await resend_webhook(_FakeRequest(b"{}", {}))
    assert exc.value.status_code == 503

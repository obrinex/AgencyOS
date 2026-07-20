"""Inbound replies: matching, classification, and what each category does.

The test this file exists for is
`test_an_out_of_office_defers_and_never_counts_as_a_reply`. Treating an
absence responder as engagement stops outreach permanently and marks the lead
as responsive when nobody read anything — a failure that looks like the best
outcome the system produces and is therefore never noticed. Everything else
here is ordinary coverage; that one is the bug that would otherwise ship.
"""

import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "sdr_test")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-hmac")

from test_campaign_flow import (  # noqa: E402  - shared fixtures and helpers
    USER, _force_due, _make_running_campaign, _seed_lead, db, ready, stub_llm,
)

SECRET = "inbound-test-secret"


# --- The pure part: machine detection -----------------------------------------

@pytest.mark.parametrize("subject", [
    "Out of Office: Re: quick question",
    "Automatic reply: Re: your email",
    "I am on vacation until 5 August",
    "Re: your email (currently unavailable)",
    "Abwesenheitsnotiz",
    "AutoReply: away from my desk",
])
def test_absence_subjects_are_caught_without_a_model(subject):
    from sdr.domain import inbound

    assert inbound.detect_machine_reply(
        headers={}, subject=subject, from_email="owner@kumar1.example"
    ) == "out_of_office"


@pytest.mark.parametrize("headers", [
    {"Auto-Submitted": "auto-replied"},
    {"X-Autoreply": "yes"},
    {"Precedence": "auto_reply"},
    {"auto-submitted": "auto-generated"},
])
def test_rfc3834_headers_are_authoritative(headers):
    from sdr.domain import inbound

    assert inbound.detect_machine_reply(
        headers=headers, subject="Re: quick question", from_email="a@b.example"
    ) == "auto_reply"


def test_auto_submitted_no_is_a_real_human():
    """`Auto-Submitted: no` is what well-behaved clients put on ordinary mail.
    Reading it as a machine would silence genuine replies."""
    from sdr.domain import inbound

    assert inbound.detect_machine_reply(
        headers={"Auto-Submitted": "no"}, subject="Re: quick question",
        from_email="owner@kumar1.example",
    ) is None


def test_an_ordinary_reply_is_not_flagged_as_a_machine():
    from sdr.domain import inbound

    assert inbound.detect_machine_reply(
        headers={"From": "Owner <owner@kumar1.example>"},
        subject="Re: your note about our booking page",
        from_email="owner@kumar1.example",
    ) is None


def test_bounces_are_recognised_by_sender_and_subject():
    from sdr.domain import inbound

    assert inbound.detect_machine_reply(
        headers={}, subject="Re: hi", from_email="MAILER-DAEMON@kumar1.example"
    ) == "bounce"
    assert inbound.detect_machine_reply(
        headers={}, subject="Undeliverable: quick question",
        from_email="postmaster@kumar1.example",
    ) == "bounce"


def test_only_human_categories_count_as_a_reply():
    """The invariant the whole module protects."""
    from sdr.domain import inbound

    for category in inbound.MACHINE_CATEGORIES:
        action = inbound.action_for(category)
        assert action["counts_as_reply"] is False
        assert action["stop_reason"] is None

    for category in inbound.HUMAN_CATEGORIES:
        assert inbound.action_for(category)["counts_as_reply"] is True

    # And only out-of-office defers.
    assert inbound.action_for("out_of_office")["defer_days"] == inbound.OOO_DEFER_DAYS
    assert inbound.action_for("auto_reply")["defer_days"] == 0


def test_message_ids_are_pulled_from_either_header():
    from sdr.domain import inbound

    order = inbound.match_order(
        in_reply_to="<sdr-b@x>",
        references="<sdr-a@x> <sdr-b@x>",
    )
    # In-Reply-To wins; the chain follows, nearest ancestor first, no repeats.
    assert order == ["<sdr-b@x>", "<sdr-a@x>"]
    assert inbound.match_order(None, None) == []


# --- Signature verification ---------------------------------------------------

def _signed(payload: dict, *, secret=SECRET, timestamp=None):
    body = json.dumps(payload).encode()
    timestamp = timestamp or str(int(time.time()))
    signature = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return body, timestamp, signature


def test_a_forged_or_stale_reply_is_refused(monkeypatch):
    from sdr.providers import inbound_cloudflare

    monkeypatch.setenv("SDR_INBOUND_WEBHOOK_SECRET", SECRET)
    body, timestamp, signature = _signed({"from": "a@b.example"})

    assert inbound_cloudflare.verify(
        body=body, timestamp=timestamp, signature=signature)[0] is True
    # Same body, wrong key.
    _, ts2, forged = _signed({"from": "a@b.example"}, secret="wrong")
    assert inbound_cloudflare.verify(
        body=body, timestamp=ts2, signature=forged)[0] is False
    # Right key, replayed an hour later.
    old = str(int(time.time()) - 3600)
    _, _, old_sig = _signed({"from": "a@b.example"}, timestamp=old)
    assert inbound_cloudflare.verify(
        body=body, timestamp=old, signature=old_sig) == (False, "stale")


def test_without_a_secret_nothing_is_trusted(monkeypatch):
    """A forged reply suppresses addresses and stops sequences. Failing open
    here is worse than not accepting replies at all."""
    from sdr.providers import inbound_cloudflare

    monkeypatch.delenv("SDR_INBOUND_WEBHOOK_SECRET", raising=False)
    assert inbound_cloudflare.is_configured() is False
    body, timestamp, signature = _signed({})
    assert inbound_cloudflare.verify(
        body=body, timestamp=timestamp, signature=signature) == (False, "not_configured")


def test_the_worker_envelope_is_normalized():
    from sdr.providers import inbound_cloudflare

    normalized = inbound_cloudflare.normalize({
        "from": "Dr Kumar <owner@kumar1.example>",
        "to": "hello@sender.example",
        "subject": "Re: your booking page",
        "text": "Sounds interesting, can we talk Thursday?",
        "headers": {
            "Message-ID": "<reply-1@kumar1.example>",
            "In-Reply-To": "<sdr-abc@sender.example>",
            "References": "<sdr-abc@sender.example>",
        },
    })
    assert normalized["from_email"] == "owner@kumar1.example"
    assert normalized["ingest_key"] == "<reply-1@kumar1.example>"
    assert normalized["in_reply_to"] == "<sdr-abc@sender.example>"
    assert normalized["provider"] == "cloudflare"


# --- End to end ---------------------------------------------------------------

async def _send_first_email_live(db, monkeypatch):
    """Run one campaign to a real (stubbed) send and return the message."""
    from sdr.agents.base.agent import AgentContext
    from sdr.agents.outreach.agent import OutreachSendAgent
    from sdr.providers import email_resend
    from sdr.repositories import campaigns as campaigns_repo
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

    async def capture(**kwargs):
        return {"provider_message_id": "re_inbound_test"}

    monkeypatch.setattr(email_resend, "send", capture)
    await OutreachSendAgent().run({"message_id": draft["id"]}, AgentContext())
    return await campaigns_repo.get_message(draft["id"])


def _reply(sent, *, subject, body, headers=None, key="<reply-1@kumar1.example>"):
    return {
        "provider": "cloudflare",
        "ingest_key": key,
        "from_email": sent["to_email"],
        "to_email": sent["identity"],
        "subject": subject,
        "text_body": body,
        "headers": headers or {},
        "in_reply_to": sent["email_message_id"],
        "references": sent["email_message_id"],
        "received_at": None,
    }


def _stub_classifier(monkeypatch, category, confidence=0.95):
    from sdr.agents.inbound import agent as inbound_agent

    async def fake_run(self, payload, ctx=None):
        class _Result:
            output = {"category": category, "confidence": confidence,
                      "reasoning": "stubbed", "needs_human": confidence < 0.6}
        return _Result()

    monkeypatch.setattr(inbound_agent.InboundClassifierAgent, "run", fake_run)


@pytest.mark.asyncio
async def test_an_interested_reply_threads_stops_and_stamps(db, ready, monkeypatch, stub_llm):
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import inbound as inbound_service

    sent = await _send_first_email_live(db, monkeypatch)
    _stub_classifier(monkeypatch, "interested")

    result = await inbound_service.ingest(_reply(
        sent, subject="Re: your booking page",
        body="Sounds interesting - can we talk Thursday?",
    ))

    # Matched by the Message-ID we minted, not by guessing at the sender.
    assert result["match_method"] == "threaded"
    assert result["category"] == "interested"
    assert "stopped:replied" in result["action_taken"]
    assert "lead_marked_replied" in result["action_taken"]

    enrollment = await campaigns_repo.get_enrollment(sent["enrollment_id"])
    assert enrollment["status"] == "stopped"
    assert enrollment["stopped_reason"] == "replied"


@pytest.mark.asyncio
async def test_an_out_of_office_defers_and_never_counts_as_a_reply(
        db, ready, monkeypatch, stub_llm):
    """**The trap.** An absence responder must not stop the sequence, must not
    stamp the lead as replied, and must push the next touch out instead."""
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import inbound as inbound_service

    sent = await _send_first_email_live(db, monkeypatch)

    before = await campaigns_repo.get_enrollment(sent["enrollment_id"])

    # No classifier stub: the headers alone must be enough. If this test only
    # passed via the model, the real protection would not exist.
    result = await inbound_service.ingest(_reply(
        sent,
        subject="Automatic reply: Re: your booking page",
        body="I am on annual leave until 5 August with limited access to email.",
        headers={"Auto-Submitted": "auto-replied"},
    ))

    assert result["category"] == "out_of_office"

    stored = await inbound_service.inbound_repo.get(result["inbound_id"])
    assert stored["category_source"] == "headers"      # no model was consulted

    # The sequence is alive.
    after = await campaigns_repo.get_enrollment(sent["enrollment_id"])
    assert after["status"] == "active"
    assert after["stopped_reason"] in (None, "")
    assert "deferred:7d" in result["action_taken"]
    assert after["next_touch_at"] > before["next_touch_at"]

    # And the lead was never marked as having answered.
    lead = await db.leads.find_one({"_id": __import__("bson").ObjectId(sent["lead_id"])})
    assert lead.get("replied_at") is None


@pytest.mark.asyncio
async def test_a_generic_auto_reply_changes_nothing(db, ready, monkeypatch, stub_llm):
    """A ticket acknowledgement is not engagement - but it is not a reason to
    delay the follow-up either."""
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import inbound as inbound_service

    sent = await _send_first_email_live(db, monkeypatch)
    before = await campaigns_repo.get_enrollment(sent["enrollment_id"])

    result = await inbound_service.ingest(_reply(
        sent, subject="[Ticket #4821] We received your message",
        body="Your message has been logged.",
        headers={"Precedence": "bulk"},
    ))

    assert result["category"] == "auto_reply"
    after = await campaigns_repo.get_enrollment(sent["enrollment_id"])
    assert after["status"] == "active"
    assert after["next_touch_at"] == before["next_touch_at"]
    assert result["action_taken"] == ["none"]


@pytest.mark.asyncio
async def test_an_unsubscribe_request_suppresses_permanently(db, ready, monkeypatch, stub_llm):
    from sdr.repositories import suppression as suppression_repo
    from sdr.services import inbound as inbound_service

    sent = await _send_first_email_live(db, monkeypatch)
    _stub_classifier(monkeypatch, "unsubscribe_request")

    result = await inbound_service.ingest(_reply(
        sent, subject="Re: your booking page", body="Please remove me from your list.",
    ))

    assert "suppressed" in result["action_taken"]
    assert await suppression_repo.is_suppressed(email=sent["to_email"])
    # An opt-out is not a "reply" for pipeline purposes.
    assert "lead_marked_replied" not in result["action_taken"]


@pytest.mark.asyncio
async def test_wrong_person_stops_with_its_own_reason(db, ready, monkeypatch, stub_llm):
    """Distinct from `replied` so the contact can be re-researched rather than
    the company being written off."""
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import inbound as inbound_service

    sent = await _send_first_email_live(db, monkeypatch)
    _stub_classifier(monkeypatch, "wrong_person")

    await inbound_service.ingest(_reply(
        sent, subject="Re: your booking page",
        body="I don't handle marketing - try Priya.",
    ))

    enrollment = await campaigns_repo.get_enrollment(sent["enrollment_id"])
    assert enrollment["stopped_reason"] == "wrong_person"


@pytest.mark.asyncio
async def test_a_replayed_webhook_is_processed_once(db, ready, monkeypatch, stub_llm):
    """Providers retry. Stopping an enrollment twice is harmless; suppressing
    and stamping twice is not."""
    from sdr.services import inbound as inbound_service

    sent = await _send_first_email_live(db, monkeypatch)
    _stub_classifier(monkeypatch, "interested")

    payload = _reply(sent, subject="Re: hi", body="Yes, let's talk.")
    first = await inbound_service.ingest(payload)
    second = await inbound_service.ingest(payload)

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["inbound_id"] == first["inbound_id"]


@pytest.mark.asyncio
async def test_an_unthreaded_reply_falls_back_to_the_sender_and_asks_a_human(
        db, ready, monkeypatch, stub_llm):
    """A from-address match cannot tell two campaigns apart, so it routes but
    does not act unsupervised."""
    from sdr.services import inbound as inbound_service

    sent = await _send_first_email_live(db, monkeypatch)
    _stub_classifier(monkeypatch, "interested")

    payload = _reply(sent, subject="your email", body="Yes please.")
    payload["in_reply_to"] = None
    payload["references"] = None

    result = await inbound_service.ingest(payload)
    assert result["match_method"] == "sender"

    stored = await inbound_service.inbound_repo.get(result["inbound_id"])
    assert stored["needs_human"] is True
    assert stored["enrollment_id"] == sent["enrollment_id"]


@pytest.mark.asyncio
async def test_a_reply_we_cannot_route_is_still_stored(db, ready, monkeypatch, stub_llm):
    """An unmatched reply is a person waiting on an answer, not a 200 and a
    shrug."""
    from sdr.repositories import inbound as inbound_repo
    from sdr.services import inbound as inbound_service

    _stub_classifier(monkeypatch, "interested")

    result = await inbound_service.ingest({
        "provider": "cloudflare", "ingest_key": "<stranger@nowhere.example>",
        "from_email": "stranger@nowhere.example", "to_email": "hello@sender.example",
        "subject": "hello?", "text_body": "Who is this?", "headers": {},
        "in_reply_to": None, "references": None, "received_at": None,
    })

    assert result["match_method"] == "none"
    stored = await inbound_repo.get(result["inbound_id"])
    assert stored["needs_human"] is True
    assert stored["text_body"] == "Who is this?"
    assert await inbound_repo.count_unmatched() == 1


@pytest.mark.asyncio
async def test_a_human_override_restarts_a_wrongly_stopped_sequence(
        db, ready, monkeypatch, stub_llm):
    """The override exists to undo a wrong call, not to relabel a row. The
    case it is built for: the classifier read an absence responder as
    interest, stopping outreach to a live lead."""
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import inbound as inbound_service

    sent = await _send_first_email_live(db, monkeypatch)
    _stub_classifier(monkeypatch, "interested")

    result = await inbound_service.ingest(_reply(
        sent, subject="Re: hi", body="I am away until Monday.",
    ))
    assert (await campaigns_repo.get_enrollment(
        sent["enrollment_id"]))["status"] == "stopped"

    corrected = await inbound_service.reclassify(
        result["inbound_id"], "out_of_office", user=USER
    )

    assert corrected["changed"] is True
    assert "resumed" in corrected["action_taken"]
    assert corrected["category_source"] == "human"
    assert corrected["needs_human"] is False

    enrollment = await campaigns_repo.get_enrollment(sent["enrollment_id"])
    assert enrollment["status"] == "active"
    assert enrollment["stopped_reason"] is None


@pytest.mark.asyncio
async def test_an_override_never_resurrects_a_bounced_or_unsubscribed_lead(
        db, ready, monkeypatch, stub_llm):
    """A suppression outranks a human's opinion about one email. Relabelling
    must not put a dead address or an opt-out back into rotation."""
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.services import inbound as inbound_service

    sent = await _send_first_email_live(db, monkeypatch)
    _stub_classifier(monkeypatch, "unsubscribe_request")

    result = await inbound_service.ingest(_reply(
        sent, subject="Re: hi", body="Remove me.",
    ))
    assert (await campaigns_repo.get_enrollment(
        sent["enrollment_id"]))["stopped_reason"] == "unsubscribed"

    corrected = await inbound_service.reclassify(
        result["inbound_id"], "interested", user=USER
    )

    assert "resumed" not in corrected["action_taken"]
    enrollment = await campaigns_repo.get_enrollment(sent["enrollment_id"])
    assert enrollment["status"] == "stopped"
    assert enrollment["stopped_reason"] == "unsubscribed"


@pytest.mark.asyncio
async def test_the_inbox_summary_counts_what_needs_a_human(
        db, ready, monkeypatch, stub_llm):
    from sdr.services import inbound as inbound_service

    _stub_classifier(monkeypatch, "interested")
    await inbound_service.ingest({
        "provider": "cloudflare", "ingest_key": "<a@nowhere.example>",
        "from_email": "a@nowhere.example", "to_email": "hello@sender.example",
        "subject": "hello?", "text_body": "Who is this?", "headers": {},
        "in_reply_to": None, "references": None, "received_at": None,
    })

    summary = await inbound_service.summary()
    assert summary["total"] == 1
    assert summary["unmatched"] == 1
    assert summary["needs_human"] == 1
    assert summary["by_category"]["interested"] == 1


@pytest.mark.asyncio
async def test_a_classifier_outage_parks_for_a_human_and_touches_nothing(
        db, ready, monkeypatch, stub_llm):
    from sdr.agents.inbound import agent as inbound_agent
    from sdr.repositories import inbound as inbound_repo
    from sdr.services import inbound as inbound_service

    sent = await _send_first_email_live(db, monkeypatch)

    async def blow_up(self, payload, ctx=None):
        raise RuntimeError("provider down")

    monkeypatch.setattr(inbound_agent.InboundClassifierAgent, "run", blow_up)

    result = await inbound_service.ingest(_reply(
        sent, subject="Re: hi", body="Tell me more.",
    ))

    stored = await inbound_repo.get(result["inbound_id"])
    assert stored["needs_human"] is True
    assert stored["category_source"] == "error"

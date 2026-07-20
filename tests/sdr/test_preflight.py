"""Send pre-flight, suppression and rate limiting.

This is the layer where a bug means emailing someone who explicitly asked us
to stop. Every check gets a test for both directions - it refuses when it
should, and it does not refuse when it shouldn't, because a gate that always
says no gets bypassed.
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

#: A Monday, 14:30 IST / 09:00 UTC - inside Indian business hours.
INSIDE_HOURS = datetime.fromisoformat("2026-08-03T09:00:00+00:00")

GOOD_DNS = {
    "overall": "pass",
    "checks": {
        "mx": {"status": "pass", "detail": "ok"},
        "spf": {"status": "pass", "detail": "ok"},
        "dkim": {"status": "pass", "detail": "ok"},
        "dmarc": {"status": "pass", "detail": "ok"},
    },
}


@pytest_asyncio.fixture
async def db(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    database = client["sdr_test"]

    import database as database_module
    monkeypatch.setattr(database_module, "db", database)

    from sdr.repositories import (
        agent_runs, audits, base, companies, identities, leads, overview,
        settings, suppression,
    )
    from sdr.services import discovery, jobs, preflight
    for module in (agent_runs, audits, base, companies, identities, leads,
                   overview, settings, suppression, discovery, jobs, preflight):
        if hasattr(module, "db"):
            monkeypatch.setattr(module, "db", database)
    return database


@pytest_asyncio.fixture
async def ready(db):
    """Module on, email enabled, one healthy fully-warmed identity."""
    from sdr.domain import warmup
    from sdr.collections import SENDING_IDENTITIES
    from sdr.repositories import identities as identities_repo
    from sdr.repositories import settings as settings_repo

    await settings_repo.update_settings({
        "module_enabled": True,
        "channels": {"email": True, "whatsapp": False, "sms": False,
                     "linkedin": False, "voice": False},
        "daily_send_cap": 500,
        "per_domain_daily_cap": 3,
    })

    identity = await identities_repo.create_identity(
        identity="hello@obrinex.space", daily_cap_target=200, dkim_selector="resend"
    )
    await identities_repo.update_dns(identity["id"], GOOD_DNS)
    await db[SENDING_IDENTITIES].update_one(
        {"_id": __import__("bson").ObjectId(identity["id"])},
        {"$set": {
            "status": warmup.HEALTHY,
            # Backdated so warm-up is complete and caps are at target.
            "warmup_started_at": "2026-01-01T00:00:00+00:00",
        }},
    )
    return identity


async def run(**kwargs):
    from sdr.services import preflight
    defaults = {
        "recipient_email": "owner@prospect.example",
        "country_code": "IN",
        "now": INSIDE_HOURS,
    }
    defaults.update(kwargs)
    return await preflight.check(**defaults)


# --- The happy path -----------------------------------------------------------

@pytest.mark.asyncio
async def test_a_fully_configured_send_is_allowed(ready):
    """A gate that always says no gets bypassed, so this matters as much as
    the refusals."""
    result = await run()
    assert result.allowed, result.reason
    assert result.code == "ok"
    assert result.identity["identity"] == "hello@obrinex.space"
    assert all(check["passed"] for check in result.checks)


# --- Refusals -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_kill_switch_stops_everything(ready):
    from sdr.repositories import settings as settings_repo

    await settings_repo.set_kill_switch(True, "investigating a bounce spike")
    result = await run()
    assert not result.allowed
    assert result.code == "kill_switch"
    assert "bounce spike" in result.reason


@pytest.mark.asyncio
async def test_a_disabled_module_stops_everything(db):
    result = await run()
    assert not result.allowed
    assert result.code == "module_disabled"


@pytest.mark.asyncio
async def test_a_disabled_channel_is_refused(ready):
    from sdr.repositories import settings as settings_repo

    await settings_repo.update_settings({"channels": {"email": False}})
    result = await run()
    assert not result.allowed
    assert result.code == "channel_disabled"


@pytest.mark.asyncio
async def test_a_suppressed_address_is_refused(ready):
    from sdr.repositories import suppression as suppression_repo

    await suppression_repo.suppress(value="owner@prospect.example", reason="unsubscribe")
    result = await run()
    assert not result.allowed
    assert result.code == "suppressed"
    assert "unsubscribe" in result.reason


@pytest.mark.asyncio
async def test_a_domain_suppression_covers_every_address_at_that_company(ready):
    from sdr.repositories import suppression as suppression_repo

    await suppression_repo.suppress(
        value="prospect.example", value_type="domain", reason="legal"
    )
    for address in ("owner@prospect.example", "someone.else@prospect.example"):
        result = await run(recipient_email=address)
        assert not result.allowed
        assert result.code == "suppressed"


@pytest.mark.asyncio
async def test_suppression_is_checked_before_anything_is_consumed(ready):
    """Ordering matters: a suppressed recipient must not burn an identity's
    daily allowance on the way to being refused."""
    from sdr.repositories import identities as identities_repo
    from sdr.repositories import suppression as suppression_repo

    await suppression_repo.suppress(value="owner@prospect.example", reason="complaint")
    await run()
    assert await identities_repo.usage_today("hello@obrinex.space") == 0


@pytest.mark.asyncio
async def test_an_unlisted_country_is_refused(ready):
    result = await run(country_code="ZZ")
    assert not result.allowed
    assert result.code == "compliance_blocked"
    assert "No compliance profile" in result.reason


@pytest.mark.asyncio
async def test_a_consent_gated_channel_is_refused(ready):
    from sdr.repositories import settings as settings_repo

    await settings_repo.update_settings({"channels": {"email": True, "whatsapp": True}})
    result = await run(channel="whatsapp")
    assert not result.allowed
    assert result.code == "compliance_blocked"


@pytest.mark.asyncio
async def test_an_invalid_address_is_refused(ready):
    result = await run(recipient_email="not-an-address")
    assert not result.allowed
    assert result.code == "invalid_recipient"


@pytest.mark.asyncio
async def test_outside_business_hours_defers_with_a_scheduled_time(ready):
    """A deferral, not a rejection - the message is still going to be sent."""
    result = await run(now=datetime.fromisoformat("2026-08-03T20:00:00+00:00"))
    assert not result.allowed
    assert result.code == "outside_send_window"
    assert result.scheduled_for is not None


@pytest.mark.asyncio
async def test_no_identity_available_is_refused(db):
    from sdr.repositories import settings as settings_repo

    await settings_repo.update_settings({
        "module_enabled": True, "channels": {"email": True},
    })
    result = await run()
    assert not result.allowed
    assert result.code == "no_identity"


@pytest.mark.asyncio
async def test_an_identity_with_failing_dns_cannot_send(ready, db):
    """Re-checked at send time as well as activation, because a domain can
    lose its records after being activated."""
    from sdr.collections import SENDING_IDENTITIES

    await db[SENDING_IDENTITIES].update_one({}, {"$set": {
        "dns_status": {"checks": {"spf": {"status": "fail", "detail": "no SPF record"}}},
    }})
    result = await run()
    assert not result.allowed
    assert result.code == "dns_unverified"


@pytest.mark.asyncio
async def test_a_paused_identity_is_not_selected(ready):
    from sdr.repositories import identities as identities_repo

    await identities_repo.pause(ready["id"], "manual pause")
    result = await run()
    assert not result.allowed
    assert result.code == "no_identity"


# --- Rate limiting ------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_per_domain_cap_is_enforced(ready):
    for index in range(3):
        result = await run(recipient_email=f"person{index}@prospect.example")
        assert result.allowed, result.reason

    fourth = await run(recipient_email="person4@prospect.example")
    assert not fourth.allowed
    assert fourth.code == "rate_limited"
    assert "prospect.example" in fourth.reason


@pytest.mark.asyncio
async def test_different_recipient_domains_have_independent_caps(ready):
    for index in range(3):
        await run(recipient_email=f"a{index}@first.example")
    result = await run(recipient_email="someone@second.example")
    assert result.allowed, result.reason


@pytest.mark.asyncio
async def test_the_warmup_cap_limits_a_new_identity(db):
    """Day one of warm-up sends a handful, not the target."""
    from sdr.domain import warmup
    from sdr.collections import SENDING_IDENTITIES
    from sdr.repositories import identities as identities_repo
    from sdr.repositories import settings as settings_repo

    await settings_repo.update_settings({
        "module_enabled": True, "channels": {"email": True},
        "per_domain_daily_cap": 1000,
    })
    identity = await identities_repo.create_identity(
        identity="new@obrinex.space", daily_cap_target=200, dkim_selector="resend"
    )
    await identities_repo.update_dns(identity["id"], GOOD_DNS)
    await db[SENDING_IDENTITIES].update_one({}, {"$set": {
        "status": warmup.WARMING,
        "warmup_started_at": datetime.now(timezone.utc).isoformat(),
    }})

    allowed = 0
    for index in range(30):
        result = await run(recipient_email=f"p{index}@prospect.example")
        if result.allowed:
            allowed += 1
    assert allowed == warmup.RAMP_ABSOLUTE[0]


@pytest.mark.asyncio
async def test_a_released_claim_returns_the_allowance(ready):
    """A provider outage must not silently eat an identity's daily allowance."""
    from sdr.repositories import identities as identities_repo
    from sdr.services import preflight

    await run()
    assert await identities_repo.usage_today("hello@obrinex.space") == 1

    await preflight.release_claim("hello@obrinex.space", "owner@prospect.example")
    assert await identities_repo.usage_today("hello@obrinex.space") == 0


@pytest.mark.asyncio
async def test_a_domain_capped_send_does_not_consume_identity_allowance(ready):
    """Otherwise a domain-capped recipient quietly burns the identity's day."""
    from sdr.repositories import identities as identities_repo

    for index in range(3):
        await run(recipient_email=f"p{index}@prospect.example")
    before = await identities_repo.usage_today("hello@obrinex.space")

    refused = await run(recipient_email="p4@prospect.example")
    assert not refused.allowed
    assert await identities_repo.usage_today("hello@obrinex.space") == before


# --- Identity lifecycle -------------------------------------------------------

@pytest.mark.asyncio
async def test_a_new_identity_starts_paused_and_unverified(db):
    from sdr.domain import warmup
    from sdr.repositories import identities as identities_repo

    identity = await identities_repo.create_identity(identity="fresh@obrinex.space")
    assert identity["status"] == warmup.PAUSED
    assert identity["dns_status"] is None


@pytest.mark.asyncio
async def test_activation_is_refused_without_verified_dns(db):
    from sdr.errors import ValidationError
    from sdr.repositories import identities as identities_repo

    identity = await identities_repo.create_identity(identity="fresh@obrinex.space")
    with pytest.raises(ValidationError) as exc:
        await identities_repo.activate(identity["id"])
    assert "DNS" in str(exc.value)


@pytest.mark.asyncio
async def test_activation_succeeds_once_dns_passes(db):
    from sdr.domain import warmup
    from sdr.repositories import identities as identities_repo

    identity = await identities_repo.create_identity(
        identity="fresh@obrinex.space", dkim_selector="resend"
    )
    await identities_repo.update_dns(identity["id"], GOOD_DNS)
    activated = await identities_repo.activate(identity["id"])
    assert activated["status"] == warmup.WARMING
    assert activated["warmup_started_at"]


@pytest.mark.asyncio
async def test_a_bounce_spike_throttles_the_identity_immediately(ready):
    """Within one message, not within a day."""
    from sdr.domain import warmup
    from sdr.repositories import identities as identities_repo

    updated = await identities_repo.record_outcome(
        "hello@obrinex.space", sent=100, bounced=8
    )
    assert updated["status"] == warmup.PAUSED
    assert updated["daily_cap_current"] == 0


@pytest.mark.asyncio
async def test_duplicate_identities_are_rejected(db):
    from sdr.errors import ValidationError
    from sdr.repositories import identities as identities_repo

    await identities_repo.create_identity(identity="dup@obrinex.space")
    with pytest.raises(ValidationError):
        await identities_repo.create_identity(identity="dup@obrinex.space")


# --- Suppression, unsubscribe tokens and consent ------------------------------

@pytest.mark.asyncio
async def test_suppressing_twice_is_not_an_error(db):
    """It happens on a public endpoint; a duplicate must be a no-op, not a 500."""
    from sdr.repositories import suppression as suppression_repo

    first = await suppression_repo.suppress(value="a@b.example", reason="unsubscribe")
    second = await suppression_repo.suppress(value="a@b.example", reason="unsubscribe")
    assert first["id"] == second["id"]


@pytest.mark.asyncio
async def test_suppression_matching_is_case_and_format_insensitive(db):
    from sdr.repositories import suppression as suppression_repo

    await suppression_repo.suppress(value="  Owner@Prospect.Example ")
    assert await suppression_repo.is_suppressed(email="owner@prospect.example")


@pytest.mark.asyncio
async def test_unsubscribe_tokens_cannot_suppress_a_third_party(db):
    """Without signing, editing the address in the URL would let anyone
    suppress anyone."""
    from sdr.repositories import suppression as suppression_repo

    token = suppression_repo.unsubscribe_token("victim@example.com")
    assert suppression_repo.verify_unsubscribe_token("victim@example.com", token)
    assert not suppression_repo.verify_unsubscribe_token("attacker@example.com", token)
    assert not suppression_repo.verify_unsubscribe_token("victim@example.com", "forged")


@pytest.mark.asyncio
async def test_consent_records_are_appended_for_the_audit_trail(db):
    """DPDP and GDPR require showing when and how someone opted out, not just
    that they are on a list now."""
    from sdr.repositories import suppression as suppression_repo

    await suppression_repo.record_consent(
        action="opt_out", value="a@b.example", ip="1.2.3.4",
        user_agent="Mozilla", evidence={"source": "one-click"},
    )
    history = await suppression_repo.consent_history("a@b.example")
    assert len(history) == 1
    assert history[0]["action"] == "opt_out"
    assert history[0]["ip"] == "1.2.3.4"


# --- Footers ------------------------------------------------------------------

def test_a_missing_mandatory_footer_element_is_reported():
    """Reported rather than silently omitted, so the send can be refused
    instead of going out non-compliant."""
    from sdr.services import preflight

    _, missing = preflight.required_footer(
        "US", company_name="Obrinex", postal_address=None,
        unsubscribe_url="https://x/u",
    )
    assert "postal address" in missing


def test_india_does_not_require_a_postal_address():
    from sdr.services import preflight

    _, missing = preflight.required_footer(
        "IN", company_name="Obrinex", postal_address=None,
        unsubscribe_url="https://x/u",
    )
    assert missing == []


def test_one_click_unsubscribe_headers_are_emitted():
    """Gmail and Yahoo require these for bulk senders; without them
    recipients use the spam button instead."""
    from sdr.services import preflight

    headers = preflight.unsubscribe_headers("https://x/u", mailto="unsub@obrinex.space")
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "https://x/u" in headers["List-Unsubscribe"]
    assert "mailto:" in headers["List-Unsubscribe"]

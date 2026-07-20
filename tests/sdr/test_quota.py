"""Provider quota maths and the monthly send ceiling.

The bug this prevents: treating "new leads per day" as "emails per day". With
a multi-touch sequence they differ by a factor of the touch count, and on a
metered plan that difference is the whole month's quota.
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

from sdr.domain import quota  # noqa: E402

RESEND_FREE_MONTHLY = 3000
RESEND_FREE_DAILY = 1000


# --- The maths ----------------------------------------------------------------

def test_the_resend_free_plan_is_defined_correctly():
    plan = quota.get_plan("resend_free")
    assert plan["daily_limit"] == RESEND_FREE_DAILY
    assert plan["monthly_limit"] == RESEND_FREE_MONTHLY


def test_an_unknown_plan_falls_back_without_inventing_limits():
    plan = quota.get_plan("nonexistent")
    assert plan["monthly_limit"] is None


def test_more_touches_means_fewer_new_leads_per_day():
    """The core relationship. Ignoring it is how a monthly quota disappears."""
    rates = [
        quota.sustainable_new_leads_per_day(
            monthly_limit=RESEND_FREE_MONTHLY, touches_per_lead=t
        )
        for t in (1, 2, 3, 4, 5)
    ]
    assert rates == sorted(rates, reverse=True)
    assert rates[0] > rates[-1] * 3


def test_thirty_leads_a_day_fits_the_free_plan_at_three_touches():
    """The number actually configured as the default."""
    result = quota.check_plan_fit(
        new_leads_per_day=30, monthly_limit=RESEND_FREE_MONTHLY,
        daily_limit=RESEND_FREE_DAILY, touches_per_lead=3,
    )
    assert result["fits"] is True
    assert result["projected_monthly_sends"] <= RESEND_FREE_MONTHLY


@pytest.mark.parametrize("rate", [40, 50])
def test_forty_and_fifty_leads_a_day_do_not_fit(rate):
    """Both would exhaust the month mid-sequence, stranding leads half-contacted."""
    result = quota.check_plan_fit(
        new_leads_per_day=rate, monthly_limit=RESEND_FREE_MONTHLY,
        daily_limit=RESEND_FREE_DAILY, touches_per_lead=3,
    )
    assert result["fits"] is False
    assert result["projected_monthly_sends"] > RESEND_FREE_MONTHLY
    assert result["warnings"]
    # The warning has to say what to do, not just that it is wrong.
    assert str(result["recommended_new_leads_per_day"]) in result["warnings"][0]


def test_the_warning_says_when_the_quota_runs_out():
    result = quota.check_plan_fit(
        new_leads_per_day=50, monthly_limit=RESEND_FREE_MONTHLY, touches_per_lead=3
    )
    assert "day" in result["warnings"][0]


def test_the_recommendation_actually_fits():
    """A recommendation that itself breaches the cap would be worse than none."""
    for touches in (1, 2, 3, 4, 5):
        recommended = quota.sustainable_new_leads_per_day(
            monthly_limit=RESEND_FREE_MONTHLY, touches_per_lead=touches
        )
        verdict = quota.check_plan_fit(
            new_leads_per_day=recommended, monthly_limit=RESEND_FREE_MONTHLY,
            touches_per_lead=touches,
        )
        assert verdict["fits"], f"{touches} touches: recommended {recommended} does not fit"


def test_a_single_touch_sequence_allows_far_more_leads():
    one = quota.sustainable_new_leads_per_day(monthly_limit=RESEND_FREE_MONTHLY, touches_per_lead=1)
    three = quota.sustainable_new_leads_per_day(monthly_limit=RESEND_FREE_MONTHLY, touches_per_lead=3)
    assert one == three * 3


def test_no_monthly_limit_means_no_recommendation():
    assert quota.sustainable_new_leads_per_day(monthly_limit=None) is None


def test_the_daily_provider_limit_is_also_enforced():
    """A huge monthly allowance still cannot exceed the daily ceiling."""
    result = quota.check_plan_fit(
        new_leads_per_day=1000, monthly_limit=10_000_000,
        daily_limit=100, touches_per_lead=3,
    )
    assert result["fits"] is False
    assert any("per day" in w or "/day" in w for w in result["warnings"])


def test_remaining_budget_reports_both_ceilings():
    budget = quota.remaining_budget(
        sent_this_month=2900, monthly_limit=RESEND_FREE_MONTHLY,
        sent_today=40, daily_limit=100,
    )
    assert budget["monthly_remaining"] == 100
    assert budget["daily_remaining"] == 60
    assert budget["exhausted"] == []


def test_remaining_budget_flags_exhaustion():
    budget = quota.remaining_budget(
        sent_this_month=3000, monthly_limit=RESEND_FREE_MONTHLY,
        sent_today=100, daily_limit=100,
    )
    assert "monthly" in budget["exhausted"]
    assert "daily" in budget["exhausted"]


# --- Enforcement --------------------------------------------------------------

GOOD_DNS = {
    "overall": "pass",
    "checks": {k: {"status": "pass", "detail": "ok"} for k in ("mx", "spf", "dkim", "dmarc")},
}


@pytest_asyncio.fixture
async def db(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    database = client["sdr_test"]

    import database as database_module
    monkeypatch.setattr(database_module, "db", database)

    from sdr.repositories import base, identities, settings, suppression
    from sdr.services import preflight
    for module in (base, identities, settings, suppression, preflight):
        if hasattr(module, "db"):
            monkeypatch.setattr(module, "db", database)
    return database


@pytest_asyncio.fixture
async def ready(db):
    from bson import ObjectId
    from sdr.collections import SENDING_IDENTITIES
    from sdr.domain import warmup
    from sdr.repositories import identities as identities_repo
    from sdr.repositories import settings as settings_repo

    await settings_repo.update_settings({
        "module_enabled": True,
        "channels": {"email": True},
        "daily_send_cap": 100,
        "monthly_send_cap": 5,          # tiny, so the ceiling is reachable in a test
        "per_domain_daily_cap": 100,
    })
    identity = await identities_repo.create_identity(
        identity="hello@sender.example", daily_cap_target=200, dkim_selector="resend"
    )
    await identities_repo.update_dns(identity["id"], GOOD_DNS)
    await db[SENDING_IDENTITIES].update_one(
        {"_id": ObjectId(identity["id"])},
        {"$set": {"status": warmup.HEALTHY,
                  "warmup_started_at": "2026-01-01T00:00:00+00:00"}},
    )
    return identity


async def send(index: int):
    from datetime import datetime
    from sdr.services import preflight
    return await preflight.check(
        recipient_email=f"p{index}@prospect{index}.example",
        country_code="IN",
        now=datetime.fromisoformat("2026-08-03T09:00:00+00:00"),
    )


@pytest.mark.asyncio
async def test_the_monthly_quota_is_enforced(ready):
    """Five allowed, sixth refused - the cap is real, not advisory."""
    allowed = 0
    for index in range(8):
        result = await send(index)
        if result.allowed:
            allowed += 1
        else:
            assert result.code == "monthly_cap_reached", result.reason
    assert allowed == 5


@pytest.mark.asyncio
async def test_the_monthly_refusal_explains_when_it_resets(ready):
    for index in range(5):
        await send(index)
    refused = await send(99)
    assert not refused.allowed
    assert "next month" in refused.reason.lower()


@pytest.mark.asyncio
async def test_monthly_usage_is_tracked_across_identities(ready):
    from sdr.repositories import identities as identities_repo

    for index in range(3):
        await send(index)
    assert await identities_repo.org_usage_this_month() == 3


@pytest.mark.asyncio
async def test_a_released_claim_returns_monthly_quota_too(ready):
    """A provider outage must not silently consume a month of quota."""
    from sdr.repositories import identities as identities_repo
    from sdr.services import preflight

    result = await send(1)
    assert result.allowed
    assert await identities_repo.org_usage_this_month() == 1

    await preflight.release_claim(result.identity["identity"], "p1@prospect1.example")
    assert await identities_repo.org_usage_this_month() == 0


@pytest.mark.asyncio
async def test_a_dry_run_does_not_consume_monthly_quota(ready):
    """The preflight tester in the UI must be free to use."""
    from sdr.repositories import identities as identities_repo
    from sdr.services import preflight

    result = await send(1)
    await preflight.release_claim(result.identity["identity"], "p1@prospect1.example")
    assert await identities_repo.org_usage_this_month() == 0


@pytest.mark.asyncio
async def test_the_org_daily_cap_spans_every_identity(db):
    """Per-identity warm-up caps are not the same thing as the org's daily
    budget - two healthy identities must not double it."""
    from bson import ObjectId
    from sdr.collections import SENDING_IDENTITIES
    from sdr.domain import warmup
    from sdr.repositories import identities as identities_repo
    from sdr.repositories import settings as settings_repo

    await settings_repo.update_settings({
        "module_enabled": True, "channels": {"email": True},
        "daily_send_cap": 3, "monthly_send_cap": 1000, "per_domain_daily_cap": 100,
    })
    for name in ("a@sender.example", "b@sender.example"):
        identity = await identities_repo.create_identity(
            identity=name, daily_cap_target=200, dkim_selector="resend"
        )
        await identities_repo.update_dns(identity["id"], GOOD_DNS)
        await db[SENDING_IDENTITIES].update_one(
            {"_id": ObjectId(identity["id"])},
            {"$set": {"status": warmup.HEALTHY,
                      "warmup_started_at": "2026-01-01T00:00:00+00:00"}},
        )

    allowed = 0
    for index in range(10):
        if (await send(index)).allowed:
            allowed += 1
    assert allowed == 3


@pytest.mark.asyncio
async def test_defaults_are_sized_for_the_configured_plan(db):
    from sdr.repositories import settings as settings_repo

    settings = await settings_repo.get_settings()
    assert settings["provider_plan"] == "resend_free"
    assert settings["monthly_send_cap"] == RESEND_FREE_MONTHLY

    verdict = quota.check_plan_fit(
        new_leads_per_day=settings["daily_new_leads_cap"],
        monthly_limit=settings["monthly_send_cap"],
        daily_limit=RESEND_FREE_DAILY,
        touches_per_lead=settings["touches_per_lead"],
    )
    assert verdict["fits"], (
        f"shipped defaults do not fit the plan: {verdict['warnings']}"
    )

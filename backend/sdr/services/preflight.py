"""Send pre-flight: the one gate every outbound message passes.

Ten checks, ordered cheapest-and-most-absolute first. The ordering is not
cosmetic - the kill switch and suppression must be decided before we spend
anything on picking an identity or claiming a rate-limit slot.

Every check returns a reason, and a refusal is recorded rather than silently
dropping the message. "Nothing sent and no explanation" is the failure mode
that makes an outreach system impossible to debug and impossible to trust.

The rate-limit slot is claimed **last**, because claiming consumes allowance.
A message refused after the claim would burn a send that never happened - so
everything that can refuse must refuse first.
"""

import logging

from sdr.config.countries import (
    get_compliance_profile, get_country, get_holidays, is_cold_outreach_permitted,
)
from sdr.domain import send_window
from sdr.domain.normalize import normalize_domain, normalize_email
from sdr.repositories import identities as identities_repo
from sdr.repositories import settings as settings_repo
from sdr.repositories import suppression as suppression_repo

logger = logging.getLogger(__name__)


class PreflightResult:
    def __init__(self, *, allowed: bool, reason: str, code: str,
                 identity: dict | None = None, scheduled_for=None,
                 checks: list | None = None):
        self.allowed = allowed
        self.reason = reason
        self.code = code
        self.identity = identity
        self.scheduled_for = scheduled_for
        self.checks = checks or []

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "code": self.code,
            "identity": (self.identity or {}).get("identity"),
            "scheduled_for": (
                self.scheduled_for.isoformat()
                if hasattr(self.scheduled_for, "isoformat") else self.scheduled_for
            ),
            "checks": self.checks,
        }


async def check(*, recipient_email: str, country_code: str | None,
                channel: str = "email", lead_id: str | None = None,
                timezone_name: str | None = None,
                now=None, respect_send_window: bool = True) -> PreflightResult:
    """Decide whether one message may be sent right now."""
    from datetime import datetime, timezone as tz

    now = now or datetime.now(tz.utc)
    checks = []

    def record(name, ok, detail):
        checks.append({"check": name, "passed": ok, "detail": detail})

    def refuse(code, reason):
        return PreflightResult(allowed=False, reason=reason, code=code, checks=checks)

    # 1. Kill switch and module state. Read from the database every time -
    #    Vercel invocations share no memory, so a cached switch would not
    #    actually stop anything within the 30 seconds the spec requires.
    settings = await settings_repo.get_settings()
    if settings["kill_switch"]:
        reason = f"Kill switch is on: {settings.get('kill_switch_reason') or 'no reason given'}"
        record("kill_switch", False, reason)
        return refuse("kill_switch", reason)
    record("kill_switch", True, "off")

    if not settings["module_enabled"]:
        record("module_enabled", False, "disabled")
        return refuse("module_disabled", "The AI SDR module is disabled.")
    record("module_enabled", True, "enabled")

    if not settings["channels"].get(channel, False):
        detail = f"The {channel} channel is disabled."
        record("channel_enabled", False, detail)
        return refuse("channel_disabled", detail)
    record("channel_enabled", True, f"{channel} enabled")

    # 2. A valid recipient. Cheap, and everything below assumes it.
    normalized = normalize_email(recipient_email)
    if not normalized:
        detail = f"'{recipient_email}' is not a valid email address."
        record("recipient_valid", False, detail)
        return refuse("invalid_recipient", detail)
    record("recipient_valid", True, normalized)

    recipient_domain = normalized.split("@")[-1]

    # 3. Suppression. Absolute and permanent - checked before anything that
    #    costs money or consumes allowance.
    hit = await suppression_repo.is_suppressed(email=normalized)
    if hit:
        detail = f"{hit['value_type']} suppressed ({hit['reason']})"
        record("suppression", False, detail)
        return refuse("suppressed", f"Recipient is on the suppression list: {detail}.")
    record("suppression", True, "not suppressed")

    # 4. Jurisdiction. Consulted for the *recipient's* country, and an
    #    unlisted country is refused by design rather than defaulting to
    #    whatever is most permissive.
    permitted, compliance_reason = is_cold_outreach_permitted(country_code, channel)
    if not permitted:
        record("compliance", False, compliance_reason)
        return refuse("compliance_blocked", compliance_reason)
    record("compliance", True, compliance_reason)

    profile = get_compliance_profile(country_code)
    country = get_country(country_code)

    # 5. Send window in the recipient's local time. A 03:00 arrival reads as
    #    spam to the reader and to the filter.
    scheduled_for = now
    if respect_send_window:
        holidays = get_holidays(country_code, now.year)
        within, window_detail = send_window.is_business_hours(
            now, country, timezone_name=timezone_name, holidays=holidays
        )
        if not within:
            scheduled_for = send_window.schedule(
                now, country, seed=lead_id or normalized,
                timezone_name=timezone_name, holidays=holidays,
            )
            record("send_window", False, window_detail)
            return PreflightResult(
                allowed=False,
                reason=f"Outside the recipient's business hours ({window_detail}).",
                code="outside_send_window",
                scheduled_for=scheduled_for,
                checks=checks,
            )
        record("send_window", True, window_detail)

    # 6. A healthy identity with allowance left.
    identity = await identities_repo.pick_identity(channel)
    if not identity:
        detail = (
            "No sending identity is available - all are paused, unverified, "
            "or have hit today's cap."
        )
        record("identity", False, detail)
        return refuse("no_identity", detail)
    record("identity", True, f"{identity['identity']} ({identity['status']})")

    # 7. DNS. Re-checked here as well as at activation, because a domain can
    #    lose its records after being activated and nothing else would notice.
    from sdr.services import dns_check
    dns_ok, dns_reason = dns_check.ready_to_send(identity.get("dns_status"))
    if not dns_ok:
        record("dns", False, dns_reason)
        return refuse("dns_unverified", f"{identity['identity']}: {dns_reason}")
    record("dns", True, "SPF, DKIM and DMARC verified")

    # 8. Org-wide daily volume, across every identity - independent of the
    #    per-identity warm-up caps.
    org_cap = settings.get("daily_send_cap") or 0
    if org_cap:
        used = await identities_repo.org_usage_today()
        if used >= org_cap:
            detail = f"Org daily cap of {org_cap} reached."
            record("org_cap", False, detail)
            return refuse("org_cap_reached", detail)
        record("org_cap", True, f"{used}/{org_cap} today")

    # 9. The provider's monthly quota. On a free tier this is the limit that
    #    actually binds - the daily one is rarely reached. Exhausting it
    #    mid-month strands sequences half-sent, which reads to the prospect
    #    as a bot that broke, so it is enforced rather than warned about.
    monthly_cap = settings.get("monthly_send_cap") or 0
    if monthly_cap:
        used_month = await identities_repo.org_usage_this_month()
        if used_month >= monthly_cap:
            detail = (
                f"Monthly quota of {monthly_cap:,} reached ({used_month:,} sent). "
                "Resets at the start of next month."
            )
            record("monthly_cap", False, detail)
            return refuse("monthly_cap_reached", detail)
        record("monthly_cap", True, f"{used_month:,}/{monthly_cap:,} this month")

    # 10. Rate limits. Claimed last, because claiming consumes allowance and
    #     anything that could still refuse has now refused.
    domain_cap = settings.get("per_domain_daily_cap") or 3
    claimed, claim_reason = await identities_repo.claim_send_slot(
        identity=identity["identity"],
        recipient_domain=recipient_domain,
        identity_cap=identity["daily_cap_current"],
        domain_cap=domain_cap,
    )
    if not claimed:
        record("rate_limit", False, claim_reason)
        return refuse("rate_limited", claim_reason)

    # The monthly counter is claimed alongside, and rolled back with the
    # others if this send never actually goes out.
    monthly_claimed, monthly_reason = await identities_repo.claim_monthly_slot(monthly_cap)
    if not monthly_claimed:
        # Hand back the daily slots just claimed, or a send refused on the
        # monthly quota would still burn the identity's day.
        await release_claim(identity["identity"], recipient_email, monthly=False)
        record("monthly_quota", False, monthly_reason)
        return refuse("monthly_cap_reached", monthly_reason)

    record("rate_limit", True, "slot claimed")

    return PreflightResult(
        allowed=True,
        reason="All pre-flight checks passed",
        code="ok",
        identity=identity,
        scheduled_for=scheduled_for,
        checks=checks,
    )


async def release_claim(identity: str, recipient_email: str,
                        *, monthly: bool = True) -> None:
    """Give back claimed slots when the send did not happen.

    Called when the provider rejects a message after pre-flight passed.
    Without this, a provider outage silently eats an identity's daily
    allowance - and, worse on a metered plan, a month of quota - while
    warm-up stalls for reasons nobody can see.

    `monthly=False` is used internally when the monthly claim itself was the
    thing that failed, so there is nothing to hand back on that counter.
    """
    from datetime import datetime, timedelta, timezone as tz

    domain = (normalize_email(recipient_email) or "@").split("@")[-1]
    expires = datetime.now(tz.utc) + timedelta(days=identities_repo.COUNTER_RETENTION_DAYS)
    day = datetime.now(tz.utc).strftime("%Y-%m-%d")
    await identities_repo._increment("identity", identity, day, expires, delta=-1)
    await identities_repo._increment("recipient_domain", domain, day, expires, delta=-1)
    if monthly:
        await identities_repo.release_monthly_slot()


def required_footer(country_code: str | None, *, company_name: str,
                    postal_address: str | None, unsubscribe_url: str) -> tuple:
    """Build the legally required footer, and say what is missing.

    Returns (footer_html, missing). A missing mandatory element is returned
    rather than silently omitted, so the send can be refused instead of
    going out non-compliant.
    """
    profile = get_compliance_profile(country_code)
    missing = []

    parts = []
    if profile["footer_requires_identity"]:
        if company_name:
            parts.append(company_name)
        else:
            missing.append("sender identity")

    if profile["footer_requires_postal_address"]:
        if postal_address:
            parts.append(postal_address)
        else:
            missing.append("postal address")

    if profile["footer_requires_unsubscribe"]:
        if unsubscribe_url:
            parts.append(
                f'<a href="{unsubscribe_url}">Unsubscribe</a> - '
                f"we will stop immediately and permanently."
            )
        else:
            missing.append("unsubscribe link")

    footer = (
        '<hr style="border:none;border-top:1px solid #ddd;margin:24px 0 12px">'
        '<p style="font-size:12px;color:#666">' + "<br>".join(parts) + "</p>"
    )
    return footer, missing


def unsubscribe_headers(unsubscribe_url: str, mailto: str | None = None) -> dict:
    """List-Unsubscribe headers, including one-click.

    Gmail and Yahoo require one-click unsubscribe for bulk senders. Without
    these, recipients use the spam button instead, which is far more damaging
    than an unsubscribe.
    """
    targets = [f"<{unsubscribe_url}>"]
    if mailto:
        targets.insert(0, f"<mailto:{mailto}?subject=unsubscribe>")
    return {
        "List-Unsubscribe": ", ".join(targets),
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }

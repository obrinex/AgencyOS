"""SDR settings singleton - feature flags, caps, and the kill switch.

Stored as one document keyed {"key": "main"}, matching how the host app
already stores `company_settings` (seed.py:28-33). The repo has no feature
flag mechanism, so this is it.

The kill switch is the important part: the spec requires halting all outbound
sending within 30 seconds. Because Vercel is stateless, an in-memory flag
would not propagate across invocations - so it is a database read, checked by
the send pre-flight on every single message rather than cached.
"""

from database import db, now_iso, serialize_doc
from sdr.collections import SETTINGS

SETTINGS_KEY = "main"

#: Deliberately conservative defaults. A fresh install requires human approval
#: before any send and has every outbound channel disabled - a misconfigured
#: deployment should do nothing, not email strangers.
DEFAULTS = {
    "key": SETTINGS_KEY,
    "module_enabled": False,
    # Master stop. When true, the send pre-flight refuses everything
    # regardless of any other setting.
    "kill_switch": False,
    "kill_switch_reason": None,
    "kill_switch_at": None,
    "channels": {
        "email": False, "whatsapp": False, "sms": False,
        "linkedin": False, "voice": False,
    },
    # New installs require a human to approve a campaign's first send.
    "require_approval_before_first_send": True,

    # "simulate" runs the entire outreach pipeline - personalization,
    # approval, pre-flight, scheduling - but stops short of the provider
    # call: messages are marked sent with `simulated: true` and no email
    # leaves the building. The default, so a fresh deployment can exercise
    # and demo everything with zero risk. Going live is an explicit,
    # admin-only, audited flip to "live".
    "send_mode": "simulate",

    # --- Volume, sized to the email provider's plan ---------------------------
    #
    # Three separate limits, because they constrain different things and
    # conflating them is how a monthly quota gets exhausted mid-sequence:
    #
    #   daily_new_leads_cap  how many NEW leads a sequence may start per day
    #   daily_send_cap       total emails/day, including follow-ups
    #   monthly_send_cap     the provider's hard monthly ceiling
    #
    # Defaults are sized for Resend's free tier (1,000/day, 3,000/month). At
    # 3 touches per lead, 30 new leads/day settles at ~2,700 emails/month -
    # inside the cap with headroom. 40/day would exhaust it around day 25 and
    # 50/day around day 20, stranding sequences half-sent, which reads to the
    # prospect as a bot that broke. See sdr/domain/quota.py.
    "provider_plan": "resend_free",
    "daily_new_leads_cap": 30,
    "daily_send_cap": 100,
    "monthly_send_cap": 3000,
    "touches_per_lead": 3,

    "per_domain_daily_cap": 3,
    "max_touches_per_lead": 5,
    "cooldown_days_between_campaigns": 30,
    "daily_llm_spend_cap_usd": 5.0,
    "default_country_code": None,

    # Allow leads in countries with no shipped compliance profile.
    #
    # Off by default: an unlisted country is one whose cold-outreach law this
    # system does not model, and blocking is the safer failure. Turning it on
    # is an explicit statement that you have checked the law yourself.
    #
    # It does NOT unblock countries that are listed and restricted - Canada
    # (CASL) and Germany (UWG) require prior consent for email, and a blanket
    # override that silently ignored that would be worse than no switch.
    "allow_unlisted_countries": False,

    # Where replies should land. Deliberately None by default rather than a
    # guessed `replies@<domain>`: a Reply-To pointing at a mailbox that does
    # not exist bounces the prospect's answer, which is worse than having no
    # Reply-To at all (replies then go to the From identity, as they do
    # today). Set this only once the address is real and monitored.
    "reply_to_address": None,

    # --- Inbound replies ------------------------------------------------------
    #
    # "imap" polls a real mailbox and leaves it untouched; "webhook" expects
    # Cloudflare Email Routing to POST. Off by default: an install with no
    # inbound configured should do nothing rather than fail every tick.
    "inbound_mode": "off",              # off | imap | webhook
    "inbound_imap_last_uid": 0,
    "inbound_imap_uidvalidity": None,
    "inbound_imap_mailbox": "INBOX",
    "inbound_last_polled_at": None,
    "inbound_last_error": None,
    "open_tracking_enabled": False,   # off by default: hurts deliverability and privacy
    "click_tracking_enabled": False,
    "brand_voice": "",
    "do_not_say": [],
}


async def get_settings() -> dict:
    """Read the singleton, seeding defaults on first access."""
    doc = await db[SETTINGS].find_one({"key": SETTINGS_KEY})
    if not doc:
        seed = dict(DEFAULTS)
        seed.update({"created_at": now_iso(), "updated_at": now_iso()})
        await db[SETTINGS].insert_one(seed)
        doc = await db[SETTINGS].find_one({"key": SETTINGS_KEY})
    result = serialize_doc(doc)
    # Merge forward: a setting added in a later release is absent from
    # documents written by an earlier one. Mongo has no migrations here, so
    # defaults fill the gap rather than the caller getting a KeyError.
    for key, value in DEFAULTS.items():
        result.setdefault(key, value)
    return result


async def update_settings(patch: dict) -> dict:
    """Partial update. Only known keys are accepted."""
    allowed = {k: v for k, v in patch.items() if k in DEFAULTS and k != "key"}
    if allowed:
        allowed["updated_at"] = now_iso()
        await db[SETTINGS].update_one(
            {"key": SETTINGS_KEY}, {"$set": allowed}, upsert=True
        )
    return await get_settings()


async def set_kill_switch(enabled: bool, reason: str | None = None) -> dict:
    await db[SETTINGS].update_one(
        {"key": SETTINGS_KEY},
        {"$set": {
            "kill_switch": bool(enabled),
            "kill_switch_reason": reason,
            "kill_switch_at": now_iso() if enabled else None,
            "updated_at": now_iso(),
        }},
        upsert=True,
    )
    return await get_settings()


async def sending_allowed(channel: str) -> tuple:
    """Whether the module may send on this channel right now.

    Called by the send pre-flight before every message. Returns
    (allowed, reason) so a refusal can be logged with a cause rather than
    disappearing silently.
    """
    settings = await get_settings()
    if settings["kill_switch"]:
        return False, f"Kill switch is on: {settings.get('kill_switch_reason') or 'no reason given'}"
    if not settings["module_enabled"]:
        return False, "The AI SDR module is disabled"
    if not settings["channels"].get(channel, False):
        return False, f"The {channel} channel is disabled"
    return True, "Allowed"

"""Country registry, compliance profiles, and the India-first/global-ready rule.

The last test in this file is the enforcement mechanism for spec section 19:
market specifics must live in `sdr/config/`, never in business logic. It runs
the grep the spec asks for at the end of every phase, so a regression fails
CI instead of relying on someone remembering.
"""

import re
from pathlib import Path

import pytest

from sdr.config import countries as c

BACKEND = Path(__file__).resolve().parents[2] / "backend"


def test_india_is_configured_as_the_primary_market():
    india = c.get_country("IN")
    assert india["currency"] == "INR"
    assert india["timezones"] == ["Asia/Kolkata"]
    assert india["phone_code"] == "+91"
    assert india["industry_classification"] == "nic"
    assert india["compliance_profile"] == "DPDP"


def test_whatsapp_outranks_email_in_the_india_channel_order():
    """WhatsApp materially outperforms email in this market, so the sequence
    engine must not assume an email-first ordering."""
    channels = c.get_country("IN")["preferred_channels"]
    assert channels.index("whatsapp") < channels.index("email")


def test_unknown_country_falls_back_to_the_conservative_default():
    assert c.get_country("ZZ") is c.DEFAULT_COUNTRY
    assert c.get_country(None) is c.DEFAULT_COUNTRY
    assert c.get_country("") is c.DEFAULT_COUNTRY


def test_country_lookup_is_case_insensitive():
    assert c.get_country("in")["code"] == "IN"


def test_every_country_references_a_profile_that_exists():
    for code in c.supported_country_codes():
        profile_key = c.get_country(code)["compliance_profile"]
        assert profile_key in c.COMPLIANCE_PROFILES, code


def test_every_country_has_the_full_required_shape():
    required = set(c.DEFAULT_COUNTRY.keys())
    for code in c.supported_country_codes():
        missing = required - set(c.get_country(code).keys())
        assert not missing, f"{code} is missing {missing}"


# --- Compliance ---------------------------------------------------------------

def test_unlisted_country_blocks_cold_outreach():
    """We would rather block a legitimate send than make an unlawful one."""
    permitted, reason = c.is_cold_outreach_permitted("ZZ", "email")
    assert permitted is False
    assert "No compliance profile" in reason


def test_india_permits_b2b_cold_email_but_not_cold_whatsapp():
    assert c.is_cold_outreach_permitted("IN", "email")[0] is True
    assert c.is_cold_outreach_permitted("IN", "whatsapp")[0] is False


def test_consent_gated_channels_are_blocked_everywhere_by_default():
    for code in c.supported_country_codes():
        for channel in ("sms", "voice", "whatsapp"):
            permitted, _ = c.is_cold_outreach_permitted(code, channel)
            assert permitted is False, f"{code}/{channel} should require consent"


def test_an_unknown_channel_is_treated_as_consent_required():
    """Defaulting an unrecognised channel to 'allowed' would be the dangerous
    direction to fail in."""
    assert c.is_cold_outreach_permitted("IN", "carrier_pigeon")[0] is False


def test_every_profile_declares_an_opt_out_sla():
    for key, profile in c.COMPLIANCE_PROFILES.items():
        assert profile["opt_out_sla_hours"] > 0, key
        assert profile["footer_requires_unsubscribe"] is True, key


def test_holidays_resolve_and_fall_back():
    assert "01-26" in c.get_holidays("IN", 2026)   # Republic Day
    assert c.get_holidays("ZZ", 2026)              # DEFAULT list, not empty


# --- Spec section 19 enforcement ----------------------------------------------

FORBIDDEN = {
    "India": re.compile(r"\bIndia\b"),
    "INR": re.compile(r"\bINR\b"),
    "IST": re.compile(r"\bIST\b"),
    "+91": re.compile(r"\+91\b"),
}

#: Market specifics are allowed here and nowhere else.
ALLOWED_DIRS = {"config"}


def _business_logic_files():
    for path in (BACKEND / "sdr").rglob("*.py"):
        relative = path.relative_to(BACKEND / "sdr")
        if relative.parts and relative.parts[0] in ALLOWED_DIRS:
            continue
        yield path


@pytest.mark.parametrize("label", sorted(FORBIDDEN))
def test_no_market_literals_outside_the_config_registry(label):
    """Spec section 19: nothing in domain/ or application/ may reference
    'India', 'INR', 'IST' or '+91' literally. Any hit is a bug.

    The grep the spec asks for at the end of every phase, run automatically.
    """
    pattern = FORBIDDEN[label]
    offenders = []
    for path in _business_logic_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(BACKEND)}:{number}: {line.strip()}")
    assert not offenders, (
        f"'{label}' must live in sdr/config/, not business logic:\n"
        + "\n".join(offenders)
    )

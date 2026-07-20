"""Country registry - the only place market specifics are allowed to appear.

India is the first entry because it is the primary market, not because it is
special-cased: it is one row in the same table as every other country, and
DEFAULT exists so an unlisted country degrades to the conservative profile
rather than to an error or to India's rules.

Adding a market means appending a COUNTRIES entry and a holiday list. No code
elsewhere changes.
"""

# --- Compliance profiles ------------------------------------------------------
#
# Consulted for the *recipient's* country, never the sender's. Each profile
# declares what cold outreach is permitted at all, what the message must
# contain, and how fast an opt-out must be honoured.

COMPLIANCE_PROFILES = {
    # India - Digital Personal Data Protection Act 2023. Business-to-business
    # contact is permitted; SMS additionally requires TRAI/DLT template
    # registration, which is modelled separately as a template registration.
    "DPDP": {
        "key": "DPDP",
        "label": "India - DPDP Act 2023",
        "b2b_cold_outreach_permitted": True,
        "lawful_bases": ["legitimate_use", "consent"],
        "consent_required_by_channel": {
            "email": False, "whatsapp": True, "sms": True, "voice": True, "linkedin": False,
        },
        "footer_requires_identity": True,
        "footer_requires_postal_address": False,
        "footer_requires_unsubscribe": True,
        "opt_out_sla_hours": 72,
        "data_retention_days": 1095,
        "notes": "SMS requires DLT template registration with the regulator before send.",
    },
    # EU / UK - GDPR + PECR. The strictest of the shipped profiles.
    "GDPR": {
        "key": "GDPR",
        "label": "EU/UK - GDPR & PECR",
        "b2b_cold_outreach_permitted": True,
        "lawful_bases": ["legitimate_interest", "consent"],
        "consent_required_by_channel": {
            "email": False, "whatsapp": True, "sms": True, "voice": True, "linkedin": False,
        },
        "footer_requires_identity": True,
        "footer_requires_postal_address": True,
        "footer_requires_unsubscribe": True,
        "opt_out_sla_hours": 24,
        "data_retention_days": 730,
        "notes": "Legitimate interest requires a documented balancing test per campaign. "
                 "Corporate subscribers only - sole traders and partnerships count as individuals under PECR.",
    },
    # US - CAN-SPAM for email, TCPA for phone and SMS.
    "CAN_SPAM": {
        "key": "CAN_SPAM",
        "label": "US - CAN-SPAM & TCPA",
        "b2b_cold_outreach_permitted": True,
        "lawful_bases": ["legitimate_interest"],
        "consent_required_by_channel": {
            "email": False, "whatsapp": True, "sms": True, "voice": True, "linkedin": False,
        },
        "footer_requires_identity": True,
        "footer_requires_postal_address": True,
        "footer_requires_unsubscribe": True,
        "opt_out_sla_hours": 240,  # CAN-SPAM allows 10 business days; we honour instantly anyway
        "data_retention_days": 1095,
        "notes": "TCPA governs SMS and voice separately and requires prior express consent. "
                 "State laws (e.g. Florida, Oklahoma) are stricter than federal.",
    },
    # Everything unlisted. Deliberately conservative: assume consent is needed.
    "DEFAULT": {
        "key": "DEFAULT",
        "label": "Unlisted country - conservative default",
        "b2b_cold_outreach_permitted": False,
        "lawful_bases": ["consent"],
        "consent_required_by_channel": {
            "email": True, "whatsapp": True, "sms": True, "voice": True, "linkedin": True,
        },
        "footer_requires_identity": True,
        "footer_requires_postal_address": True,
        "footer_requires_unsubscribe": True,
        "opt_out_sla_hours": 24,
        "data_retention_days": 365,
        "notes": "No profile shipped for this country. Cold outreach is blocked until one is added.",
    },
}


# --- Public holidays ----------------------------------------------------------
#
# Send windows skip these. Stored as MM-DD for fixed-date holidays; movable
# feasts (Diwali, Eid, Easter) shift annually and are listed per-year.

HOLIDAYS = {
    "IN": {
        "fixed": ["01-26", "05-01", "08-15", "10-02", "12-25"],
        "by_year": {
            2026: ["03-04", "03-21", "04-01", "05-01", "08-28", "10-20", "11-08"],
        },
        "note": "National holidays only. Major state holidays vary and are not modelled.",
    },
    "US": {
        "fixed": ["01-01", "06-19", "07-04", "11-11", "12-25"],
        "by_year": {2026: ["01-19", "02-16", "05-25", "09-07", "11-26"]},
    },
    "GB": {
        "fixed": ["01-01", "12-25", "12-26"],
        "by_year": {2026: ["04-03", "04-06", "05-04", "05-25", "08-31"]},
    },
    "DEFAULT": {"fixed": ["01-01", "12-25"], "by_year": {}},
}


# --- Country registry ---------------------------------------------------------

COUNTRIES = {
    "IN": {
        "code": "IN",
        "name": "India",
        "currency": "INR",
        "currency_display": "lakh_crore",   # 12,34,567 grouping, not 1,234,567
        "locales": ["en-IN", "hi-IN"],
        "languages": ["en", "hi", "mr", "ta", "te", "bn", "gu", "kn", "ml", "pa"],
        "timezones": ["Asia/Kolkata"],
        "phone_code": "+91",
        "phone_nsn_length": 10,
        "business_hours": {"start": "10:00", "end": "19:00", "days": [0, 1, 2, 3, 4, 5]},
        "industry_classification": "nic",
        "registration_id_label": "CIN / GSTIN",
        "compliance_profile": "DPDP",
        # WhatsApp materially outperforms email in this market, so the
        # sequence engine must not assume an email-first ordering.
        "preferred_channels": ["whatsapp", "email", "sms", "voice"],
        "preferred_data_providers": ["osm_overpass", "google_places", "justdial", "indiamart", "mca_registry"],
    },
    "US": {
        "code": "US",
        "name": "United States",
        "currency": "USD",
        "currency_display": "western",
        "locales": ["en-US"],
        "languages": ["en", "es"],
        "timezones": ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"],
        "phone_code": "+1",
        "phone_nsn_length": 10,
        "business_hours": {"start": "09:00", "end": "17:00", "days": [0, 1, 2, 3, 4]},
        "industry_classification": "naics",
        "registration_id_label": "EIN",
        "compliance_profile": "CAN_SPAM",
        "preferred_channels": ["email", "linkedin", "voice"],
        "preferred_data_providers": ["google_places", "apollo", "clearbit", "osm_overpass"],
    },
    "GB": {
        "code": "GB",
        "name": "United Kingdom",
        "currency": "GBP",
        "currency_display": "western",
        "locales": ["en-GB"],
        "languages": ["en"],
        "timezones": ["Europe/London"],
        "phone_code": "+44",
        "phone_nsn_length": 10,
        "business_hours": {"start": "09:00", "end": "17:30", "days": [0, 1, 2, 3, 4]},
        "industry_classification": "sic",
        "registration_id_label": "Company number",
        "compliance_profile": "GDPR",
        "preferred_channels": ["email", "linkedin"],
        "preferred_data_providers": ["google_places", "apollo", "osm_overpass"],
    },
    "AE": {
        "code": "AE",
        "name": "United Arab Emirates",
        "currency": "AED",
        "currency_display": "western",
        "locales": ["en-AE", "ar-AE"],
        "languages": ["en", "ar"],
        "timezones": ["Asia/Dubai"],
        "phone_code": "+971",
        "phone_nsn_length": 9,
        # The working week runs Monday-Friday, with Friday a half day.
        "business_hours": {"start": "09:00", "end": "18:00", "days": [0, 1, 2, 3, 4]},
        "industry_classification": "provider",
        "registration_id_label": "Trade licence number",
        "compliance_profile": "DEFAULT",
        "preferred_channels": ["whatsapp", "email"],
        "preferred_data_providers": ["google_places", "osm_overpass"],
    },
}

#: Used whenever a country code is unknown or absent. Conservative by design.
DEFAULT_COUNTRY = {
    "code": "DEFAULT",
    "name": "Unlisted",
    "currency": "USD",
    "currency_display": "western",
    "locales": ["en"],
    "languages": ["en"],
    "timezones": ["UTC"],
    "phone_code": None,
    "phone_nsn_length": None,
    "business_hours": {"start": "09:00", "end": "17:00", "days": [0, 1, 2, 3, 4]},
    "industry_classification": "provider",
    "registration_id_label": "Registration number",
    "compliance_profile": "DEFAULT",
    "preferred_channels": ["email"],
    "preferred_data_providers": ["osm_overpass"],
}


def get_country(country_code: str | None) -> dict:
    """Resolve a country profile, falling back to the conservative default."""
    if not country_code:
        return DEFAULT_COUNTRY
    return COUNTRIES.get(country_code.upper(), DEFAULT_COUNTRY)


def get_compliance_profile(country_code: str | None) -> dict:
    """Compliance rules for a recipient in this country."""
    country = get_country(country_code)
    return COMPLIANCE_PROFILES.get(
        country["compliance_profile"], COMPLIANCE_PROFILES["DEFAULT"]
    )


def get_holidays(country_code: str | None, year: int) -> list:
    """Public holidays as MM-DD strings for the given year."""
    key = (country_code or "").upper()
    entry = HOLIDAYS.get(key, HOLIDAYS["DEFAULT"])
    return list(entry.get("fixed", [])) + list(entry.get("by_year", {}).get(year, []))


def is_cold_outreach_permitted(country_code: str | None, channel: str) -> tuple:
    """Whether cold outreach may be sent. Returns (permitted, reason).

    The send pre-flight calls this before anything else. An unlisted country
    returns False, which is the point of the DEFAULT profile - we would rather
    block a legitimate send than make an unlawful one.
    """
    profile = get_compliance_profile(country_code)
    if not profile["b2b_cold_outreach_permitted"]:
        return False, (
            f"No compliance profile is configured for country '{country_code or 'unknown'}'. "
            "Cold outreach is blocked until one is added."
        )
    if profile["consent_required_by_channel"].get(channel, True):
        return False, (
            f"{profile['label']} requires prior consent for the {channel} channel."
        )
    return True, f"Permitted under {profile['label']}"


def supported_country_codes() -> list:
    return sorted(COUNTRIES.keys())

"""Industry benchmarks behind every ROI estimate.

Each figure carries a source note and the whole table carries a version, both
of which are stored on every generated estimate. When a benchmark changes,
old estimates keep the version they were computed under - a proposal sent
last month must still be defensible on the numbers it actually showed.

These are honest industry-typical figures, not measured values for any
specific prospect. `roi.estimate_opportunity` returns them inside
`assumptions` so the UI can show exactly what a number rests on.

Deal values are stored in the industry's base currency and converted per
country via REGION_MULTIPLIER - purchasing power differs enough that a single
global figure would be wrong everywhere.
"""

BENCHMARK_VERSION = "2026.07"

BENCHMARK_SOURCE = (
    "Industry-typical ranges compiled from public small-business marketing "
    "benchmarks. Directional estimates for prioritisation and proposal "
    "framing - not measured values for any individual prospect."
)

#: Baseline share of enquiries a business with no detected gaps converts into
#: a contactable lead. Gaps reduce nothing directly; they define how much of
#: the remaining miss is recoverable (see roi._combined_uplift).
_GLOBAL = {
    "baseline_capture_rate": 0.35,
    # Even a perfect setup never captures everything - people browse and leave.
    "max_capture_rate": 0.85,
    "leads_per_review": 0.8,
    "leads_per_employee": 4.0,
    "monthly_leads_min": 5.0,
    "monthly_leads_max": 800.0,
}

#: Per-industry overrides. `avg_deal_value` is in `base_currency`.
INDUSTRIES = {
    "restaurant": {
        "base_currency": "USD", "avg_deal_value": 45, "close_rate": 0.55,
        "monthly_leads_baseline": 120, "leads_per_review": 1.6,
    },
    "cafe": {
        "base_currency": "USD", "avg_deal_value": 18, "close_rate": 0.60,
        "monthly_leads_baseline": 140, "leads_per_review": 1.8,
    },
    "dental": {
        "base_currency": "USD", "avg_deal_value": 900, "close_rate": 0.35,
        "monthly_leads_baseline": 45, "leads_per_review": 0.7,
    },
    "medical": {
        "base_currency": "USD", "avg_deal_value": 450, "close_rate": 0.40,
        "monthly_leads_baseline": 60, "leads_per_review": 0.8,
    },
    "salon": {
        "base_currency": "USD", "avg_deal_value": 70, "close_rate": 0.50,
        "monthly_leads_baseline": 90, "leads_per_review": 1.2,
    },
    "gym": {
        "base_currency": "USD", "avg_deal_value": 480, "close_rate": 0.25,
        "monthly_leads_baseline": 55, "leads_per_review": 0.9,
    },
    "hotel": {
        "base_currency": "USD", "avg_deal_value": 280, "close_rate": 0.30,
        "monthly_leads_baseline": 110, "leads_per_review": 1.1,
    },
    "real_estate": {
        "base_currency": "USD", "avg_deal_value": 4500, "close_rate": 0.12,
        "monthly_leads_baseline": 40, "leads_per_review": 0.5,
    },
    "legal": {
        "base_currency": "USD", "avg_deal_value": 2200, "close_rate": 0.20,
        "monthly_leads_baseline": 30, "leads_per_review": 0.4,
    },
    "accounting": {
        "base_currency": "USD", "avg_deal_value": 1400, "close_rate": 0.28,
        "monthly_leads_baseline": 28, "leads_per_review": 0.4,
    },
    "veterinary": {
        "base_currency": "USD", "avg_deal_value": 180, "close_rate": 0.45,
        "monthly_leads_baseline": 65, "leads_per_review": 0.9,
    },
    "car_repair": {
        "base_currency": "USD", "avg_deal_value": 320, "close_rate": 0.42,
        "monthly_leads_baseline": 70, "leads_per_review": 1.0,
    },
    "pharmacy": {
        "base_currency": "USD", "avg_deal_value": 35, "close_rate": 0.65,
        "monthly_leads_baseline": 150, "leads_per_review": 1.5,
    },
}

#: Fallback for an industry with no entry. Mid-range and deliberately modest,
#: so an unrecognised industry never produces an inflated headline number.
DEFAULT_INDUSTRY = {
    "base_currency": "USD", "avg_deal_value": 400, "close_rate": 0.30,
    "monthly_leads_baseline": 50, "leads_per_review": 0.8,
}

#: Purchasing-power adjustment applied to `avg_deal_value`, keyed by country.
#: Rough and openly so - it is surfaced in the assumptions.
REGION_MULTIPLIER = {"IN": 0.35, "US": 1.0, "GB": 0.95, "AE": 0.85, "DEFAULT": 0.7}


def resolve(industry: str | None, country_code: str | None) -> dict:
    """Build the benchmark set for one company.

    Returns a flat dict ready to hand to `roi.estimate_opportunity`, including
    the currency the figures are denominated in - the ROI module never assumes
    a currency of its own.
    """
    from sdr.config.countries import get_country

    industry_key = (industry or "").strip().lower()
    industry_row = INDUSTRIES.get(industry_key, DEFAULT_INDUSTRY)
    country = get_country(country_code)
    multiplier = REGION_MULTIPLIER.get(
        country["code"], REGION_MULTIPLIER["DEFAULT"]
    )

    resolved = dict(_GLOBAL)
    resolved.update(industry_row)
    resolved.update({
        # Deal values are quoted in the prospect's own currency so a proposal
        # never shows a figure the reader has to convert in their head.
        "currency": country["currency"],
        "avg_deal_value": round(industry_row["avg_deal_value"] * multiplier, 2),
        "version": BENCHMARK_VERSION,
        "source": BENCHMARK_SOURCE,
        "industry_matched": industry_key if industry_key in INDUSTRIES else None,
        "region_multiplier": multiplier,
    })
    return resolved

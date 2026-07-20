"""ROI model and the opportunity signal registry.

These numbers end up in proposals and outreach copy shown to real
prospects, so the properties that matter are: no invented figures, no
unbounded claims, and every estimate carrying its assumptions.
"""

import pytest

from sdr.config import benchmarks
from sdr.domain import roi, signals

FULL_FACTS = {
    "has_chat_widget": False, "has_crm_pixel": False, "has_booking_system": False,
    "lighthouse_performance": 30, "mobile_friendly": False, "ssl_valid": True,
    "contact_form_present": True, "contact_form_working": True,
    "google_review_count": 120, "review_response_rate": 0.05,
    "employee_count": 10, "has_analytics": True,
}


# --- Signals ------------------------------------------------------------------

def test_signal_keys_are_unique():
    keys = [s.key for s in signals.SIGNALS]
    assert len(keys) == len(set(keys))


def test_all_signals_have_valid_severity_and_bounded_uplift():
    for s in signals.SIGNALS:
        assert s.severity in signals.SEVERITY_RANK, s.key
        assert 0.0 <= s.capture_uplift <= 1.0, s.key
        assert s.evidence_keys, f"{s.key} cites no evidence"


def test_detects_the_gaps_that_are_present():
    found = {s["signal_key"] for s in signals.detect(FULL_FACTS)}
    assert "no_chatbot" in found
    assert "manual_appointment_booking" in found
    assert "not_mobile_friendly" in found
    assert "poor_website_performance" in found


def test_does_not_claim_gaps_that_are_absent():
    found = {s["signal_key"] for s in signals.detect(FULL_FACTS)}
    assert "no_ssl" not in found          # ssl_valid is True
    assert "no_analytics" not in found    # has_analytics is True
    assert "broken_contact_form" not in found


def test_unknown_facts_produce_no_signal():
    """A failed crawl must not become 'this prospect has no chatbot'.

    That claim would end up in an outreach email, so silence beats a guess.
    """
    assert signals.detect({}) == []


def test_missing_form_reports_weak_capture_not_broken_form():
    found = {s["signal_key"] for s in signals.detect({"contact_form_present": False})}
    assert "weak_lead_capture" in found
    assert "broken_contact_form" not in found


def test_broken_form_is_detected_when_present_but_not_working():
    found = {s["signal_key"] for s in signals.detect(
        {"contact_form_present": True, "contact_form_working": False}
    )}
    assert "broken_contact_form" in found


def test_results_are_ordered_most_severe_first():
    found = signals.detect(FULL_FACTS)
    ranks = [signals.SEVERITY_RANK[s["severity"]] for s in found]
    assert ranks == sorted(ranks, reverse=True)


def test_every_signal_carries_traceable_evidence():
    for row in signals.detect(FULL_FACTS):
        assert row["evidence"], f"{row['signal_key']} carries no evidence"


def test_a_detector_that_raises_does_not_abort_the_audit():
    hostile = {"lighthouse_performance": object(), "has_chat_widget": False}
    found = {s["signal_key"] for s in signals.detect(hostile)}
    assert "no_chatbot" in found


def test_confidence_reflects_evidence_coverage():
    row = {"signal_key": "no_chatbot", "evidence": {"has_chat_widget": False, "chat_vendor": None}}
    assert 0.0 < signals.confidence(row) <= 1.0
    assert signals.confidence({"signal_key": "unknown_key", "evidence": {}}) == 0.0


# --- Benchmarks ---------------------------------------------------------------

def test_benchmarks_resolve_currency_from_the_country():
    assert benchmarks.resolve("dental", "IN")["currency"] == "INR"
    assert benchmarks.resolve("dental", "US")["currency"] == "USD"


def test_unknown_industry_falls_back_without_inflating():
    fallback = benchmarks.resolve("underwater-basket-weaving", "US")
    assert fallback["industry_matched"] is None
    assert fallback["avg_deal_value"] > 0


def test_benchmarks_always_carry_version_and_source():
    resolved = benchmarks.resolve("dental", "IN")
    assert resolved["version"] == benchmarks.BENCHMARK_VERSION
    assert resolved["source"]


def test_region_multiplier_is_applied():
    india = benchmarks.resolve("dental", "IN")["avg_deal_value"]
    us = benchmarks.resolve("dental", "US")["avg_deal_value"]
    assert india < us


# --- ROI ----------------------------------------------------------------------

def test_uplift_never_exceeds_one_however_many_gaps():
    """Naive summing would claim a >100% capture rate from eight gaps."""
    assert roi._combined_uplift([0.5] * 20) < 1.0
    assert roi._combined_uplift([0.9, 0.9, 0.9]) < 1.0
    assert roi._combined_uplift([]) == 0.0


def test_combined_uplift_is_less_than_the_naive_sum():
    uplifts = [0.2, 0.2, 0.2]
    assert roi._combined_uplift(uplifts) < sum(uplifts)


def test_capture_rate_never_exceeds_the_benchmark_ceiling():
    marks = benchmarks.resolve("dental", "IN")
    detected = signals.detect(FULL_FACTS)
    result = roi.estimate_opportunity(marks, FULL_FACTS, detected)
    assert result["improved_capture_rate"] <= marks["max_capture_rate"]
    assert result["improved_capture_rate"] > result["current_capture_rate"]


def test_no_signals_means_no_claimed_opportunity():
    marks = benchmarks.resolve("dental", "IN")
    result = roi.estimate_opportunity(marks, FULL_FACTS, [])
    assert result["monthly_opportunity_value"] == 0.0


def test_estimate_is_labelled_and_carries_its_assumptions():
    """The UI marks these as estimates; the data has to support that."""
    marks = benchmarks.resolve("dental", "IN")
    result = roi.estimate_opportunity(marks, FULL_FACTS, signals.detect(FULL_FACTS))
    assert result["is_estimate"] is True
    assumptions = result["assumptions"]
    assert assumptions["benchmark_version"]
    assert assumptions["benchmark_source"]
    assert assumptions["signals_counted"]
    assert assumptions["monthly_leads"]["basis"]


def test_lead_estimate_is_clamped_to_a_defensible_band():
    """One outlier review count must not produce an absurd headline number."""
    marks = benchmarks.resolve("dental", "IN")
    value, assumptions = roi.estimate_monthly_leads(marks, {"google_review_count": 999999})
    assert value <= marks["monthly_leads_max"]
    assert assumptions["was_clamped"] is True


def test_lead_estimate_falls_back_when_no_traffic_signal_exists():
    marks = benchmarks.resolve("dental", "IN")
    value, assumptions = roi.estimate_monthly_leads(marks, {})
    assert value > 0
    assert "baseline" in assumptions["basis"]


def test_annual_value_is_twelve_times_monthly():
    marks = benchmarks.resolve("dental", "IN")
    result = roi.estimate_opportunity(marks, FULL_FACTS, signals.detect(FULL_FACTS))
    assert result["annual_opportunity_value"] == pytest.approx(
        result["monthly_opportunity_value"] * 12, rel=1e-3
    )


def test_per_signal_values_do_not_sum_to_the_combined_total():
    """This is intended, not a bug - the combined model applies diminishing
    returns. The note on the payload exists so nobody 'fixes' it later."""
    marks = benchmarks.resolve("dental", "IN")
    detected = signals.detect(FULL_FACTS)
    combined = roi.estimate_opportunity(marks, FULL_FACTS, detected)
    parts = [roi.estimate_signal_value(marks, FULL_FACTS, s) for s in detected]
    assert sum(p["monthly_opportunity_value"] for p in parts) > combined["monthly_opportunity_value"]
    assert all(p["note"] for p in parts)

"""Lead scoring - determinism, bounds, explainability."""

import pytest

from sdr.domain import scoring

COMPANY = {
    "name": "Acme Dental", "domain": "acmedental.in", "industry": "dental",
    "city": "Pune", "country_code": "IN", "employee_count": 12,
    "phone_e164": "+912012345678", "description": "Family dental clinic",
}

ICP = {
    "filters": {
        "industry": {"categories": ["dental", "medical"]},
        "size": {"employeeMin": 5, "employeeMax": 50},
        "geo": {"countryCodes": ["IN"]},
    }
}


def test_weights_sum_to_one():
    assert sum(scoring.DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)


def test_score_is_bounded_and_deterministic():
    first = scoring.score_lead({}, COMPANY, icp=ICP)
    second = scoring.score_lead({}, COMPANY, icp=ICP)
    assert first == second, "Scoring must be deterministic"
    assert 0 <= first["score"] <= 100


def test_empty_company_scores_low_but_valid():
    result = scoring.score_lead({}, {})
    assert 0 <= result["score"] <= 100


def test_breakdown_covers_every_component_and_sums_to_the_score():
    result = scoring.score_lead({}, COMPANY, icp=ICP)
    assert set(result["score_breakdown"]) == set(scoring.DEFAULT_WEIGHTS)
    total = sum(c["points"] for c in result["score_breakdown"].values())
    assert result["score"] == pytest.approx(total, abs=1)


def test_every_component_explains_itself():
    """An unexplained score is one a rep cannot argue with, which makes it useless."""
    result = scoring.score_lead({}, COMPANY, icp=ICP)
    for name, component in result["score_breakdown"].items():
        assert component["reasons"], f"{name} produced no reasons"


def test_score_carries_its_version():
    result = scoring.score_lead({}, COMPANY, icp=ICP)
    assert result["score_version"] == scoring.SCORING_VERSION


# --- Components ---------------------------------------------------------------

def test_missing_icp_scores_neutral_not_zero():
    """An unconfigured ICP must not make the whole pipeline look worthless."""
    raw, reasons = scoring.score_icp_fit(COMPANY, None)
    assert raw == 0.5
    assert reasons


def test_icp_fit_rewards_a_match_and_punishes_a_miss():
    match, _ = scoring.score_icp_fit(COMPANY, ICP)
    miss, _ = scoring.score_icp_fit({**COMPANY, "industry": "legal", "country_code": "US"}, ICP)
    assert match > miss
    assert match == pytest.approx(1.0)


def test_icp_fit_scores_unknown_headcount_neutral():
    raw, _ = scoring.score_icp_fit({**COMPANY, "employee_count": None}, ICP)
    assert 0.0 < raw < 1.0


def test_reachability_is_harsh_without_contacts():
    """An unreachable lead is worthless regardless of how good the fit is."""
    raw, _ = scoring.score_reachability({}, [])
    assert raw == 0.0


def test_reachability_rewards_a_verified_decision_maker():
    contacts = [{"is_decision_maker": True, "email_status": "valid", "phone_e164": "+911111111111"}]
    raw, _ = scoring.score_reachability(COMPANY, contacts)
    assert raw == pytest.approx(1.0)


def test_unverified_email_scores_below_verified():
    verified, _ = scoring.score_reachability({}, [{"email": "a@b.com", "email_status": "valid"}])
    unverified, _ = scoring.score_reachability({}, [{"email": "a@b.com", "email_status": "unknown"}])
    assert verified > unverified


def test_opportunity_scales_with_severity_not_count():
    one_critical = scoring.score_opportunity([{"signal_key": "no_ssl", "severity": "critical"}])[0]
    three_low = scoring.score_opportunity([
        {"signal_key": "a", "severity": "low"},
        {"signal_key": "b", "severity": "low"},
        {"signal_key": "c", "severity": "low"},
    ])[0]
    assert one_critical > three_low


def test_opportunity_is_capped_at_one():
    many = [{"signal_key": f"s{i}", "severity": "critical"} for i in range(50)]
    raw, _ = scoring.score_opportunity(many)
    assert raw <= 1.0


def test_inbound_source_shows_more_intent_than_cold_discovery():
    inbound, _ = scoring.score_intent({"source": "web_form"})
    cold, _ = scoring.score_intent({"source": "ai_finder"})
    assert inbound > cold


def test_reply_and_meeting_raise_intent():
    raw, _ = scoring.score_intent({"replied_at": "2026-07-01T00:00:00+00:00",
                                   "meeting_booked_at": "2026-07-02T00:00:00+00:00"})
    assert raw == pytest.approx(1.0)


# --- Qualification ------------------------------------------------------------

def test_hard_fail_disqualifies_at_any_score():
    status, reason = scoring.qualification_status(99, hard_fails=["suppressed_domain"])
    assert status == "disqualified"
    assert "suppressed_domain" in reason


def test_qualification_thresholds():
    assert scoring.qualification_status(scoring.QUALIFICATION_THRESHOLD)[0] == "qualified"
    assert scoring.qualification_status(scoring.QUALIFICATION_THRESHOLD - 5)[0] == "needs_review"
    assert scoring.qualification_status(10)[0] == "unqualified"


def test_borderline_goes_to_review_rather_than_being_guessed():
    """A wrong auto-qualify costs a real send to a real person."""
    status, _ = scoring.qualification_status(scoring.QUALIFICATION_THRESHOLD - 1)
    assert status == "needs_review"

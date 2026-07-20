"""Lead scoring - deterministic, explainable, versioned.

Two hard requirements shape this module:

1. **Explainable.** Every score returns the contribution of each component,
   so a rep can see why a lead scored 78 and disagree with a specific line
   rather than the number. The UI renders this breakdown directly.
2. **Versioned.** `SCORING_VERSION` is stored on every scored lead. When
   weights change, historical scores keep their original version and are not
   silently recomputed - otherwise week-on-week conversion analysis compares
   numbers produced by different models.

Scores are 0-100. The existing `leads.score` field is an int, so the final
value is rounded to match what CRMPipeline.jsx already renders.

Pure module: no I/O.
"""

from sdr.domain import signals as signals_module

SCORING_VERSION = "1.0.0"

#: Component weights. Must sum to 1.0 - asserted at import so a bad edit
#: fails immediately rather than producing quietly wrong scores.
DEFAULT_WEIGHTS = {
    "icp_fit": 0.30,          # does it match the ICP the campaign targets
    "opportunity": 0.30,      # how much detectable value is on the table
    "reachability": 0.20,     # can we actually contact a decision maker
    "intent": 0.10,           # observed engagement signals
    "data_quality": 0.10,     # how much we actually know about them
}

assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9, "Scoring weights must sum to 1.0"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def score_icp_fit(company: dict, icp: dict | None) -> tuple:
    """How well the company matches the ICP definition. Returns (0-1, reasons).

    With no ICP supplied every lead scores neutral rather than zero - an
    unconfigured ICP should not make the whole pipeline look worthless.
    """
    if not icp:
        return 0.5, ["No ICP profile applied - scored neutral"]

    checks, reasons = [], []
    filters = icp.get("filters") or {}

    industries = (filters.get("industry") or {}).get("categories") or []
    if industries:
        match = company.get("industry") in industries
        checks.append(1.0 if match else 0.0)
        reasons.append(
            f"Industry '{company.get('industry') or 'unknown'}' "
            f"{'matches' if match else 'is outside'} the ICP"
        )

    size = filters.get("size") or {}
    employees = company.get("employee_count")
    if (size.get("employeeMin") is not None or size.get("employeeMax") is not None):
        if employees is None:
            checks.append(0.5)
            reasons.append("Headcount unknown - scored neutral")
        else:
            low = size.get("employeeMin", 0) or 0
            high = size.get("employeeMax")
            within = employees >= low and (high is None or employees <= high)
            checks.append(1.0 if within else 0.0)
            reasons.append(
                f"Headcount {employees} {'is within' if within else 'is outside'} "
                f"the target band"
            )

    geo = filters.get("geo") or {}
    countries = geo.get("countryCodes") or []
    if countries:
        match = company.get("country_code") in countries
        checks.append(1.0 if match else 0.0)
        reasons.append(
            f"Country '{company.get('country_code') or 'unknown'}' "
            f"{'matches' if match else 'is outside'} the ICP"
        )

    if not checks:
        return 0.5, ["ICP profile defines no scorable filters - scored neutral"]
    return sum(checks) / len(checks), reasons


def score_opportunity(detected_signals: list) -> tuple:
    """Value on the table, from detected gaps. Returns (0-1, reasons).

    Weighted by severity rather than raw count: one broken contact form
    matters more than four cosmetic gaps.
    """
    if not detected_signals:
        return 0.0, ["No opportunity signals detected yet"]

    total = sum(
        signals_module.SEVERITY_RANK.get(s.get("severity"), 0)
        for s in detected_signals
    )
    # Four critical signals is a strong ceiling; beyond that the lead is not
    # meaningfully better, it is just a worse website.
    normalised = _clamp01(total / (signals_module.SEVERITY_RANK[signals_module.CRITICAL] * 4))
    top = [s["signal_key"] for s in detected_signals[:3]]
    return normalised, [f"{len(detected_signals)} gaps detected, led by {', '.join(top)}"]


def score_reachability(company: dict, contacts: list) -> tuple:
    """Can we contact a decision maker. Returns (0-1, reasons).

    An unreachable lead is worthless regardless of fit, so this is deliberately
    harsh: no verified contact route caps the component near zero.
    """
    reasons, points = [], 0.0

    decision_makers = [c for c in contacts if c.get("is_decision_maker")]
    valid_emails = [c for c in contacts if c.get("email_status") == "valid"]

    if decision_makers:
        points += 0.4
        reasons.append(f"{len(decision_makers)} decision maker(s) identified")
    elif contacts:
        points += 0.15
        reasons.append("Contacts found, but no confirmed decision maker")
    else:
        reasons.append("No contacts found")

    if valid_emails:
        points += 0.4
        reasons.append(f"{len(valid_emails)} verified email address(es)")
    elif any(c.get("email") for c in contacts) or company.get("primary_email"):
        points += 0.15
        reasons.append("Email present but unverified")
    else:
        reasons.append("No email address")

    if company.get("phone_e164") or any(c.get("phone_e164") for c in contacts):
        points += 0.2
        reasons.append("Phone number available")

    return _clamp01(points), reasons


def score_intent(lead: dict) -> tuple:
    """Observed engagement. Returns (0-1, reasons).

    Phase 1 has no outreach yet, so this reads whatever engagement fields
    exist and scores zero when there are none. It becomes meaningful in
    Phase 5 once messages are actually sent.
    """
    reasons, points = [], 0.0
    if lead.get("replied_at"):
        points += 0.6
        reasons.append("Replied to outreach")
    if lead.get("meeting_booked_at"):
        points += 0.4
        reasons.append("Booked a meeting")
    if not reasons:
        # An inbound lead that arrived on its own has shown more intent than
        # one we discovered cold, even before any outreach.
        if lead.get("source") in ("web_form", "inbound", "referral"):
            points += 0.3
            reasons.append(f"Inbound via {lead.get('source')}")
        else:
            reasons.append("No engagement recorded yet")
    return _clamp01(points), reasons


def score_data_quality(company: dict) -> tuple:
    """How much we actually know. Returns (0-1, reasons).

    Low data quality suppresses the score because personalised outreach needs
    facts to cite - a lead we know nothing about cannot be written to well.
    """
    fields = [
        "name", "domain", "industry", "city", "country_code",
        "employee_count", "phone_e164", "description",
    ]
    present = [f for f in fields if company.get(f)]
    ratio = len(present) / len(fields)
    return ratio, [f"{len(present)} of {len(fields)} core fields populated"]


def score_lead(
    lead: dict,
    company: dict,
    contacts: list | None = None,
    detected_signals: list | None = None,
    icp: dict | None = None,
    weights: dict | None = None,
) -> dict:
    """Compute a 0-100 score with a full explainable breakdown."""
    contacts = contacts or []
    detected_signals = detected_signals or []
    weights = weights or DEFAULT_WEIGHTS

    components = {
        "icp_fit": score_icp_fit(company, icp),
        "opportunity": score_opportunity(detected_signals),
        "reachability": score_reachability(company, contacts),
        "intent": score_intent(lead),
        "data_quality": score_data_quality(company),
    }

    breakdown, total = {}, 0.0
    for key, (raw, reasons) in components.items():
        weight = weights.get(key, 0.0)
        contribution = _clamp01(raw) * weight * 100
        total += contribution
        breakdown[key] = {
            "raw": round(_clamp01(raw), 3),
            "weight": weight,
            "points": round(contribution, 1),
            "reasons": reasons,
        }

    return {
        "score": int(round(total)),
        "score_version": SCORING_VERSION,
        "score_breakdown": breakdown,
    }


#: Score at or above which a lead is worth working, absent a hard
#: disqualification. Deliberately a constant rather than a magic number
#: scattered through the qualification agent.
QUALIFICATION_THRESHOLD = 55


def qualification_status(score: int, hard_fails: list | None = None) -> tuple:
    """Map a score plus hard rules to a qualification decision.

    Hard fails always win - a lead in a suppressed country is disqualified at
    any score. Everything between the threshold and a hard fail lands in
    `needs_review` rather than being guessed at, because a wrong auto-qualify
    costs a real send to a real person.
    """
    if hard_fails:
        return "disqualified", f"Failed hard rule(s): {', '.join(hard_fails)}"
    if score >= QUALIFICATION_THRESHOLD:
        return "qualified", f"Score {score} meets the {QUALIFICATION_THRESHOLD} threshold"
    if score >= QUALIFICATION_THRESHOLD - 15:
        return "needs_review", f"Score {score} is borderline - a human should decide"
    return "unqualified", f"Score {score} is below the {QUALIFICATION_THRESHOLD} threshold"

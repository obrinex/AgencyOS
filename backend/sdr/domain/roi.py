"""ROI estimation.

Every number this module produces is an *estimate*, and it returns its
assumptions alongside the figure so the claim can always be defended. The UI
marks these visually as estimates and exposes the assumptions on click; the
proposal and outreach copy must never present them as guaranteed.

The formula, per spec section 6.2:

    monthly_leads_estimate    <- industry benchmark, adjusted for observed
                                 review volume and headcount
    current_capture_rate      <- benchmark baseline minus detected gaps
    improved_capture_rate     <- current + uplift per signal (with diminishing
                                 returns, see _combined_uplift)
    monthly_opportunity_value = (improved - current)
                                * monthly_leads * avg_deal_value * close_rate

All benchmarks come from `sdr/config/benchmarks.py`, which carries a source
note and a version for each figure. No number is invented here.

Pure module: no I/O, and no currency/country literals - the caller supplies
a resolved benchmark set.
"""


def _combined_uplift(uplifts: list) -> float:
    """Combine per-signal uplifts with diminishing returns.

    Naively summing them is the obvious mistake: eight gaps at 15% each would
    claim a 120% capture-rate improvement. Instead we treat each uplift as
    recovering a fraction of what is still being missed, which composes
    multiplicatively and can never exceed 1.0.
    """
    remaining = 1.0
    for uplift in uplifts:
        bounded = max(0.0, min(float(uplift), 1.0))
        remaining *= (1.0 - bounded)
    return 1.0 - remaining


def estimate_monthly_leads(benchmarks: dict, facts: dict) -> tuple:
    """Estimate monthly inbound enquiries. Returns (value, assumptions).

    Review volume is the strongest observable proxy for foot/enquiry traffic
    in local business, so it leads. Headcount is the fallback. When neither
    is available we fall back to the industry's baseline, and say so.
    """
    baseline = float(benchmarks["monthly_leads_baseline"])
    reviews = facts.get("google_review_count")
    employees = facts.get("employee_count")

    if reviews is not None:
        try:
            # Reviews accumulate over years; the benchmark converts a total
            # review count into an implied monthly enquiry rate.
            value = float(reviews) * float(benchmarks["leads_per_review"])
            basis = f"{int(float(reviews))} Google reviews x {benchmarks['leads_per_review']} enquiries per review"
        except (TypeError, ValueError):
            value, basis = baseline, "industry baseline (review count unreadable)"
    elif employees is not None:
        try:
            value = float(employees) * float(benchmarks["leads_per_employee"])
            basis = f"{int(float(employees))} employees x {benchmarks['leads_per_employee']} enquiries per employee"
        except (TypeError, ValueError):
            value, basis = baseline, "industry baseline (employee count unreadable)"
    else:
        value, basis = baseline, "industry baseline (no traffic signal available)"

    # Clamp to the benchmark's plausible band so one outlier review count
    # cannot produce an indefensible headline number in a proposal.
    low = float(benchmarks["monthly_leads_min"])
    high = float(benchmarks["monthly_leads_max"])
    clamped = max(low, min(value, high))
    assumptions = {
        "basis": basis,
        "raw_estimate": round(value, 1),
        "clamped_to": [low, high],
        "was_clamped": clamped != round(value, 6) and abs(clamped - value) > 1e-6,
    }
    return round(clamped, 1), assumptions


def estimate_opportunity(benchmarks: dict, facts: dict, signals: list) -> dict:
    """The full ROI model for one company.

    `signals` is the output of domain.signals.detect(). `benchmarks` is a
    resolved dict for this company's industry and region, including its
    currency code - this module never assumes one.
    """
    monthly_leads, lead_assumptions = estimate_monthly_leads(benchmarks, facts)

    current_capture = float(benchmarks["baseline_capture_rate"])
    uplift = _combined_uplift([s.get("capture_uplift", 0.0) for s in signals])

    # The uplift recovers a share of what is currently missed, so it can
    # approach but never reach a 100% capture rate.
    improved_capture = current_capture + (1.0 - current_capture) * uplift
    improved_capture = min(improved_capture, float(benchmarks["max_capture_rate"]))

    avg_deal_value = float(benchmarks["avg_deal_value"])
    close_rate = float(benchmarks["close_rate"])

    recovered_leads = monthly_leads * (improved_capture - current_capture)
    monthly_value = recovered_leads * avg_deal_value * close_rate

    return {
        "currency": benchmarks["currency"],
        "monthly_leads_estimate": monthly_leads,
        "current_capture_rate": round(current_capture, 4),
        "improved_capture_rate": round(improved_capture, 4),
        "recovered_leads_per_month": round(recovered_leads, 1),
        "monthly_opportunity_value": round(monthly_value, 2),
        "annual_opportunity_value": round(monthly_value * 12, 2),
        "is_estimate": True,
        "assumptions": {
            "monthly_leads": lead_assumptions,
            "baseline_capture_rate": current_capture,
            "combined_uplift": round(uplift, 4),
            "uplift_method": "diminishing returns - each gap recovers a share of the remaining miss, never summed",
            "avg_deal_value": avg_deal_value,
            "close_rate": close_rate,
            "signals_counted": [s["signal_key"] for s in signals],
            "benchmark_version": benchmarks.get("version"),
            "benchmark_source": benchmarks.get("source"),
        },
    }


def estimate_signal_value(benchmarks: dict, facts: dict, signal: dict) -> dict:
    """Attribute a monthly value to one signal in isolation.

    Used when a proposal itemises gaps. Note that the per-signal figures will
    not sum to the combined total - that is correct, not a bug, because the
    combined model applies diminishing returns. The returned dict says so
    explicitly so nobody 'fixes' it later.
    """
    single = estimate_opportunity(benchmarks, facts, [signal])
    single["note"] = (
        "Isolated estimate. Per-signal values intentionally do not sum to the "
        "combined figure, which applies diminishing returns across gaps."
    )
    return single

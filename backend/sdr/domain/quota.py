"""Provider quota maths: turning a plan's limits into a safe lead rate.

The mistake this module exists to prevent: treating "new leads approached per
day" as if it were "emails sent per day". It is not. A sequence with three
touches sends roughly three emails per lead, so approaching 50 new leads a day
settles at ~150 emails a day once follow-ups accumulate - and a 3,000/month
plan is exhausted in twenty days, mid-sequence, leaving leads half-contacted.

Half-finished sequences are worse than never starting: the prospect gets an
opener and a follow-up, then silence, which reads as a bot that broke.

So the sustainable figure is derived from the *monthly* budget divided by
touches per lead, not from the daily send limit. On most free tiers the daily
limit is not the binding constraint at all.

Pure module: no I/O.
"""

#: Known provider plans. Daily and monthly ceilings are the provider's hard
#: limits - exceeding them means rejected sends, not just throttling.
PROVIDER_PLANS = {
    "resend_free": {
        "label": "Resend (free)",
        "daily_limit": 1000,
        "monthly_limit": 3000,
        "note": "The monthly limit binds first: 3,000/month is ~100/day averaged.",
    },
    "resend_pro": {
        "label": "Resend (Pro)",
        "daily_limit": 5000,
        "monthly_limit": 50_000,
        "note": None,
    },
    "custom": {
        "label": "Custom",
        "daily_limit": None,
        "monthly_limit": None,
        "note": "Set the caps manually.",
    },
}

DEFAULT_PLAN = "resend_free"

#: Emails per lead across a full sequence. Used to convert a monthly email
#: budget into a sustainable new-lead rate.
DEFAULT_TOUCHES_PER_LEAD = 3

#: Days per month for averaging. 30 rather than 30.44 - erring low leaves
#: headroom rather than overshooting the plan.
DAYS_PER_MONTH = 30

#: Fraction of the monthly quota to actually plan against, leaving room for
#: retries, replies, and the fact that months are not all 30 days.
SAFETY_MARGIN = 0.9


def get_plan(plan_key: str | None) -> dict:
    return PROVIDER_PLANS.get(plan_key or DEFAULT_PLAN, PROVIDER_PLANS["custom"])


def sustainable_new_leads_per_day(*, monthly_limit: int | None,
                                  touches_per_lead: int = DEFAULT_TOUCHES_PER_LEAD,
                                  safety_margin: float = SAFETY_MARGIN) -> int | None:
    """How many *new* leads can be started per day without exhausting the month.

    Returns None when there is no monthly limit to plan against.
    """
    if not monthly_limit:
        return None
    touches = max(1, int(touches_per_lead))
    usable = monthly_limit * max(0.1, min(safety_margin, 1.0))
    return max(1, int(usable / DAYS_PER_MONTH / touches))


def sustainable_sends_per_day(*, monthly_limit: int | None,
                              daily_limit: int | None,
                              safety_margin: float = SAFETY_MARGIN) -> int | None:
    """Total emails per day the monthly budget supports, capped by the daily limit."""
    candidates = []
    if monthly_limit:
        candidates.append(int(monthly_limit * safety_margin / DAYS_PER_MONTH))
    if daily_limit:
        candidates.append(int(daily_limit))
    return min(candidates) if candidates else None


def projected_monthly_sends(*, new_leads_per_day: int,
                            touches_per_lead: int = DEFAULT_TOUCHES_PER_LEAD) -> int:
    """Steady-state monthly email volume for a given new-lead rate."""
    return int(max(0, new_leads_per_day) * max(1, touches_per_lead) * DAYS_PER_MONTH)


def check_plan_fit(*, new_leads_per_day: int, monthly_limit: int | None,
                   daily_limit: int | None = None,
                   touches_per_lead: int = DEFAULT_TOUCHES_PER_LEAD) -> dict:
    """Whether a desired lead rate fits the plan. Returns an explained verdict.

    Surfaced in the UI so the number an operator types is checked against
    reality before a campaign starts, rather than discovered when sends begin
    failing three weeks in.
    """
    projected = projected_monthly_sends(
        new_leads_per_day=new_leads_per_day, touches_per_lead=touches_per_lead
    )
    recommended = sustainable_new_leads_per_day(
        monthly_limit=monthly_limit, touches_per_lead=touches_per_lead
    )
    daily_projected = new_leads_per_day * touches_per_lead

    warnings = []
    fits = True

    if monthly_limit and projected > monthly_limit:
        fits = False
        days_until_exhausted = (
            int(monthly_limit / daily_projected) if daily_projected else DAYS_PER_MONTH
        )
        warnings.append(
            f"{new_leads_per_day} new leads/day with {touches_per_lead} touches each "
            f"is about {projected:,} emails/month, over the {monthly_limit:,} limit. "
            f"The quota would run out around day {days_until_exhausted}, leaving "
            f"sequences half-finished. Recommended: {recommended} new leads/day."
        )
    elif monthly_limit and projected > monthly_limit * SAFETY_MARGIN:
        warnings.append(
            f"About {projected:,} emails/month leaves little headroom under the "
            f"{monthly_limit:,} limit. {recommended} new leads/day is safer."
        )

    if daily_limit and daily_projected > daily_limit:
        fits = False
        warnings.append(
            f"At steady state this sends about {daily_projected}/day, over the "
            f"provider's {daily_limit}/day limit."
        )

    return {
        "fits": fits,
        "new_leads_per_day": new_leads_per_day,
        "touches_per_lead": touches_per_lead,
        "projected_monthly_sends": projected,
        "projected_daily_sends": daily_projected,
        "monthly_limit": monthly_limit,
        "daily_limit": daily_limit,
        "recommended_new_leads_per_day": recommended,
        "warnings": warnings,
    }


def remaining_budget(*, sent_this_month: int, monthly_limit: int | None,
                     sent_today: int = 0, daily_limit: int | None = None) -> dict:
    """What is left to spend, and whether either ceiling is already reached."""
    monthly_remaining = (
        max(0, monthly_limit - sent_this_month) if monthly_limit else None
    )
    daily_remaining = max(0, daily_limit - sent_today) if daily_limit else None

    exhausted = []
    if monthly_limit and sent_this_month >= monthly_limit:
        exhausted.append("monthly")
    if daily_limit and sent_today >= daily_limit:
        exhausted.append("daily")

    return {
        "sent_this_month": sent_this_month,
        "sent_today": sent_today,
        "monthly_limit": monthly_limit,
        "daily_limit": daily_limit,
        "monthly_remaining": monthly_remaining,
        "daily_remaining": daily_remaining,
        "monthly_used_pct": (
            round(sent_this_month / monthly_limit, 3) if monthly_limit else None
        ),
        "exhausted": exhausted,
    }

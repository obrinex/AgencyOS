"""The Founding Circle: application questions, scoring, rounds and seats.

Pure module - no I/O, no database, no imports beyond the standard library. The
router does the persisting; everything here is a decision you can unit-test and
read in one sitting.

## Why the score is arithmetic and not a model

Sixty-five of the hundred points come from four banded answers - revenue,
tenure, team size, weekly hours - and are computed the same way every time. The
remaining thirty-five are yours, entered while reading four free-text answers.

A language model could rate the whole thing, and it would be worse: two similar
applicants would score differently on different days, you could not explain a
rejection to someone who asked, and tuning it would mean fiddling with a prompt
rather than a number. The bands below are visible, arguable and adjustable. If
`REVENUE_POINTS` is wrong, it is wrong in a way you can see and change.

The score does not decide anything. It orders a list; every seat is your call.

## The two caps are different things

`ROUND_APPLICATION_CAP` (100) limits how many applications a monthly round
accepts before it closes itself - a workload ceiling, so that reviewing a round
stays a finite job. `TOTAL_SEATS` (10) limits how many people are ever in the
circle. A round can fill with 100 applicants and produce zero members.
"""

from datetime import datetime, timezone

#: Seats in the circle, ever. The eleventh approval is refused, not queued.
TOTAL_SEATS = 10

#: Applications one monthly round accepts before closing itself.
ROUND_APPLICATION_CAP = 100

# --- Status ------------------------------------------------------------------

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
STATUSES = (PENDING, APPROVED, REJECTED)

#: A round is open, or it is not. Closing happens on the cap or the month end,
#: whichever arrives first.
ROUND_OPEN = "open"
ROUND_CLOSED = "closed"

CLOSED_BY_CAP = "cap_reached"
CLOSED_BY_MONTH = "month_ended"


# --- The application form -----------------------------------------------------
#
# Six banded questions carry the automatic score; four free-text ones carry the
# judgement. Bands rather than free numbers on purpose: "12,00,000/yr" and
# "1.2M ARR" and "about a lakh a month" are the same answer written three ways,
# and a number typed by an applicant is a number nobody verified anyway.

REVENUE_POINTS = {
    "pre_revenue": 0,
    "under_1l": 10,
    "1l_to_5l": 20,
    "5l_to_20l": 27,
    "over_20l": 30,
}

TENURE_POINTS = {
    "under_6m": 3,
    "6m_to_18m": 8,
    "18m_to_3y": 13,
    "over_3y": 15,
}

TEAM_POINTS = {
    "solo": 4,
    "2_to_5": 8,
    "6_to_20": 10,
    "over_20": 10,
}

#: Commitment is scored on stated hours. Deliberately flat at the top: someone
#: promising 10+ hours a week is not twice as good a member as someone
#: promising 5, and rewarding the biggest promise selects for over-promising.
COMMITMENT_POINTS = {
    "under_2": 0,
    "2_to_5": 7,
    "5_to_10": 10,
    "over_10": 10,
}

#: The qualitative block you fill in while reading. Kept to four axes because a
#: rubric nobody completes is a rubric that does not exist.
QUALITATIVE_MAX = {
    "clarity": 10,      # Q6: is the bottleneck a real, specific problem?
    "self_awareness": 10,  # Q7: did they try anything before asking?
    "work_quality": 10,    # Q8: the linked work
    "fit": 5,              # Q9: can this circle actually give them that?
}

AUTOMATIC_MAX = (max(REVENUE_POINTS.values()) + max(TENURE_POINTS.values())
                 + max(TEAM_POINTS.values()) + max(COMMITMENT_POINTS.values()))
TOTAL_MAX = AUTOMATIC_MAX + sum(QUALITATIVE_MAX.values())

QUESTIONS = [
    {"key": "company", "type": "text", "required": True,
     "label": "Company or product name"},
    {"key": "website", "type": "url", "required": False,
     "label": "Website or portfolio link"},
    {"key": "one_liner", "type": "text", "required": True, "max_length": 200,
     "label": "What do you do, in one sentence?"},
    {"key": "revenue_band", "type": "band", "required": True,
     "label": "Current monthly revenue",
     "options": list(REVENUE_POINTS)},
    {"key": "tenure_band", "type": "band", "required": True,
     "label": "How long have you been operating?",
     "options": list(TENURE_POINTS)},
    {"key": "team_band", "type": "band", "required": True,
     "label": "Team size",
     "options": list(TEAM_POINTS)},
    {"key": "bottleneck", "type": "textarea", "required": True, "max_length": 1500,
     "label": "What is the single biggest bottleneck in your business right now?"},
    {"key": "already_tried", "type": "textarea", "required": True, "max_length": 1500,
     "label": "What have you already tried to solve it?"},
    {"key": "best_work", "type": "url", "required": False,
     "label": "Link to your best piece of work"},
    {"key": "first_90_days", "type": "textarea", "required": True, "max_length": 1500,
     "label": "What would you want from the Founding Circle in your first 90 days?"},
    {"key": "commitment_band", "type": "band", "required": True,
     "label": "Hours per week you can genuinely commit",
     "options": list(COMMITMENT_POINTS)},
]

#: Human labels for the bands, for the form and the review screen. Kept beside
#: the points so a new band cannot be added to one and forgotten in the other.
BAND_LABELS = {
    "revenue_band": {
        "pre_revenue": "Pre-revenue", "under_1l": "Under ₹1L/month",
        "1l_to_5l": "₹1L–5L/month", "5l_to_20l": "₹5L–20L/month",
        "over_20l": "₹20L+/month",
    },
    "tenure_band": {
        "under_6m": "Under 6 months", "6m_to_18m": "6–18 months",
        "18m_to_3y": "18 months–3 years", "over_3y": "3+ years",
    },
    "team_band": {
        "solo": "Just me", "2_to_5": "2–5 people",
        "6_to_20": "6–20 people", "over_20": "20+ people",
    },
    "commitment_band": {
        "under_2": "Under 2 hours", "2_to_5": "2–5 hours",
        "5_to_10": "5–10 hours", "over_10": "10+ hours",
    },
}

REQUIRED_KEYS = tuple(q["key"] for q in QUESTIONS if q["required"])
BAND_KEYS = tuple(q["key"] for q in QUESTIONS if q["type"] == "band")


def validate_answers(answers: dict) -> list:
    """Problems with a submitted application. Empty list means it is fine.

    Returns every problem rather than the first, so an applicant fixes their
    form once instead of discovering faults one reload at a time.
    """
    problems = []
    for question in QUESTIONS:
        key, value = question["key"], (answers or {}).get(question["key"])
        text = value.strip() if isinstance(value, str) else value

        if question["required"] and not text:
            problems.append(f"{question['label']} is required.")
            continue
        if not text:
            continue
        if question["type"] == "band" and text not in question["options"]:
            problems.append(f"{question['label']}: '{text}' is not one of the options.")
        limit = question.get("max_length")
        if limit and isinstance(text, str) and len(text) > limit:
            problems.append(f"{question['label']} is limited to {limit} characters.")
    return problems


# --- Scoring ------------------------------------------------------------------

def automatic_score(answers: dict) -> dict:
    """The 65 points that need no human. Unknown bands score zero, never crash.

    An unrecognised band means the form and this module disagree, which is a
    bug - but it is not a reason to lose an application, so it scores nothing
    and shows up as a zero somebody can ask about.
    """
    answers = answers or {}
    parts = {
        "revenue": REVENUE_POINTS.get(answers.get("revenue_band"), 0),
        "tenure": TENURE_POINTS.get(answers.get("tenure_band"), 0),
        "team": TEAM_POINTS.get(answers.get("team_band"), 0),
        "commitment": COMMITMENT_POINTS.get(answers.get("commitment_band"), 0),
    }
    return {"parts": parts, "total": sum(parts.values()), "max": AUTOMATIC_MAX}


def qualitative_score(ratings: dict) -> dict:
    """The 35 points you enter. Each axis is clamped to its own ceiling."""
    ratings = ratings or {}
    parts = {}
    for axis, ceiling in QUALITATIVE_MAX.items():
        try:
            value = int(ratings.get(axis) or 0)
        except (TypeError, ValueError):
            value = 0
        parts[axis] = max(0, min(value, ceiling))
    return {"parts": parts, "total": sum(parts.values()),
            "max": sum(QUALITATIVE_MAX.values())}


def total_score(answers: dict, ratings: dict | None = None) -> dict:
    """The whole picture, and whether a human has looked at it yet.

    `reviewed` is False until at least one qualitative axis is non-zero. Without
    it a freshly-submitted application and one you rated as poor both read as a
    low number, and only one of them means anything.
    """
    auto = automatic_score(answers)
    manual = qualitative_score(ratings)
    return {
        "automatic": auto,
        "qualitative": manual,
        "total": auto["total"] + manual["total"],
        "max": TOTAL_MAX,
        "reviewed": manual["total"] > 0,
    }


# --- Rounds -------------------------------------------------------------------

def round_key(now: datetime | None = None) -> str:
    """The round an application submitted now belongs to: 'YYYY-MM'."""
    moment = now or datetime.now(timezone.utc)
    return f"{moment.year:04d}-{moment.month:02d}"


def should_close(received: int, round_status: str,
                 current_round: str, submitted_round: str) -> str | None:
    """Why this round should close, or None if it should stay open.

    Two independent reasons. The cap keeps a round reviewable; the month
    boundary keeps the cycle honest, so an under-subscribed round does not stay
    open into the next one and quietly become a two-month round.
    """
    if round_status == ROUND_CLOSED:
        return None
    if submitted_round != current_round:
        return CLOSED_BY_MONTH
    if received >= ROUND_APPLICATION_CAP:
        return CLOSED_BY_CAP
    return None


def seats_remaining(approved_count: int) -> int:
    return max(0, TOTAL_SEATS - approved_count)


def can_approve(approved_count: int) -> bool:
    return seats_remaining(approved_count) > 0

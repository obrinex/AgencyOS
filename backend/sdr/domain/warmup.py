"""Sending-identity warm-up and reputation thresholds.

A new domain that sends 500 cold emails on day one gets filtered, and the
damage is durable - domain reputation is slow to build and fast to lose. So
volume ramps, and the ramp is not negotiable by a campaign asking for more.

The curve below reaches a 200/day target in roughly three weeks, which is the
conventional shape for a cold domain. It is deliberately front-loaded slowly:
the first week is where a bad list does the most harm.

Pure module: no I/O, no clock. The caller supplies the day index and the
measured rates, which is what makes the thresholds testable.
"""

# Identity lifecycle.
WARMING = "warming"
HEALTHY = "healthy"
THROTTLED = "throttled"
PAUSED = "paused"
BLOCKED = "blocked"

#: Daily volume as a fraction of target, by day of warm-up. Index 0 is day 1.
#: Held at low absolute numbers early rather than as a smooth curve, because
#: percentages of a large target are still too much on day two.
RAMP_ABSOLUTE = [
    5, 10, 15, 20, 30, 40, 50,          # week 1
    65, 80, 95, 110, 125, 140, 155,     # week 2
    170, 180, 190, 200, 210, 220, 230,  # week 3
]

#: Bounce rate above which an identity is throttled. 3% is the figure most
#: providers treat as the warning line; 5% is where accounts get suspended.
BOUNCE_WARN = 0.03
BOUNCE_CRITICAL = 0.05

#: Spam-complaint thresholds. An order of magnitude tighter than bounces -
#: 0.1% is the industry line, and 0.3% risks blocklisting.
SPAM_WARN = 0.001
SPAM_CRITICAL = 0.003

#: Minimum sends before a rate means anything. Two bounces out of three sends
#: is a 67% bounce rate and tells you nothing.
MIN_SAMPLE = 20


def daily_cap(day_index: int, target: int) -> int:
    """Volume allowed on a given day of warm-up.

    `day_index` is zero-based. Past the ramp, the identity sends its target.
    Never exceeds the target, so raising the target mid-ramp does not cause a
    sudden jump.
    """
    target = max(0, int(target))
    if day_index < 0:
        return 0
    if day_index >= len(RAMP_ABSOLUTE):
        return target
    return min(RAMP_ABSOLUTE[day_index], target)


def is_warmed(day_index: int, target: int) -> bool:
    return daily_cap(day_index, target) >= target


def evaluate_health(*, sent_7d: int, bounces_7d: int, complaints_7d: int,
                    current_status: str = WARMING) -> tuple:
    """Decide an identity's status from its recent behaviour.

    Returns (status, reason). Deliberately one-directional for the bad news:
    a blocked identity is never automatically restored, because whatever
    caused it needs a human to look before more mail goes out under it.
    """
    if current_status == BLOCKED:
        return BLOCKED, "Blocked - requires manual review before sending resumes"

    if sent_7d < MIN_SAMPLE:
        # Not enough data to judge. Staying in warming is the safe default -
        # it keeps the cap low rather than promoting on a tiny sample.
        return (
            WARMING if current_status in (WARMING, HEALTHY) else current_status,
            f"Only {sent_7d} sends in 7 days - too few to judge reputation",
        )

    bounce_rate = bounces_7d / sent_7d
    spam_rate = complaints_7d / sent_7d

    if spam_rate >= SPAM_CRITICAL:
        return PAUSED, (
            f"Spam complaints at {spam_rate:.2%}, over the "
            f"{SPAM_CRITICAL:.1%} limit - sending paused"
        )
    if bounce_rate >= BOUNCE_CRITICAL:
        return PAUSED, (
            f"Bounce rate at {bounce_rate:.1%}, over the "
            f"{BOUNCE_CRITICAL:.0%} limit - sending paused"
        )
    if spam_rate >= SPAM_WARN:
        return THROTTLED, f"Spam complaints at {spam_rate:.2%} - volume reduced"
    if bounce_rate >= BOUNCE_WARN:
        return THROTTLED, f"Bounce rate at {bounce_rate:.1%} - volume reduced"

    return HEALTHY, f"Bounce {bounce_rate:.1%}, complaints {spam_rate:.2%} - healthy"


def throttled_cap(cap: int) -> int:
    """Volume for a throttled identity: a quarter, floor of one.

    Cutting to zero would look identical to paused and lose the signal about
    whether the reduced volume is recovering.
    """
    return max(1, int(cap * 0.25))


def effective_cap(*, day_index: int, target: int, status: str) -> int:
    """The cap actually applied, after warm-up stage and health."""
    if status in (PAUSED, BLOCKED):
        return 0
    base = daily_cap(day_index, target)
    if status == THROTTLED:
        return throttled_cap(base)
    return base


def reputation_score(*, sent_7d: int, bounces_7d: int, complaints_7d: int) -> float:
    """A 0-1 summary for the UI. Not used for decisions - the thresholds are.

    Exists so an operator can see an identity degrading before it crosses a
    line, rather than only when it trips.
    """
    if sent_7d < MIN_SAMPLE:
        return 1.0
    bounce_rate = bounces_7d / sent_7d
    spam_rate = complaints_7d / sent_7d
    # Complaints weigh ten times bounces, matching the threshold ratio.
    penalty = (bounce_rate / BOUNCE_CRITICAL) + (spam_rate / SPAM_CRITICAL)
    return round(max(0.0, 1.0 - min(penalty, 1.0)), 3)

"""Retry scheduling.

Kept pure and separate from the job runner so the timing rules can be tested
without a database or a clock.

Jitter matters more than it looks: without it, a provider outage that fails
200 jobs at once produces 200 simultaneous retries 60 seconds later, which is
a self-inflicted thundering herd against a service that is already unwell.

`Math.random()` equivalents are fine here (this is not a workflow script), but
the caller supplies the random function so tests stay deterministic.
"""

import random

#: Per-queue attempt limits, from the spec: sends are expensive to repeat,
#: scraping is cheap to abandon, enrichment is worth persisting with.
MAX_ATTEMPTS = {
    "send": 3,
    # Two attempts only: each retry is a fresh LLM generation with real cost,
    # and a draft that failed grounding or copy checks twice needs a human
    # looking at the dead-letter, not a fifth invoice.
    "personalization": 2,
    "enrichment": 5,
    "audit": 2,
    "research": 3,
    "scoring": 3,
    "discovery": 2,
    "default": 3,
}

BASE_DELAY_SECONDS = 60
MAX_DELAY_SECONDS = 6 * 60 * 60  # six hours; beyond that a human should look
JITTER_RATIO = 0.25


def max_attempts_for(queue: str) -> int:
    return MAX_ATTEMPTS.get(queue, MAX_ATTEMPTS["default"])


def delay_seconds(attempt: int, *, base: int = BASE_DELAY_SECONDS,
                  rand=random.random) -> int:
    """Exponential backoff with full-width jitter, in seconds.

    `attempt` is the number of attempts already made (1 after the first
    failure). Delay is capped so a job never disappears for a day.
    """
    attempt = max(1, int(attempt))
    exponential = min(base * (2 ** (attempt - 1)), MAX_DELAY_SECONDS)
    jitter = exponential * JITTER_RATIO * (rand() * 2 - 1)  # +/- 25%
    return max(1, int(exponential + jitter))


def should_retry(error_retryable: bool, attempt: int, queue: str) -> bool:
    """Whether a failed job gets another attempt.

    A non-retryable error is never retried regardless of budget: retrying a
    validation failure with identical input just burns the remaining attempts
    and delays the dead-letter that an operator needs to see.
    """
    if not error_retryable:
        return False
    return attempt < max_attempts_for(queue)

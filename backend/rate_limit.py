"""A DB-backed fixed-window rate limiter for the public endpoints.

`RATE_LIMITING.md` specified this and it was never built, which left two
unauthenticated write endpoints - the lead-capture webhook and the public lead
form - with no ceiling at all. The lead form is the expensive one: every
submission writes three documents, a notification per admin, a WhatsApp message
to the owner and a background LLM call, so an unthrottled script there burns
real money rather than merely filling a table.

Mongo rather than Redis, deliberately: the deployment target has no Redis and
`RATE_LIMITING.md` calls for something that works without one. The cost is one
extra round trip on public requests only.

## How the window works

Fixed window, not sliding. The counter's `_id` is
`"{scope}:{key}:{window_start_epoch}"`, so the upsert is atomic on the primary
key - no unique index to maintain and no read-modify-write to race. A caller
can therefore burst up to `2 x limit` across a window boundary; that is the
accepted trade for a limiter that costs one operation and cannot deadlock. The
limits here are set for abuse control, not fairness, so the doubling is
harmless.

Counters carry a TTL and delete themselves. `expires_at` is a real BSON date,
unlike the ISO strings used everywhere else in this codebase, because
`expireAfterSeconds` ignores anything that is not a date.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from pymongo import ReturnDocument

from database import db

logger = logging.getLogger(__name__)

COUNTERS = "rate_limit_counters"


def client_ip(request: Request | None) -> str:
    """The caller's address, trusting the platform's proxy header.

    Render and Vercel both terminate TLS in front of the app, so
    `request.client.host` is the proxy and `X-Forwarded-For` holds the real
    client first. That header is trivially forged by anyone talking to the app
    directly, so this is a speed bump against scripted abuse rather than an
    access control - never authorise anything on it.
    """
    if request is None:
        return "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:64]
    return (request.client.host if request.client else "unknown")[:64]


async def check_rate_limit(request: Request | None, *, scope: str, limit: int,
                           window_seconds: int, key: str | None = None,
                           detail: str | None = None) -> None:
    """Count this request against a window; raise 429 once it is over `limit`.

    `key` defaults to the caller's IP. Pass something else - an email address,
    a form slug - to limit per identity as well, which is what stops one
    address being submitted a thousand times from a thousand addresses.

    A failure inside the limiter lets the request through. An outage in the
    throttle must not take down the lead form: dropping real leads is a worse
    outcome than briefly accepting junk, and the endpoint's own validation
    still applies.
    """
    bucket = key or client_ip(request)
    window_start = int(time.time()) // window_seconds * window_seconds
    counter_id = f"{scope}:{bucket}:{window_start}"

    try:
        doc = await db[COUNTERS].find_one_and_update(
            {"_id": counter_id},
            {
                "$inc": {"count": 1},
                "$setOnInsert": {
                    "scope": scope,
                    "expires_at": datetime.now(timezone.utc)
                                  + timedelta(seconds=window_seconds * 2),
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except Exception:
        logger.warning("Rate limiter unavailable for scope %s; allowing request",
                       scope, exc_info=True)
        return

    if (doc or {}).get("count", 0) > limit:
        logger.warning("Rate limit hit: scope=%s bucket=%s", scope, bucket)
        raise HTTPException(
            status_code=429,
            detail=detail or "Too many requests. Please try again shortly.",
        )


async def create_rate_limit_indexes() -> None:
    """Called from `database.create_indexes()`. Safe to run repeatedly."""
    try:
        await db[COUNTERS].create_index("expires_at", expireAfterSeconds=0)
    except Exception as exc:
        # An index is a performance concern and must never stop the application
        # serving requests. Learned the hard way here: one rejected index spec
        # previously aborted startup and 500'd every endpoint in the app.
        logger.error("Could not create rate limit TTL index: %s", exc)

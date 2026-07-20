"""The job queue: a Mongo collection, claimed atomically, drained by cron.

See ADR 0003 for why this rather than a real queue. The short version: Vercel
serverless has no long-running process, no shared memory and a 60-second
ceiling, and the deployment has no queue product. `find_one_and_update` gives
genuine at-most-once claiming with zero new infrastructure - the same atomic
primitive `next_counter()` already uses for invoice numbers.

Two invariants hold this together:

1. **`idempotency_key` is uniquely indexed.** Enqueueing the same logical work
   twice fails at the database rather than sending a second email to a real
   person.
2. **Claims carry a lease** (`locked_until`). If an invocation dies mid-job -
   which on serverless means a timeout with no chance to clean up - the lease
   expires and the job is reclaimed, rather than being stuck in `running`
   forever.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from database import db, now_iso, serialize_doc, serialize_list
from sdr.collections import JOBS
from sdr.domain import backoff
from sdr.errors import SDRError, ValidationError
from sdr.repositories.base import object_id, paginate

logger = logging.getLogger(__name__)

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
DEAD_LETTER = "dead_letter"
CANCELLED = "cancelled"

#: How long a claim is held before another invocation may steal it. Longer
#: than the 60s function ceiling, so a job cannot be running twice.
LEASE_SECONDS = 300

#: Finished jobs expire via the TTL index after this long.
RETENTION_DAYS = 30

#: Leave headroom before the serverless ceiling so the drain loop can finish
#: its bookkeeping and return a response rather than being killed mid-write.
DRAIN_BUDGET_SECONDS = 45


async def enqueue(*, agent_key: str, payload: dict, queue: str = "default",
                  idempotency_key: str | None = None, run_after: str | None = None,
                  priority: int = 0, correlation_id: str | None = None,
                  user_id: str | None = None) -> dict:
    """Add a job. Returns the job, or the existing one if already queued.

    A duplicate `idempotency_key` is not an error - it is the mechanism
    working. Re-running discovery over the same 500 companies should enqueue
    500 enrichment jobs the first time and zero the second.
    """
    from pymongo.errors import DuplicateKeyError

    doc = {
        "agent_key": agent_key,
        "queue": queue,
        "payload": payload,
        "status": QUEUED,
        "attempt": 0,
        "max_attempts": backoff.max_attempts_for(queue),
        "priority": priority,
        "idempotency_key": idempotency_key,
        "correlation_id": correlation_id,
        "created_by": user_id,
        "run_after": run_after or now_iso(),
        "locked_until": None,
        "last_error": None,
        "run_ids": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "expires_at": None,
    }

    if idempotency_key:
        existing = await db[JOBS].find_one({"idempotency_key": idempotency_key})
        if existing:
            return {**serialize_doc(existing), "duplicate": True}

    try:
        result = await db[JOBS].insert_one(doc)
    except DuplicateKeyError:
        # Lost a race against a concurrent enqueue. The other one won, which
        # is exactly the desired outcome.
        existing = await db[JOBS].find_one({"idempotency_key": idempotency_key})
        return {**serialize_doc(existing), "duplicate": True}

    return {**serialize_doc(await db[JOBS].find_one({"_id": result.inserted_id})),
            "duplicate": False}


async def enqueue_many(jobs: list) -> dict:
    """Bulk enqueue. Returns counts rather than documents - callers batch
    hundreds of these and do not want the payloads back."""
    created, duplicates = 0, 0
    for job in jobs:
        result = await enqueue(**job)
        if result.get("duplicate"):
            duplicates += 1
        else:
            created += 1
    return {"created": created, "duplicates": duplicates}


async def claim_next(queues: list | None = None) -> dict | None:
    """Atomically claim one due job.

    The `$or` covers both a genuinely queued job and one whose lease expired
    because the invocation holding it died. Sorted by priority then age, so a
    high-priority job jumps the line but nothing starves.
    """
    now = now_iso()
    query = {
        "$or": [
            {"status": QUEUED, "run_after": {"$lte": now}},
            {"status": RUNNING, "locked_until": {"$lt": now}},
        ]
    }
    if queues:
        query["queue"] = {"$in": queues}

    lease_until = (datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)).isoformat()

    doc = await db[JOBS].find_one_and_update(
        query,
        {
            "$set": {
                "status": RUNNING,
                "locked_until": lease_until,
                "started_at": now,
                "updated_at": now,
            },
            "$inc": {"attempt": 1},
        },
        sort=[("priority", -1), ("run_after", 1)],
        return_document=True,
    )
    return serialize_doc(doc)


async def complete(job_id: str, *, run_id: str | None = None, output=None) -> None:
    patch = {
        "status": SUCCEEDED,
        "locked_until": None,
        "finished_at": now_iso(),
        "updated_at": now_iso(),
        "last_error": None,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS),
    }
    update = {"$set": patch}
    if run_id:
        update["$push"] = {"run_ids": run_id}
    await db[JOBS].update_one({"_id": object_id(job_id, "job id")}, update)


async def fail(job_id: str, *, error: Exception, run_id: str | None = None,
               rand=None) -> str:
    """Record a failure and decide between retry and dead-letter.

    Returns the resulting status so the drain loop can report it.
    """
    job = await db[JOBS].find_one({"_id": object_id(job_id, "job id")})
    if not job:
        return DEAD_LETTER

    attempt = job.get("attempt", 1)
    queue = job.get("queue", "default")
    retryable = getattr(error, "retryable", True)

    error_record = {
        "type": type(error).__name__,
        "message": str(error)[:1000],
        "retryable": retryable,
        "attempt": attempt,
        "at": now_iso(),
    }

    if backoff.should_retry(retryable, attempt, queue):
        delay = backoff.delay_seconds(attempt, **({"rand": rand} if rand else {}))
        run_after = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        patch = {
            "status": QUEUED,
            "locked_until": None,
            "run_after": run_after,
            "last_error": error_record,
            "updated_at": now_iso(),
        }
        status = QUEUED
    else:
        # Dead-lettered work is abandoned work. It must be visible - the
        # Overview page surfaces the count and the Agents page can replay it.
        patch = {
            "status": DEAD_LETTER,
            "locked_until": None,
            "last_error": error_record,
            "finished_at": now_iso(),
            "updated_at": now_iso(),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS),
        }
        status = DEAD_LETTER
        logger.error(
            "Job %s (%s) dead-lettered after %s attempts: %s",
            job_id, job.get("agent_key"), attempt, error,
        )

    update = {"$set": patch}
    if run_id:
        update["$push"] = {"run_ids": run_id}
    await db[JOBS].update_one({"_id": object_id(job_id, "job id")}, update)
    return status


async def drain(*, queues: list | None = None, budget_seconds: int = DRAIN_BUDGET_SECONDS,
                max_jobs: int = 100) -> dict:
    """Run due jobs until the time budget is nearly spent.

    Called by the cron endpoint. Returns a report rather than raising: a
    single poisonous job must not abort the whole drain, or one bad record
    blocks the queue indefinitely.
    """
    from sdr.agents.base.agent import AgentContext
    from sdr.agents.registry import get_agent

    started = time.monotonic()
    processed, succeeded, failed, dead = 0, 0, 0, 0
    results = []

    while processed < max_jobs:
        if time.monotonic() - started > budget_seconds:
            break

        job = await claim_next(queues)
        if not job:
            break

        processed += 1
        agent = get_agent(job["agent_key"])

        if not agent:
            await fail(job["id"], error=ValidationError(
                f"No agent registered under '{job['agent_key']}'."
            ))
            failed += 1
            results.append({"job_id": job["id"], "status": "no_such_agent"})
            continue

        ctx = AgentContext(
            correlation_id=job.get("correlation_id"),
            trigger="schedule",
            attempt=job.get("attempt", 1),
            max_attempts=job.get("max_attempts", 1),
        )

        try:
            result = await agent.run(job["payload"], ctx)
            await complete(job["id"], run_id=result.run_id)
            succeeded += 1
            results.append({"job_id": job["id"], "agent": agent.key, "status": "succeeded"})
        except SDRError as exc:
            status = await fail(job["id"], error=exc, run_id=ctx.run_id)
            failed += 1
            if status == DEAD_LETTER:
                dead += 1
            results.append({
                "job_id": job["id"], "agent": agent.key,
                "status": status, "error": str(exc)[:200],
            })
        except Exception as exc:
            logger.exception("Unhandled error draining job %s", job["id"])
            status = await fail(job["id"], error=exc, run_id=ctx.run_id)
            failed += 1
            if status == DEAD_LETTER:
                dead += 1
            results.append({
                "job_id": job["id"], "agent": agent.key,
                "status": status, "error": str(exc)[:200],
            })

    return {
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "dead_lettered": dead,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "exhausted_budget": (time.monotonic() - started) > budget_seconds,
        "results": results[:50],
    }


async def replay(job_id: str) -> dict:
    """Requeue a dead-lettered job.

    Resets the attempt counter: an operator replaying a job has usually fixed
    the underlying cause, so it deserves a full retry budget rather than
    immediately dead-lettering again.
    """
    job = await db[JOBS].find_one({"_id": object_id(job_id, "job id")})
    if not job:
        raise ValidationError("Job not found")
    if job.get("status") not in (DEAD_LETTER, FAILED, CANCELLED):
        raise ValidationError(
            f"Only failed or dead-lettered jobs can be replayed (this one is "
            f"'{job.get('status')}')."
        )

    await db[JOBS].update_one(
        {"_id": job["_id"]},
        {"$set": {
            "status": QUEUED,
            "attempt": 0,
            "run_after": now_iso(),
            "locked_until": None,
            "expires_at": None,
            "updated_at": now_iso(),
        }},
    )
    return serialize_doc(await db[JOBS].find_one({"_id": job["_id"]}))


async def cancel(job_id: str) -> dict:
    await db[JOBS].update_one(
        {"_id": object_id(job_id, "job id")},
        {"$set": {"status": CANCELLED, "locked_until": None, "updated_at": now_iso()}},
    )
    return serialize_doc(await db[JOBS].find_one({"_id": object_id(job_id, "job id")}))


async def list_jobs(*, status: str | None = None, agent_key: str | None = None,
                    limit: int = 50, cursor: str | None = None) -> dict:
    query = {}
    if status:
        query["status"] = status
    if agent_key:
        query["agent_key"] = agent_key
    return await paginate(JOBS, query, sort=("created_at", -1), limit=limit, cursor=cursor)


async def stats() -> dict:
    cursor = db[JOBS].aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ])
    rows = await cursor.to_list(20)
    counts = {row["_id"]: row["count"] for row in rows}

    # Oldest queued job - the number that actually tells you the pinger died.
    oldest = await db[JOBS].find({"status": QUEUED}).sort("run_after", 1).to_list(1)
    oldest_queued_at = oldest[0]["run_after"] if oldest else None

    return {
        "queued": counts.get(QUEUED, 0),
        "running": counts.get(RUNNING, 0),
        "succeeded": counts.get(SUCCEEDED, 0),
        "dead_letter": counts.get(DEAD_LETTER, 0),
        "cancelled": counts.get(CANCELLED, 0),
        "oldest_queued_at": oldest_queued_at,
        **queue_health(oldest_queued_at),
    }


#: A job due this long ago means nothing has drained since. The external
#: pinger runs every few minutes, so an hour is well past coincidence.
STALE_QUEUE_MINUTES = 60


def queue_health(oldest_queued_at: str | None, *, now: str | None = None) -> dict:
    """Whether the queue is draining, stated rather than left to be noticed.

    `oldest_queued_at` has always been exposed and nothing ever read it. If
    the external pinger dies, work accumulates in complete silence: no error,
    no failed job, just a system that quietly stops doing anything. This
    turns that into something a page can show.
    """
    if not oldest_queued_at:
        return {"queue_stalled": False, "queue_lag_minutes": 0}

    from datetime import datetime, timezone as dt_timezone

    def _parse(value):
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt_timezone.utc)

    try:
        due = _parse(oldest_queued_at)
    except (ValueError, TypeError):
        return {"queue_stalled": False, "queue_lag_minutes": 0}

    reference = _parse(now) if now else datetime.now(dt_timezone.utc)
    lag = max(0, int((reference - due).total_seconds() // 60))
    return {"queue_stalled": lag >= STALE_QUEUE_MINUTES, "queue_lag_minutes": lag}


async def dead_letters(limit: int = 50) -> list:
    docs = await db[JOBS].find({"status": DEAD_LETTER}) \
        .sort("updated_at", -1).to_list(limit)
    return serialize_list(docs)

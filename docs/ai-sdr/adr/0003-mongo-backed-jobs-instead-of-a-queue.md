# ADR 0003 — A Mongo-backed job collection, drained by cron

**Status:** Accepted · **Date:** 2026-07-20 · **Phase:** 1 (schema), Phase 3 (runner)

## Context

The spec calls for fifteen named queues, exponential backoff with jitter,
per-provider circuit breakers, dead-letter replay, and warm-up schedulers that
ramp sending caps through the day.

The deployment constrains all of it:

- **No queue exists.** No Celery, RQ, APScheduler, Inngest, Trigger.dev or
  QStash. The only background mechanisms are in-process asyncio loops (disabled
  in production, and unusable on serverless) and two cron endpoints.
- **60-second hard request ceiling** (`vercel.json` `maxDuration: 60`).
  `leadfinder.py:149-151` already tunes its HTTP timeouts around this.
- **Vercel Hobby permits daily crons only.** An hourly schedule was rejected
  at deploy time.
- **No shared in-process state survives an invocation.** `login_attempts` and
  `fx_rates` are collections precisely because of this.

## Decision

A `sdr_jobs` collection, claimed atomically, drained by a new cron endpoint,
triggered by an external pinger.

**Claiming.** `find_one_and_update` on `{status: "queued", run_after: {$lte: now}}`
setting `status: "running"` and a `locked_until` lease. This is the same atomic
primitive `next_counter()` already uses for invoice numbers, and it gives real
at-most-once claiming with no new infrastructure.

**Idempotency.** A unique sparse index on `idempotency_key`. This is the single
most important index in the module: it is what makes redelivery safe. A
duplicate insert fails loudly rather than sending a second email to a real
person.

**Retries.** `attempts` / `max_attempts` on the document, exponential backoff
with jitter written into `run_after`. Exhausted jobs move to `dead_letter` and
surface on the Overview page — abandoned work must be visible, not silent.

**Bounding.** A TTL index on `expires_at` expires finished jobs after 30 days,
so the collection stays bounded without a cleanup cron. TTL needs a real BSON
date, so writers set `expires_at` as a datetime rather than the ISO string used
everywhere else in this codebase. That inconsistency is deliberate and is
called out in `collections.py`.

**Triggering.** An external free pinger (cron-job.org or a GitHub Actions
schedule) hits `/api/automations/cron/sdr` every ~5 minutes with `CRON_SECRET`.
The endpoint drains until its 60-second budget is nearly spent, then returns.

The runner is written so the trigger source is irrelevant — moving to Vercel
Pro's minute-level crons later is a configuration change, not a code change.

## Consequences

**Good.** Zero new infrastructure and zero recurring cost. Retries,
dead-lettering, idempotency and observability are all genuinely implementable.
Everything stays in one database that is already backed up.

**Bad.** Throughput is capped by what fits in 60 seconds per invocation.
Mongo-as-a-queue has no fan-out, no priority preemption and no backpressure
signalling. At the spec's stated target of 100k messages/day this design does
not hold and will need a real queue — that threshold is far beyond current
volumes, and this ADR is where the successor should start reading.

**Risk.** If the external pinger silently stops, work queues up invisibly.
Mitigation: the Overview page surfaces `jobs_queued`, and a stale-queue alert
belongs in Phase 3 alongside the runner.

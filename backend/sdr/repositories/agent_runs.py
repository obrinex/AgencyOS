"""Agent run recording - the observability spine.

Every agent execution opens a row here before it starts and closes it however
it ends, success or failure. That is what makes a single lead's journey
reconstructable across dozens of runs via `correlation_id`, and what makes a
failure inspectable rather than merely absent.

Inputs and outputs are redacted before persistence (see
`agents/base/guardrails.redact`) so this collection does not become a second,
less-protected copy of the contact database.
"""

from datetime import datetime, timedelta, timezone

from database import db, now_iso, serialize_doc, serialize_list
from sdr.agents.base.guardrails import redact
from sdr.collections import AGENT_RUNS
from sdr.repositories.base import object_id, paginate

#: Runs self-expire after 30 days via the TTL index. Long enough to diagnose
#: last month's incident, short enough that the collection stays bounded
#: without a cleanup job.
RETENTION_DAYS = 30


async def start_run(*, agent_key: str, version: str, trigger: str,
                    entity_type: str | None = None, entity_id: str | None = None,
                    correlation_id: str | None = None, parent_run_id: str | None = None,
                    attempt: int = 1, max_attempts: int = 1,
                    payload: dict | None = None) -> str:
    doc = {
        "agent_key": agent_key,
        "version": version,
        "trigger": trigger,
        "entity_type": entity_type,
        "entity_id": entity_id,
        # Falls back to the run's own id after insert, so a run that starts a
        # chain becomes the root of its own correlation.
        "correlation_id": correlation_id,
        "parent_run_id": parent_run_id,
        "status": "running",
        "attempt": attempt,
        "max_attempts": max_attempts,
        "input": redact(payload or {}),
        "output": None,
        "model_used": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd_estimated": 0.0,
        "llm_calls": 0,
        "duration_ms": None,
        "error_type": None,
        "error_message": None,
        "guardrail_flags": [],
        "started_at": now_iso(),
        "finished_at": None,
        "created_at": now_iso(),
        # TTL needs a real BSON date, unlike every other timestamp in this
        # codebase which is an ISO string.
        "expires_at": datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS),
    }
    result = await db[AGENT_RUNS].insert_one(doc)
    run_id = str(result.inserted_id)

    if not correlation_id:
        await db[AGENT_RUNS].update_one(
            {"_id": result.inserted_id}, {"$set": {"correlation_id": run_id}}
        )
    return run_id


async def finish_run(run_id: str, *, status: str, output=None,
                     model_used: str | None = None, cost: dict | None = None,
                     duration_ms: int | None = None,
                     error_type: str | None = None, error_message: str | None = None,
                     guardrail_flags: list | None = None,
                     provider_used: str | None = None) -> None:
    patch = {
        "status": status,
        "output": redact(output) if output is not None else None,
        "model_used": model_used,
        "provider_used": provider_used,
        "duration_ms": duration_ms,
        "error_type": error_type,
        "error_message": (error_message or "")[:2000] or None,
        "guardrail_flags": guardrail_flags or [],
        "finished_at": now_iso(),
    }
    if cost:
        patch.update(cost)
    await db[AGENT_RUNS].update_one(
        {"_id": object_id(run_id, "run id")}, {"$set": patch}
    )


async def list_runs(*, agent_key: str | None = None, status: str | None = None,
                    entity_id: str | None = None, correlation_id: str | None = None,
                    limit: int = 50, cursor: str | None = None) -> dict:
    query = {}
    if agent_key:
        query["agent_key"] = agent_key
    if status:
        query["status"] = status
    if entity_id:
        query["entity_id"] = entity_id
    if correlation_id:
        query["correlation_id"] = correlation_id
    # Not scope()d: agent runs have no deleted_at and are never soft-deleted.
    return await paginate(AGENT_RUNS, query, sort=("created_at", -1),
                          limit=limit, cursor=cursor)


async def get_run(run_id: str) -> dict | None:
    doc = await db[AGENT_RUNS].find_one({"_id": object_id(run_id, "run id")})
    return serialize_doc(doc)


async def get_trace(correlation_id: str) -> list:
    """Every run in one lead's journey, oldest first.

    This is the payoff for propagating correlation_id: "why did this lead end
    up disqualified" is answerable by reading one list.
    """
    docs = await db[AGENT_RUNS].find({"correlation_id": correlation_id}) \
        .sort("created_at", 1).to_list(200)
    return serialize_list(docs)


async def agent_stats(hours: int = 24) -> list:
    """Per-agent health for the Agents page.

    Timestamps are ISO strings, so the window is a lexicographic comparison -
    correct for UTC ISO, and the reason `since` is built the way it is.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    cursor = db[AGENT_RUNS].aggregate([
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": "$agent_key",
            "total": {"$sum": 1},
            "succeeded": {"$sum": {"$cond": [{"$eq": ["$status", "succeeded"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            "cost_usd": {"$sum": "$cost_usd_estimated"},
            "avg_duration_ms": {"$avg": "$duration_ms"},
            "last_run_at": {"$max": "$created_at"},
        }},
    ])
    rows = await cursor.to_list(100)
    stats = []
    for row in rows:
        total = row["total"] or 1
        stats.append({
            "agent_key": row["_id"],
            "total": row["total"],
            "succeeded": row["succeeded"],
            "failed": row["failed"],
            "success_rate": round(row["succeeded"] / total, 3),
            "cost_usd_estimated": round(row["cost_usd"] or 0.0, 4),
            "avg_duration_ms": int(row["avg_duration_ms"] or 0),
            "last_run_at": row["last_run_at"],
        })
    stats.sort(key=lambda s: s["agent_key"])
    return stats


async def daily_spend_usd() -> float:
    """Estimated LLM spend since midnight UTC, for the org-wide cap."""
    since = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    cursor = db[AGENT_RUNS].aggregate([
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": None, "total": {"$sum": "$cost_usd_estimated"}}},
    ])
    rows = await cursor.to_list(1)
    return round(rows[0]["total"], 4) if rows else 0.0

"""Aggregates for the SDR Overview page.

Kept in the repository layer because it touches `db`. The host dashboard
(`routers/dashboard.py`) counts documents per request; at SDR lead volumes
that stops being viable and these move to a materialised rollup refreshed by
the cron (Phase 9). Until then, aggregation pipelines with a covering index
are honest and fast enough - and this is noted here so the eventual switch is
a deliberate change rather than a surprise.
"""

from database import db, serialize_list
from sdr.collections import AGENT_RUNS, COMPANIES, JOBS
from sdr.domain import pipeline
from sdr.repositories.base import scope


async def _count_by_stage() -> dict:
    cursor = db.leads.aggregate([
        {"$match": scope({"sdr_managed": True})},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
    ])
    rows = await cursor.to_list(100)
    return {row["_id"]: row["count"] for row in rows if row["_id"]}


async def get_overview() -> dict:
    """KPI payload for the Overview page.

    Returns an object, not a list - so `fallbackForGet` in the frontend api
    client needs a matching entry, or a failed GET resolves to [] and the page
    crashes on property access. See the Phase 0 report, section 8.
    """
    by_stage = await _count_by_stage()

    open_count = sum(by_stage.get(s, 0) for s in pipeline.OPEN_STAGES)
    won_count = by_stage.get(pipeline.WON, 0)
    lost_count = by_stage.get(pipeline.LOST, 0) + by_stage.get(pipeline.REJECTED, 0)

    companies_total = await db[COMPANIES].count_documents(scope({}))
    companies_enriched = await db[COMPANIES].count_documents(
        scope({"enrichment_status": "complete"})
    )

    qualified = await db.leads.count_documents(
        scope({"sdr_managed": True, "qualification_status": "qualified"})
    )
    needs_review = await db.leads.count_documents(
        scope({"sdr_managed": True, "qualification_status": "needs_review"})
    )

    # Job health. `dead_letter` is the number an operator actually needs to
    # see - it means work was abandoned after exhausting its retries.
    jobs_queued = await db[JOBS].count_documents({"status": "queued"})
    jobs_dead = await db[JOBS].count_documents({"status": "dead_letter"})

    runs_failed = await db[AGENT_RUNS].count_documents({"status": "failed"})
    recent_runs = await db[AGENT_RUNS].find({}).sort("created_at", -1).to_list(10)

    conversion_base = won_count + lost_count
    return {
        "leads": {
            "open": open_count,
            "won": won_count,
            "lost": lost_count,
            "qualified": qualified,
            "needs_review": needs_review,
            "by_stage": by_stage,
        },
        "companies": {
            "total": companies_total,
            "enriched": companies_enriched,
            "enrichment_coverage": (
                round(companies_enriched / companies_total, 3) if companies_total else 0.0
            ),
        },
        "conversion": {
            "won_rate": round(won_count / conversion_base, 3) if conversion_base else 0.0,
            "sample_size": conversion_base,
        },
        "health": {
            "jobs_queued": jobs_queued,
            "jobs_dead_letter": jobs_dead,
            "agent_runs_failed": runs_failed,
        },
        "recent_runs": serialize_list(recent_runs),
    }

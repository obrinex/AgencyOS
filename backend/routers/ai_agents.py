"""Platform-wide AI monitor.

Deliberately separate from `routers/sdr.py`: this is the view across *every*
AI capability in the app, not the SDR module's own pages. The SDR endpoints
stay where they are and keep serving that module.

Guarded by `require_staff` rather than the `ai_sdr` module permission - a
team member restricted away from the SDR module should still be able to see
that the proposal writer is failing.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

import ai_platform
from auth_utils import require_staff
from sdr.agents.base import providers as llm_providers
from sdr.repositories import agent_runs as runs_repo
from sdr.services import jobs as jobs_service

router = APIRouter(prefix="/api/ai-agents", tags=["ai-agents"])


@router.get("/overview")
async def overview(hours: int = Query(default=24, ge=1, le=720),
                   user: dict = Depends(require_staff)):
    """Everything the monitor's landing view needs, in one call.

    Stats are keyed by agent/assistant key and merged into the catalogue
    client-side, so a capability that has never run still appears - with
    "no runs yet" rather than being invisible.
    """
    stats = await runs_repo.agent_stats(hours=hours)
    by_key = {row["agent_key"]: row for row in stats}

    groups = ai_platform.grouped_catalogue()
    totals = {"total": 0, "succeeded": 0, "failed": 0, "cost_usd": 0.0}

    for group in groups:
        for item in group["items"]:
            row = by_key.get(item["key"])
            item["stats"] = row
            if row:
                totals["total"] += row["total"]
                totals["succeeded"] += row["succeeded"]
                totals["failed"] += row["failed"]
                totals["cost_usd"] += row["cost_usd_estimated"]

    totals["cost_usd"] = round(totals["cost_usd"], 4)
    totals["success_rate"] = (
        round(totals["succeeded"] / totals["total"], 3) if totals["total"] else None
    )

    # Capabilities with runs that are not in the catalogue - usually an agent
    # that was renamed. Surfaced rather than dropped, so history is not lost
    # silently.
    known = {item["key"] for group in groups for item in group["items"]}
    orphans = [row for row in stats if row["agent_key"] not in known]

    return {
        "window_hours": hours,
        "categories": ai_platform.CATEGORIES,
        "groups": groups,
        "totals": totals,
        "unlisted": orphans,
        "jobs": await jobs_service.stats(),
        "daily_spend_usd": await runs_repo.daily_spend_usd(),
        "providers": llm_providers.describe(),
        "active_provider_chain": llm_providers.available(),
    }


@router.get("/providers")
async def list_providers(user: dict = Depends(require_staff)):
    """The free-tier LLM catalogue, including providers with no key set.

    Showing the unconfigured ones is the point - it is how someone discovers
    they could add a free Groq key and gain a faster fallback.
    """
    return {
        "providers": llm_providers.describe(),
        "active_chain": llm_providers.available(),
        "note": (
            "Providers are tried in priority order. A rate limit or quota "
            "refusal moves to the next one, which is what makes free tiers "
            "usable. Limits shown are indicative and change without notice."
        ),
    }


@router.get("/runs")
async def list_runs(
    agent_key: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    user: dict = Depends(require_staff),
):
    """Runs across every capability, optionally filtered by use case."""
    if category and not agent_key:
        keys = [
            item["key"]
            for group in ai_platform.grouped_catalogue() if group["category"] == category
            for item in group["items"]
        ]
        results = []
        for key in keys:
            page = await runs_repo.list_runs(agent_key=key, status=status, limit=limit)
            results.extend(page["items"])
        results.sort(key=lambda run: run.get("created_at") or "", reverse=True)
        return {"items": results[:limit], "next_cursor": None, "has_more": False}

    return await runs_repo.list_runs(
        agent_key=agent_key, status=status, limit=limit, cursor=cursor
    )


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: dict = Depends(require_staff)):
    from fastapi import HTTPException

    run = await runs_repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/catalogue")
async def catalogue(user: dict = Depends(require_staff)):
    """Every AI capability in the app, grouped by what it is used for."""
    return {
        "categories": ai_platform.CATEGORIES,
        "groups": ai_platform.grouped_catalogue(),
    }

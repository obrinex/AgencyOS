"""Discovery orchestration: providers -> post-filter -> dedupe -> storage.

A run is recorded in `sdr_discovery_runs` whatever happens, including failure,
because "we searched Pune for dentists and got nothing" is a result worth
keeping - it stops the same fruitless search being repeated by hand.

Partial success is the normal case, not an error path. One dead provider does
not fail the run; it is recorded in `provider_results` and the run is marked
`partial`. The spec is explicit about this: commit what you got.
"""

import logging

from database import db, now_iso, serialize_doc
from sdr.collections import DISCOVERY_RUNS
from sdr.dto.filters import DiscoveryFilters, matches
from sdr.errors import SDRError, ValidationError
from sdr.providers import registry
from sdr.repositories import companies as companies_repo
from sdr.repositories import leads as leads_repo
from sdr.repositories.base import scope, stamp_create, stamp_update

logger = logging.getLogger(__name__)


async def run_discovery(filters: DiscoveryFilters, *, user: dict,
                        create_leads: bool = False,
                        icp_profile_id: str | None = None) -> dict:
    """Execute a discovery run and persist everything it finds."""
    selected, rejected = registry.select_for_search(filters)

    run_doc = {
        "filters": filters.model_dump(),
        "icp_profile_id": icp_profile_id,
        "providers_selected": [provider.key for provider, _ in selected],
        "providers_rejected": rejected,
        "status": "running",
        "requested_count": filters.limits.max_results,
        "discovered_count": 0,
        "deduped_count": 0,
        "cost_usd": 0.0,
        "started_at": now_iso(),
        "finished_at": None,
        "error": None,
    }
    stamp_create(run_doc, user)
    run_id = str((await db[DISCOVERY_RUNS].insert_one(run_doc)).inserted_id)

    if not selected:
        reasons = "; ".join(f"{r['label']}: {r['reason']}" for r in rejected) or "none registered"
        await _finish(run_id, {
            "status": "failed",
            "error": f"No provider could run this search ({reasons}).",
        })
        raise ValidationError(
            f"No provider can run this search. {reasons}",
            detail={"rejected": rejected, "discovery_run_id": run_id},
        )

    raw_records = []
    provider_results = []
    total_cost = 0.0

    for provider, report in selected:
        try:
            page = await provider.search(filters)
        except SDRError as exc:
            # A provider failing is expected often enough that it must not
            # abort the run - record it and continue to the next one.
            logger.warning("Provider %s failed during discovery: %s", provider.key, exc)
            provider_results.append({
                "provider": provider.key, "label": provider.label,
                "status": "failed", "error": exc.message, "returned": 0,
                "native_filters": sorted(report.native),
                "post_filters": sorted(report.post_filter),
            })
            continue

        raw_records.extend(page.items)
        total_cost += page.cost_usd
        provider_results.append({
            "provider": provider.key, "label": provider.label,
            "status": "ok", "returned": len(page.items),
            "cost_usd": page.cost_usd, "warnings": page.warnings,
            "native_filters": sorted(report.native),
            # Stating which filters the provider could not honour natively is
            # the difference between a trustworthy result set and one that is
            # quietly narrower than the operator believes.
            "post_filters": sorted(report.post_filter),
        })

        if len(raw_records) >= filters.limits.max_results:
            break

    # Post-filter whatever the providers could not enforce themselves.
    kept, filtered_out = [], {}
    for record in raw_records:
        passed, failed_on = matches(record, filters)
        if passed:
            kept.append(record)
        else:
            filtered_out[failed_on] = filtered_out.get(failed_on, 0) + 1

    kept = kept[: filters.limits.max_results]

    upsert = await companies_repo.upsert_many(kept, discovery_run_id=run_id)

    lead_result = {"created": 0, "already_existed": 0, "lead_ids": []}
    if create_leads and upsert["company_ids"]:
        found = await companies_repo.companies_by_ids(upsert["company_ids"])
        lead_result = await leads_repo.create_many_from_companies(
            found, icp_profile_id=icp_profile_id, owner_id=user.get("id")
        )

    any_failed = any(r["status"] == "failed" for r in provider_results)
    status = "partial" if any_failed and kept else ("failed" if not kept else "completed")

    await _finish(run_id, {
        "status": status,
        "provider_results": provider_results,
        "discovered_count": len(raw_records),
        "kept_count": len(kept),
        "filtered_out": filtered_out,
        "deduped_count": upsert["deduped_in_batch"],
        "inserted_count": upsert["inserted"],
        "merged_count": upsert["merged"],
        "leads_created": lead_result["created"],
        "cost_usd": round(total_cost, 4),
    })

    return {
        "discovery_run_id": run_id,
        "status": status,
        "providers": provider_results,
        "providers_rejected": rejected,
        "discovered": len(raw_records),
        "kept": len(kept),
        "filtered_out": filtered_out,
        "companies": upsert,
        "leads": lead_result,
        "cost_usd": round(total_cost, 4),
    }


async def import_companies(records: list, *, user: dict, create_leads: bool = True,
                           filters: DiscoveryFilters | None = None,
                           source_label: str = "csv_import") -> dict:
    """Import already-parsed records (CSV upload, manual paste).

    Shares the discovery path deliberately: imported rows get the same
    normalisation, dedupe and audit trail as anything from an API.
    """
    filters = filters or DiscoveryFilters()

    kept, filtered_out = [], {}
    for record in records:
        passed, failed_on = matches(record, filters)
        if passed:
            kept.append(record)
        else:
            filtered_out[failed_on] = filtered_out.get(failed_on, 0) + 1

    run_doc = {
        "filters": filters.model_dump(),
        "providers_selected": [source_label],
        "providers_rejected": [],
        "status": "running",
        "requested_count": len(records),
        "started_at": now_iso(),
    }
    stamp_create(run_doc, user)
    run_id = str((await db[DISCOVERY_RUNS].insert_one(run_doc)).inserted_id)

    upsert = await companies_repo.upsert_many(kept, discovery_run_id=run_id)

    lead_result = {"created": 0, "already_existed": 0, "lead_ids": []}
    if create_leads and upsert["company_ids"]:
        found = await companies_repo.companies_by_ids(upsert["company_ids"])
        lead_result = await leads_repo.create_many_from_companies(
            found, owner_id=user.get("id"), source="csv_import"
        )

    await _finish(run_id, {
        "status": "completed",
        "discovered_count": len(records),
        "kept_count": len(kept),
        "filtered_out": filtered_out,
        "deduped_count": upsert["deduped_in_batch"],
        "inserted_count": upsert["inserted"],
        "merged_count": upsert["merged"],
        "leads_created": lead_result["created"],
        "cost_usd": 0.0,
    })

    return {
        "discovery_run_id": run_id,
        "kept": len(kept),
        "filtered_out": filtered_out,
        "companies": upsert,
        "leads": lead_result,
    }


async def _finish(run_id: str, patch: dict) -> None:
    from sdr.repositories.base import object_id
    patch = dict(patch)
    patch["finished_at"] = now_iso()
    await db[DISCOVERY_RUNS].update_one(
        {"_id": object_id(run_id, "run id")}, {"$set": stamp_update(patch)}
    )


async def list_runs(limit: int = 25) -> list:
    docs = await db[DISCOVERY_RUNS].find(scope({})).sort("created_at", -1).to_list(limit)
    return [serialize_doc(doc) for doc in docs]

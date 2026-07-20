"""Lead persistence.

Writes to the host CRM's existing `leads` collection rather than a parallel
one, so an SDR lead appears on the CRM pipeline board, converts through
`run_won_automation` and shows up in search exactly like a manually created
lead. The only difference is `sdr_managed: True`, which marks the leads this
module is allowed to automate.

Note on `scope()`: it filters `deleted_at: None`, and in MongoDB that matches
documents where the field is null *or* absent - so the thousands of existing
leads written before this module existed are still returned. That behaviour is
load-bearing; do not "fix" it to `$exists`.
"""

from database import db, now_iso, serialize_doc, serialize_list
from sdr.domain import pipeline
from sdr.errors import NotFoundError, ValidationError
from sdr.repositories.base import object_id, paginate, scope, stamp_update

#: Fields the SDR module owns on a lead document. Everything else on `leads`
#: belongs to the host CRM and is not written by this module.
_SDR_FIELDS = (
    "sdr_company_id", "sdr_managed", "icp_profile_id", "score_version",
    "score_breakdown", "qualification_status", "disqualification_reason",
    "stage_entered_at", "previous_stage", "next_action_at", "next_action_type",
)


async def create_from_company(company: dict, *, icp_profile_id: str | None = None,
                              owner_id: str | None = None,
                              source: str = "ai_sdr") -> dict:
    """Create a CRM lead for a discovered company, or return the existing one.

    Idempotent on `sdr_company_id`: re-running discovery must not create a
    second lead for the same business, because that is how the same person
    ends up receiving the same pitch twice.
    """
    company_id = company.get("id") or str(company.get("_id"))
    existing = await db.leads.find_one(scope({"sdr_company_id": company_id}))
    if existing:
        return serialize_doc(existing)

    now = now_iso()
    doc = {
        # Host CRM fields - shape matches routers/crm.py exactly.
        "company": company.get("name"),
        "website": company.get("website_url"),
        "industry": company.get("industry"),
        "location": company.get("city"),
        "email": company.get("primary_email"),
        "phone": company.get("phone_e164"),
        "employees": company.get("employee_count"),
        "revenue": company.get("revenue_estimate"),
        "linkedin": company.get("linkedin_url"),
        "notes": "",
        "tags": ["ai-sdr"] + ([company["industry"]] if company.get("industry") else []),
        "stage": pipeline.PROSPECT,
        "priority": "medium",
        "source": source,
        "owner_id": owner_id,
        "score": 0,
        "custom_fields": {},
        "converted_client_id": None,
        "created_at": now,
        "updated_at": now,
        # SDR-owned fields.
        "sdr_company_id": company_id,
        "sdr_managed": True,
        "icp_profile_id": icp_profile_id,
        "qualification_status": "unqualified",
        "stage_entered_at": now,
        "previous_stage": None,
        "next_action_at": None,
        "next_action_type": None,
        "deleted_at": None,
    }
    result = await db.leads.insert_one(doc)

    # The host CRM writes an activity on every lead creation; matching that
    # keeps the lead timeline coherent across both modules.
    await db.lead_activities.insert_one({
        "lead_id": str(result.inserted_id),
        "type": "note",
        "content": f"Discovered by AI SDR via {company.get('discovery_source') or 'discovery'}",
        "created_by": owner_id or "ai_sdr",
        "created_at": now,
    })

    return serialize_doc(await db.leads.find_one({"_id": result.inserted_id}))


async def create_many_from_companies(companies: list, **kwargs) -> dict:
    created, skipped = [], 0
    for company in companies:
        before = await db.leads.find_one(scope({"sdr_company_id": company.get("id")}))
        lead = await create_from_company(company, **kwargs)
        if before:
            skipped += 1
        else:
            created.append(lead["id"])
    return {"created": len(created), "already_existed": skipped, "lead_ids": created}


async def list_leads(*, stage: str | None = None, qualification_status: str | None = None,
                     owner_id: str | None = None, search: str | None = None,
                     min_score: int | None = None, sdr_only: bool = True,
                     limit: int = 50, cursor: str | None = None) -> dict:
    query = {}
    if sdr_only:
        query["sdr_managed"] = True
    if stage:
        if not pipeline.is_valid_stage(stage):
            raise ValidationError(f"Unknown stage '{stage}'.")
        query["stage"] = stage
    if qualification_status:
        query["qualification_status"] = qualification_status
    if owner_id:
        query["owner_id"] = owner_id
    if min_score is not None:
        query["score"] = {"$gte": min_score}
    if search:
        query["company"] = {"$regex": search, "$options": "i"}
    return await paginate(
        "leads", scope(query), sort=("updated_at", -1), limit=limit, cursor=cursor
    )


async def get_lead(lead_id: str) -> dict:
    doc = await db.leads.find_one(scope({"_id": object_id(lead_id, "lead id")}))
    if not doc:
        raise NotFoundError("Lead not found")
    return serialize_doc(doc)


async def transition_stage(lead_id: str, to_stage: str, *, actor: str = "system",
                           actor_id: str | None = None, reason: str | None = None) -> dict:
    """Move a lead through the pipeline, validating against the state machine.

    Writes an activity and stamps `stage_entered_at` so time-in-stage
    analytics stay honest. Illegal moves raise rather than being silently
    coerced.
    """
    lead = await get_lead(lead_id)
    from_stage = lead.get("stage") or pipeline.PROSPECT

    pipeline.validate_transition(from_stage, to_stage, actor)
    if pipeline.requires_reason(to_stage) and not reason:
        raise ValidationError(f"Moving a lead to '{to_stage}' requires a reason.")

    now = now_iso()
    patch = {
        "stage": to_stage,
        "previous_stage": from_stage,
        "stage_entered_at": now,
    }
    if to_stage in (pipeline.LOST, pipeline.REJECTED):
        patch["lost_reason"] = reason
    if to_stage == pipeline.ARCHIVED:
        patch["next_action_at"] = None

    await db.leads.update_one(
        {"_id": object_id(lead_id, "lead id")}, {"$set": stamp_update(patch)}
    )

    overridden = pipeline.is_override(from_stage, to_stage)
    note = f"Stage {from_stage} -> {to_stage} by {actor}"
    if overridden:
        note += " (manual override)"
    if reason:
        note += f": {reason}"

    await db.lead_activities.insert_one({
        "lead_id": lead_id,
        "type": "stage_change",
        "content": note,
        "created_by": actor_id or actor,
        "created_at": now,
    })

    return await get_lead(lead_id)


async def apply_score(lead_id: str, scored: dict) -> dict:
    """Persist a scoring result and its explainable breakdown."""
    await db.leads.update_one(
        {"_id": object_id(lead_id, "lead id")},
        {"$set": stamp_update({
            "score": scored["score"],
            "score_version": scored["score_version"],
            "score_breakdown": scored["score_breakdown"],
        })},
    )
    return await get_lead(lead_id)


async def set_qualification(lead_id: str, status: str, reason: str | None = None) -> dict:
    valid = ("unqualified", "qualified", "disqualified", "needs_review")
    if status not in valid:
        raise ValidationError(f"Qualification status must be one of: {', '.join(valid)}")
    patch = {"qualification_status": status}
    if status == "disqualified":
        patch["disqualification_reason"] = reason
    await db.leads.update_one(
        {"_id": object_id(lead_id, "lead id")}, {"$set": stamp_update(patch)}
    )
    return await get_lead(lead_id)


async def soft_delete(lead_id: str) -> None:
    """Soft delete, SDR-managed leads only.

    The host CRM hard-deletes leads. This module does not, because an audit
    log entry pointing at a vanished lead is not an audit trail.
    """
    lead = await get_lead(lead_id)
    if not lead.get("sdr_managed"):
        raise ValidationError(
            "This lead is not managed by the AI SDR - delete it from the CRM instead."
        )
    await db.leads.update_one(
        {"_id": object_id(lead_id, "lead id")},
        {"$set": stamp_update({"deleted_at": now_iso()})},
    )


async def bulk_assign(lead_ids: list, owner_id: str) -> int:
    object_ids = [object_id(value, "lead id") for value in lead_ids]
    result = await db.leads.update_many(
        scope({"_id": {"$in": object_ids}}),
        {"$set": stamp_update({"owner_id": owner_id})},
    )
    return result.modified_count


async def activities(lead_id: str, limit: int = 100) -> list:
    docs = await db.lead_activities.find({"lead_id": lead_id}) \
        .sort("created_at", -1).to_list(limit)
    return serialize_list(docs)


async def count_by_stage(sdr_only: bool = True) -> dict:
    match = scope({"sdr_managed": True} if sdr_only else {})
    cursor = db.leads.aggregate([
        {"$match": match},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
    ])
    rows = await cursor.to_list(100)
    return {row["_id"]: row["count"] for row in rows if row["_id"]}

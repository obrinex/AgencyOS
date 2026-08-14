from datetime import datetime, timezone
from typing import Optional, List
import csv
import io
import re
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, Query, Request, UploadFile, File
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, require_staff, require_admin, log_audit
from automation_engine import run_won_automation
from lead_stages import CREATABLE_STAGES, PROSPECT, WON, is_terminal, is_valid, joined
from rate_limit import check_rate_limit

router = APIRouter(prefix="/api", tags=["crm"])

#: Every lead query in this router carries this. The AI SDR module soft-deletes
#: the leads it owns - it stamps `deleted_at` and keeps the row so its audit
#: trail does not point at a vanished document (sdr/repositories/leads.py) - and
#: filters it out of every one of its own reads. This router did not, so a lead
#: deleted in the SDR UI stayed on the pipeline board, stayed fetchable by id,
#: and stayed in the header count and the bulk-delete preview. The CRM was the
#: only surface in the application still showing them.
#:
#: `{"deleted_at": None}` matches documents where the field is null *or absent*,
#: which is what makes it safe on the leads written before either module
#: existed. Do not "fix" it to `$exists`.
NOT_DELETED = {"deleted_at": None}


def _live(query: dict | None = None) -> dict:
    """A lead query, scoped to leads that have not been soft-deleted."""
    return {**(query or {}), **NOT_DELETED}


class LeadCreate(BaseModel):
    company: str
    website: Optional[str] = None
    industry: Optional[str] = None
    employees: Optional[int] = None
    revenue: Optional[float] = None
    location: Optional[str] = None
    owner_id: Optional[str] = None
    source: Optional[str] = "manual"
    priority: Optional[str] = "medium"
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = []
    stage: Optional[str] = "prospect"
    custom_fields: Optional[dict] = {}


class LeadUpdate(BaseModel):
    company: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    employees: Optional[int] = None
    revenue: Optional[float] = None
    location: Optional[str] = None
    owner_id: Optional[str] = None
    source: Optional[str] = None
    priority: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    score: Optional[int] = None
    custom_fields: Optional[dict] = None


class ContactUpdate(BaseModel):
    """Every field optional, so a partial update does not have to resend the
    whole contact. `ContactCreate` requires `name`, which made changing only a
    phone number impossible without knowing the current name."""
    name: Optional[str] = None
    lead_id: Optional[str] = None
    client_id: Optional[str] = None
    company: Optional[str] = None
    position: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    timezone: Optional[str] = None
    birthday: Optional[str] = None
    notes: Optional[str] = None


class StagePatch(BaseModel):
    stage: str


class ActivityCreate(BaseModel):
    type: str
    content: str


class ContactCreate(BaseModel):
    name: str
    lead_id: Optional[str] = None
    client_id: Optional[str] = None
    company: Optional[str] = None
    position: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    timezone: Optional[str] = None
    birthday: Optional[str] = None
    notes: Optional[str] = None


@router.get("/leads")
async def list_leads(stage: Optional[str] = None, owner_id: Optional[str] = None,
                     search: Optional[str] = None,
                     limit: int = Query(default=500, ge=1, le=2000),
                     skip: int = Query(default=0, ge=0),
                     user: dict = Depends(require_staff)):
    """One page of leads, newest first.

    This used to be a bare `.to_list(1000)`: a hard cap that silently dropped
    lead 1001 with nothing in the response to say so. The board showed a subset
    and called it the pipeline. `limit`/`skip` make the boundary explicit, and
    the board pages until a short page comes back.
    """
    query = _live()
    if stage:
        query["stage"] = stage
    if owner_id:
        query["owner_id"] = owner_id
    if search:
        # Escaped: a company name containing regex metacharacters ("A+ Design",
        # "Smith & Co (UK)") must be matched literally, not compiled as a
        # pattern that errors or matches the wrong rows.
        query["company"] = {"$regex": re.escape(search), "$options": "i"}
    leads = await db.leads.find(query).sort("updated_at", -1) \
        .skip(skip).limit(limit).to_list(limit)
    return serialize_list(leads)


@router.post("/leads")
async def create_lead(payload: LeadCreate, user: dict = Depends(require_staff)):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    if doc.get("stage") not in CREATABLE_STAGES:
        raise HTTPException(status_code=400,
                            detail=f"Invalid stage. Valid: {joined(CREATABLE_STAGES)}")
    doc.update({"score": 0, "owner_id": doc.get("owner_id") or user["id"], "created_at": now, "updated_at": now, "converted_client_id": None, "deleted_at": None})
    res = await db.leads.insert_one(doc)
    await db.lead_activities.insert_one({"lead_id": str(res.inserted_id), "type": "note", "content": "Lead created", "created_by": user["id"], "created_at": now})
    await log_audit(user["id"], "create_lead", "lead", str(res.inserted_id))
    lead = await db.leads.find_one({"_id": res.inserted_id})
    return serialize_doc(lead)


#: Rows past this are refused rather than half-imported. Each row costs a
#: document plus an activity, and the whole request has to finish inside the
#: serverless function ceiling - a 50k-row paste used to time out partway,
#: leaving an unknown number of leads in and no way to tell which.
CSV_ROW_LIMIT = 5000

#: Cap on the "already in your pipeline" list in the response. The count is
#: always exact; only the names are truncated, so a 4000-row re-import does not
#: return a 4000-item error array.
CSV_REPORT_LIMIT = 20


@router.post("/leads/import-csv")
async def import_leads_csv(file: UploadFile = File(...), user: dict = Depends(require_staff)):
    """Import leads from a CSV, skipping companies already in the pipeline.

    Deduplicates, which it did not before: re-uploading the same file used to
    produce a second copy of every lead in it. The Lead Finder already deduped
    by name, so this was the only way into the pipeline that would silently
    double it.

    Matching is case-insensitive on company name against live leads only - a
    company whose old lead was lost or archived can legitimately come back.
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded CSV")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "company" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(status_code=400, detail="CSV must include a 'company' column")

    now = datetime.now(timezone.utc).isoformat()
    errors = []
    docs = []
    seen_in_file = set()
    duplicates = []

    # One pass over the existing pipeline rather than a query per row: at a few
    # thousand rows that is the difference between one round trip and a few
    # thousand of them.
    existing = {
        (doc.get("company") or "").strip().lower()
        for doc in await db.leads.find(_live(), {"company": 1}).to_list(None)
    }

    for i, raw_row in enumerate(reader, start=2):
        # Counts rows read, not rows kept: a file that is 20,000 duplicates
        # still costs 20,000 iterations, and the point of the cap is to bound
        # the work, not just the inserts.
        if i - 2 >= CSV_ROW_LIMIT:
            errors.append(
                f"Stopped at row {i}: this file exceeds the {CSV_ROW_LIMIT:,}-row "
                f"limit. Split it and import the parts separately."
            )
            break
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        company = row.get("company", "")
        if not company:
            errors.append(f"Row {i}: missing company name")
            continue

        key = company.lower()
        if key in existing or key in seen_in_file:
            duplicates.append(company)
            continue
        seen_in_file.add(key)

        stage = row.get("stage")
        try:
            doc = {
                "company": company,
                "website": row.get("website") or None,
                "industry": row.get("industry") or None,
                "employees": int(row["employees"]) if row.get("employees") else None,
                "revenue": float(row["revenue"]) if row.get("revenue") else None,
                "location": row.get("location") or None,
                "owner_id": user["id"],
                "source": row.get("source") or "csv_import",
                "priority": row.get("priority") or "medium",
                "email": row.get("email") or None,
                "phone": row.get("phone") or None,
                "linkedin": row.get("linkedin") or None,
                "notes": row.get("notes") or None,
                "tags": [],
                # An unrecognised stage falls back to prospect rather than
                # being written through: a typo'd stage is a lead that renders
                # in no column at all.
                "stage": stage if stage in CREATABLE_STAGES else PROSPECT,
                "custom_fields": {},
                "score": 0, "created_at": now, "updated_at": now,
                "converted_client_id": None, "deleted_at": None,
            }
        except ValueError as e:
            errors.append(f"Row {i}: invalid number format ({e})")
            continue
        docs.append(doc)

    imported = 0
    if docs:
        result = await db.leads.insert_many(docs)
        imported = len(result.inserted_ids)
        await db.lead_activities.insert_many([
            {"lead_id": str(lead_id), "type": "note",
             "content": "Lead imported via CSV", "created_by": user["id"],
             "created_at": now}
            for lead_id in result.inserted_ids
        ])

    if duplicates:
        shown = ", ".join(duplicates[:CSV_REPORT_LIMIT])
        more = len(duplicates) - CSV_REPORT_LIMIT
        errors.append(
            f"Skipped {len(duplicates)} already in your pipeline: {shown}"
            + (f" and {more} more" if more > 0 else "")
        )

    await log_audit(user["id"], "import_leads_csv", "lead", f"{imported} leads")
    return {"imported": imported, "skipped_duplicates": len(duplicates), "errors": errors}


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str, user: dict = Depends(require_staff)):
    lead = await db.leads.find_one(_live({"_id": to_object_id(lead_id)}))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return serialize_doc(lead)


@router.put("/leads/{lead_id}")
async def update_lead(lead_id: str, payload: LeadUpdate, user: dict = Depends(require_staff)):
    """Update the fields the caller actually sent.

    `exclude_unset`, not a `is not None` filter. The old version dropped every
    null, which meant no field could ever be cleared through the API - removing
    a stale email address or phone number was impossible from any surface in
    the application. Omitting a field still leaves it untouched; sending it as
    null now clears it, which is what a caller sending null means.
    """
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.leads.update_one(_live({"_id": to_object_id(lead_id)}),
                                       {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead = await db.leads.find_one({"_id": to_object_id(lead_id)})
    return serialize_doc(lead)


#: Collections the removed outreach engine wrote, still cleaned up here.
#:
#: The engine is gone; its rows are not. They were left in the database
#: deliberately (the removal did not touch data), so a lead delete still has to
#: take its outreach state with it - otherwise a deleted lead leaves records
#: pointing at nothing, and the unique (campaign, lead) index on enrollments
#: would block that company from ever being enrolled again by a replacement.
#:
#: Names are literals rather than an import because the module that defined
#: them no longer exists. When the new agent system lands, point these at
#: whatever it calls its own tables.
_OUTREACH_ENROLLMENTS = "sdr_enrollments"
_OUTREACH_MESSAGES = "sdr_messages"
_OUTREACH_INBOUND = "sdr_inbound_messages"


async def cascade_lead_deletes(lead_ids: list) -> dict:
    """Remove everything that hangs off a set of deleted leads.

    Deleting a lead used to leave its `lead_activities` behind, and its outreach
    state too.

    Contacts are the exception. A contact carrying a `client_id` was promoted
    when the deal closed and belongs to a live client now; only the ones that
    belong to no client go.
    """
    scoped = {"lead_id": {"$in": lead_ids}}

    activities = await db.lead_activities.delete_many(scoped)
    contacts = await db.contacts.delete_many(orphaned_contacts_query(lead_ids))
    enrollments = await db[_OUTREACH_ENROLLMENTS].delete_many(scoped)

    # Only messages that never left the building are deleted. Anything that
    # reached a real person - sent, delivered, bounced, complained - stays, with
    # its dead lead pointer cleared. That record is the evidence behind the
    # suppression and consent trail (`backend/suppression.py`), and deleting a
    # lead is not grounds for forgetting that we emailed someone.
    unsent = {**scoped, "status": {"$in": ["awaiting_approval", "approved",
                                           "cancelled", "rejected", "failed"]}}
    messages = await db[_OUTREACH_MESSAGES].delete_many(unsent)
    await db[_OUTREACH_MESSAGES].update_many(scoped, {"$set": {"lead_id": None,
                                                               "lead_deleted": True}})

    # Same reasoning for inbound: a reply is a real thing a real person sent,
    # and the inbox is the record of it.
    await db[_OUTREACH_INBOUND].update_many(scoped, {"$set": {"lead_id": None,
                                                              "lead_deleted": True}})

    return {
        "activities": activities.deleted_count,
        "contacts": contacts.deleted_count,
        "enrollments": enrollments.deleted_count,
        "messages": messages.deleted_count,
    }


@router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, request: Request, user: dict = Depends(require_staff)):
    result = await db.leads.delete_one(_live({"_id": to_object_id(lead_id)}))
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")
    cascaded = await cascade_lead_deletes([lead_id])
    await log_audit(user["id"], "delete_lead", "lead", lead_id, request)
    return {"message": "Lead deleted", "deleted": cascaded}


class BulkDeleteLeads(BaseModel):
    confirm: str
    include_won: bool = False


#: The phrase the operator must type. Deliberately not "OK" or "yes" - those
#: are muscle memory.
BULK_DELETE_PHRASE = "DELETE"


def bulk_delete_query(include_won: bool) -> dict:
    """Which leads a bulk delete matches.

    Won leads are excluded unless explicitly asked for. A won lead has already
    produced a client, a project and an invoice through `run_won_automation`;
    deleting it undoes none of that, it just removes the deal those records
    point back to.
    """
    return _live() if include_won else _live({"stage": {"$ne": WON}})


def orphaned_contacts_query(lead_ids: list) -> dict:
    """Contacts that belong to these leads and to no client.

    A contact carrying a `client_id` was promoted when the deal closed and
    belongs to a live client now - it outlives the lead it arrived on.
    """
    return {
        "lead_id": {"$in": lead_ids},
        "$or": [{"client_id": None}, {"client_id": {"$exists": False}}],
    }


class DeleteSelectedLeads(BaseModel):
    lead_ids: List[str]


@router.post("/leads/delete-selected")
async def delete_selected_leads(payload: DeleteSelectedLeads, request: Request,
                                user: dict = Depends(require_staff)):
    """Delete a hand-picked set of leads.

    Staff-level and no typed phrase, unlike delete-all: picking six leads out
    of a board *is* the confirmation, and the count is shown before the click.
    Making the everyday action as heavy as the nuclear one only trains people
    to reach for the nuclear one.

    Won leads are not filtered out here. Delete-all excludes them because
    "everything" is a blunt instrument and nobody pictures the won column when
    they say it - but choosing one by hand is unambiguous. The cascade below
    still protects contacts that belong to a live client.
    """
    if not payload.lead_ids:
        raise HTTPException(status_code=400, detail="No leads selected.")
    if len(payload.lead_ids) > 500:
        raise HTTPException(status_code=400, detail="Select at most 500 leads at a time.")

    object_ids = [to_object_id(lead_id) for lead_id in payload.lead_ids]
    found = [str(d["_id"]) for d in
             await db.leads.find(_live({"_id": {"$in": object_ids}}), {"_id": 1}).to_list(None)]
    if not found:
        raise HTTPException(status_code=404, detail="None of those leads exist.")

    leads = await db.leads.delete_many(_live({"_id": {"$in": object_ids}}))
    cascaded = await cascade_lead_deletes(found)

    await log_audit(user["id"], "delete_selected_leads", "lead",
                    f"{leads.deleted_count} leads", request)
    return {
        "message": f"Deleted {leads.deleted_count} lead{'s' if leads.deleted_count != 1 else ''}.",
        "deleted": {"leads": leads.deleted_count, **cascaded},
    }


@router.get("/leads/bulk-delete/preview")
async def preview_bulk_delete(include_won: bool = False, user: dict = Depends(require_admin)):
    """What a bulk delete would remove, counted before anything is destroyed.

    The dialog shows these numbers. Deleting an unknown quantity is how people
    discover they had 200 leads and meant to clear 3.
    """
    query = bulk_delete_query(include_won)
    lead_ids = [str(d["_id"]) for d in await db.leads.find(query, {"_id": 1}).to_list(None)]
    return {
        "leads": len(lead_ids),
        "activities": await db.lead_activities.count_documents({"lead_id": {"$in": lead_ids}}),
        "contacts": await db.contacts.count_documents({"lead_id": {"$in": lead_ids}}),
        # Named separately in the dialog: stopping live outreach mid-sequence is
        # a different kind of consequence from deleting a row, and the operator
        # should see it before they type DELETE.
        "enrollments": await db[_OUTREACH_ENROLLMENTS].count_documents(
            {"lead_id": {"$in": lead_ids}, "status": "active"}),
        "won_excluded": 0 if include_won else await db.leads.count_documents(_live({"stage": WON})),
        "total_leads": await db.leads.count_documents(_live()),
    }


@router.post("/leads/bulk-delete")
async def bulk_delete_leads(payload: BulkDeleteLeads, request: Request,
                            user: dict = Depends(require_admin)):
    """Delete every lead in the pipeline. Irreversible, admin-only, audited.

    Three deliberate constraints, none of them decoration:

    1. **Won leads are excluded by default.** A won lead carries
       `converted_client_id` and has already produced a client, a project and
       an invoice via `run_won_automation`. Deleting it does not undo any of
       that - it orphans them, leaving an invoice whose originating deal no
       longer exists. Removing them is possible but has to be asked for.

    2. **It cascades.** Single-lead delete leaves `lead_activities` and
       `contacts` behind; at one row that is untidy, at several hundred it is
       a junk table nobody knows to clean.

    3. **The typed phrase must match.** A misclick cannot reach this, and the
       word is DELETE rather than OK so it cannot be muscle-memory.
    """
    if payload.confirm != BULK_DELETE_PHRASE:
        raise HTTPException(status_code=400, detail=f"Type {BULK_DELETE_PHRASE} to confirm.")

    query = bulk_delete_query(payload.include_won)
    lead_ids = [str(d["_id"]) for d in await db.leads.find(query, {"_id": 1}).to_list(None)]
    if not lead_ids:
        return {"message": "Nothing to delete.",
                "deleted": {"leads": 0, "activities": 0, "contacts": 0,
                            "enrollments": 0, "messages": 0}}

    leads = await db.leads.delete_many(query)
    cascaded = await cascade_lead_deletes(lead_ids)

    await log_audit(user["id"], "bulk_delete_leads", "lead",
                    f"{leads.deleted_count} leads", request)

    return {
        "message": f"Deleted {leads.deleted_count} leads.",
        "deleted": {"leads": leads.deleted_count, **cascaded},
    }


@router.patch("/leads/{lead_id}/stage")
async def patch_stage(lead_id: str, payload: StagePatch, user: dict = Depends(require_staff)):
    """Move a lead to a different stage.

    `won` is a one-way door. Reaching it runs `run_won_automation`, which
    creates a client, an onboarding project, four tasks and a draft invoice.
    Moving back out strands all of those - the client stays, the invoice stays,
    and the deal they point back to no longer claims to exist - and moving in
    again mints a *second* full set, because the automation keys off the
    transition rather than off the lead. The SDR module's state machine has
    always refused to leave a terminal stage; this endpoint was the way around
    it, and the dashboard's own stage dropdown was the way in.
    """
    if not is_valid(payload.stage):
        raise HTTPException(status_code=400,
                            detail=f"Invalid stage. Valid: {joined()}")
    lead = await db.leads.find_one(_live({"_id": to_object_id(lead_id)}))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    old_stage = lead.get("stage")
    if payload.stage == old_stage:
        return {"lead": serialize_doc(lead), "automation": None}

    if is_terminal(old_stage):
        raise HTTPException(
            status_code=409,
            detail=(
                f"This deal is already marked {old_stage} and cannot be moved back. "
                "Winning it created a client, a project and a draft invoice; "
                "reopening the lead would leave those with no deal behind them. "
                "Delete the client if it was won by mistake."
            ),
        )

    now = datetime.now(timezone.utc).isoformat()
    await db.leads.update_one(
        {"_id": lead["_id"]},
        {"$set": {"stage": payload.stage, "previous_stage": old_stage,
                  "stage_entered_at": now, "updated_at": now}},
    )
    await db.lead_activities.insert_one({"lead_id": lead_id, "type": "stage_change", "content": f"Stage changed from {old_stage} to {payload.stage}", "created_by": user["id"], "created_at": now})

    automation_result = None
    if payload.stage == WON:
        lead["stage"] = WON
        lead["id"] = lead_id
        automation_result = await run_won_automation(lead, user["id"])

    updated = await db.leads.find_one({"_id": lead["_id"]})
    return {"lead": serialize_doc(updated), "automation": automation_result}


@router.get("/leads/{lead_id}/activities")
async def get_activities(lead_id: str, user: dict = Depends(require_staff)):
    activities = await db.lead_activities.find({"lead_id": lead_id}).sort("created_at", -1).to_list(500)
    return serialize_list(activities)


@router.post("/leads/{lead_id}/activities")
async def add_activity(lead_id: str, payload: ActivityCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc.update({"lead_id": lead_id, "created_by": user["id"], "created_at": datetime.now(timezone.utc).isoformat()})
    res = await db.lead_activities.insert_one(doc)
    activity = await db.lead_activities.find_one({"_id": res.inserted_id})
    return serialize_doc(activity)


#: Unauthenticated, so the ceiling is per-IP and deliberately low. A real
#: integration posting a form submission or a Zapier hook is nowhere near 30
#: leads an hour from one address; a script filling the pipeline with junk is.
WEBHOOK_RATE_LIMIT = 30
WEBHOOK_RATE_WINDOW_SECONDS = 3600


@router.post("/webhooks/lead-capture")
async def webhook_lead_capture(payload: LeadCreate, request: Request):
    """Public lead capture. No authentication, so nothing here is trusted.

    Three things the caller does not get to decide, all of which it could
    before:

    - **`stage`.** This endpoint took whatever string arrived. Posting
      `stage: "won"` produced a deal sitting in the won column that never ran
      the won automation - a win with no client, no project and no invoice
      behind it, inflating the conversion rate on every dashboard that reads
      the funnel. Posting a stage nobody recognised produced a lead the board
      renders in no column at all. Inbound leads start at prospect, full stop.
    - **`owner_id`.** Assigning a lead to a named staff member from outside is
      not something a public endpoint should be able to do.
    - **`score`.** Never came from the payload, but pinning it here keeps the
      shape identical to every other creation path.
    """
    await check_rate_limit(request, scope="lead_capture",
                           limit=WEBHOOK_RATE_LIMIT,
                           window_seconds=WEBHOOK_RATE_WINDOW_SECONDS,
                           detail="Too many submissions. Try again later.")

    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({
        "score": 0,
        "stage": PROSPECT,
        "owner_id": None,
        "source": doc.get("source") or "webhook",
        "created_at": now, "updated_at": now,
        "converted_client_id": None, "deleted_at": None,
    })
    res = await db.leads.insert_one(doc)
    await db.lead_activities.insert_one({"lead_id": str(res.inserted_id), "type": "note", "content": "Lead captured via webhook", "created_by": None, "created_at": now})
    return {"message": "Lead created", "id": str(res.inserted_id)}


# ---------------- Contacts ----------------

@router.get("/contacts")
async def list_contacts(lead_id: Optional[str] = None, client_id: Optional[str] = None,
                        limit: int = Query(default=500, ge=1, le=2000),
                        skip: int = Query(default=0, ge=0),
                        user: dict = Depends(require_staff)):
    query = {}
    if lead_id:
        query["lead_id"] = lead_id
    if client_id:
        query["client_id"] = client_id
    contacts = await db.contacts.find(query).sort("created_at", -1) \
        .skip(skip).limit(limit).to_list(limit)
    return serialize_list(contacts)


@router.post("/contacts")
async def create_contact(payload: ContactCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.contacts.insert_one(doc)
    contact = await db.contacts.find_one({"_id": res.inserted_id})
    return serialize_doc(contact)


@router.put("/contacts/{contact_id}")
async def update_contact(contact_id: str, payload: ContactUpdate, user: dict = Depends(require_staff)):
    # exclude_unset, so an explicit null clears a field instead of being
    # dropped. See update_lead for why.
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    result = await db.contacts.update_one({"_id": to_object_id(contact_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contact not found")
    contact = await db.contacts.find_one({"_id": to_object_id(contact_id)})
    return serialize_doc(contact)


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, user: dict = Depends(require_staff)):
    await db.contacts.delete_one({"_id": to_object_id(contact_id)})
    return {"message": "Contact deleted"}

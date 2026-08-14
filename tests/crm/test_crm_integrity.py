"""The CRM's own guarantees, against an in-memory database.

Everything here covers a way the subsystems sharing the `leads` collection used
to disagree with each other about the same rows.

Several of these were written while an AI SDR module was the other writer. That
module has since been deleted, but its *data* was left in place and the CRM's
delete cascade still has to clean up after it - so the coverage stays, pointed
at the collection names rather than at an import.
"""

import io
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "crm_test")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-hmac")

USER = {"id": "u-test", "role": "admin"}

ENROLLMENTS = "sdr_enrollments"
MESSAGES = "sdr_messages"


@pytest_asyncio.fixture
async def db(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    database = client["crm_test"]

    import auth_utils
    import automation_engine
    import database as database_module
    import rate_limit
    import whatsapp_service
    from routers import crm, dashboard, leadform

    monkeypatch.setattr(database_module, "db", database)
    for module in (crm, dashboard, leadform, automation_engine, rate_limit,
                   auth_utils, whatsapp_service):
        if hasattr(module, "db"):
            monkeypatch.setattr(module, "db", database)
    return database


async def _make_lead(db, **overrides) -> str:
    doc = {
        "company": "Acme", "stage": "prospect", "revenue": 50000,
        "email": "hi@acme.example", "owner_id": USER["id"],
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
        "converted_client_id": None, "deleted_at": None,
    }
    doc.update(overrides)
    result = await db.leads.insert_one(doc)
    return str(result.inserted_id)


async def _soft_delete(db, lead_id):
    """What a soft delete looks like on the wire.

    Previously `sdr.repositories.leads.soft_delete()`. Stamped directly now
    that the module is gone - the CRM's job is to respect the marker, wherever
    it came from, and rows carrying it are still in the database.
    """
    from database import to_object_id

    await db.leads.update_one({"_id": to_object_id(lead_id)},
                              {"$set": {"deleted_at": "2026-08-02T00:00:00+00:00"}})


async def _list_leads(**kwargs):
    """The endpoint's defaults are FastAPI `Query` objects, which only become
    values when a request goes through the router."""
    from routers import crm

    return await crm.list_leads(user=USER, limit=500, skip=0, **kwargs)


# --- One stage vocabulary -----------------------------------------------------

def test_every_stage_the_board_renders_is_a_stage_the_api_accepts():
    """The board offered `interested` and the API rejected it with a 400, so
    dragging a card into that column failed. The frontend map and this list
    have to hold the same keys or one of them is lying to the user."""
    import re

    import lead_stages

    config = (Path(__file__).resolve().parents[2]
              / "frontend/src/lib/statusConfig.js").read_text(encoding="utf-8")
    block = config.split("export const STAGE_CONFIG = {")[1].split("};")[0]
    rendered = re.findall(r"^\s{2}(\w+):", block, re.MULTILINE)

    assert rendered == lead_stages.STAGES, (
        "frontend/src/lib/statusConfig.js and backend/lead_stages.py disagree. "
        "A stage in one and not the other is either a column the API rejects "
        "or a lead that renders nowhere."
    )


def test_the_frontend_and_backend_agree_on_which_stages_are_terminal():
    import re

    import lead_stages

    config = (Path(__file__).resolve().parents[2]
              / "frontend/src/lib/statusConfig.js").read_text(encoding="utf-8")
    block = config.split("export const TERMINAL_STAGES = [")[1].split("]")[0]
    assert re.findall(r'"(\w+)"', block) == list(lead_stages.TERMINAL_STAGES)


def test_no_lead_can_be_created_directly_as_won():
    """Creating one straight into won skips run_won_automation entirely - a
    win with no client, project or invoice behind it."""
    from lead_stages import CREATABLE_STAGES, WON

    assert WON not in CREATABLE_STAGES


# --- Soft-deleted leads stay deleted ------------------------------------------

@pytest.mark.asyncio
async def test_a_soft_deleted_lead_is_off_the_board(db):
    lead_id = await _make_lead(db)
    await _soft_delete(db, lead_id)

    assert await _list_leads() == []


@pytest.mark.asyncio
async def test_a_soft_deleted_lead_is_a_404_not_a_record(db):
    from fastapi import HTTPException
    from routers import crm

    lead_id = await _make_lead(db)
    await _soft_delete(db, lead_id)

    with pytest.raises(HTTPException) as exc:
        await crm.get_lead(lead_id, user=USER)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_the_dashboard_funnel_does_not_count_deleted_leads(db):
    from routers import dashboard

    await _make_lead(db, company="Live")
    doomed = await _make_lead(db, company="Deleted")
    await _soft_delete(db, doomed)

    stats = await dashboard.dashboard_stats(user=USER)
    assert stats["total_leads"] == 1
    assert sum(row["count"] for row in stats["sales_funnel"]) == 1


# --- Won is a one-way door ----------------------------------------------------

@pytest.mark.asyncio
async def test_a_won_deal_cannot_be_reopened(db):
    """Winning it created a client, a project and a draft invoice. Moving back
    out strands them; moving in again used to mint a second set of each."""
    from fastapi import HTTPException
    from routers import crm

    lead_id = await _make_lead(db, stage="won", converted_client_id="c1")

    with pytest.raises(HTTPException) as exc:
        await crm.patch_stage(lead_id, crm.StagePatch(stage="negotiation"), user=USER)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_winning_a_deal_twice_creates_one_client_not_two(db):
    """The old guard was on the stage *transition*, which any re-run or
    corrected stage could get around. Idempotency belongs in the operation."""
    from automation_engine import run_won_automation

    lead_id = await _make_lead(db)
    lead = await db.leads.find_one({"company": "Acme"})
    lead["id"] = lead_id

    first = await run_won_automation({**lead, "stage": "won"}, USER["id"])
    refreshed = await db.leads.find_one({"_id": lead["_id"]})
    second = await run_won_automation({**refreshed, "id": lead_id, "stage": "won"},
                                      USER["id"])

    assert second["already_ran"] is True
    assert second["client_id"] == first["client_id"]
    assert await db.clients.count_documents({}) == 1
    assert await db.projects.count_documents({}) == 1
    assert await db.invoices.count_documents({}) == 1


@pytest.mark.asyncio
async def test_reaching_won_still_runs_the_automation(db):
    from routers import crm

    lead_id = await _make_lead(db, stage="negotiation")
    result = await crm.patch_stage(lead_id, crm.StagePatch(stage="won"), user=USER)

    assert result["automation"]["client_id"]
    assert await db.clients.count_documents({}) == 1


# --- Deleting a lead takes its outreach state with it -------------------------

@pytest.mark.asyncio
async def test_deleting_a_lead_clears_its_enrollments(db):
    """The engine that wrote these is gone, but its rows are not. A live
    enrollment left behind still blocks that company from being enrolled again
    by whatever replaces it - the unique (campaign, lead) index sees to that."""
    from routers import crm

    lead_id = await _make_lead(db)
    await db[ENROLLMENTS].insert_one({"lead_id": lead_id, "campaign_id": "camp1",
                                      "status": "active"})

    await crm.delete_lead(lead_id, request=None, user=USER)

    assert await db[ENROLLMENTS].count_documents({}) == 0


@pytest.mark.asyncio
async def test_an_email_that_reached_a_real_person_survives_the_delete(db):
    """A sent message is the evidence behind the suppression and consent
    trail. Deleting a lead is not grounds for forgetting we emailed someone -
    the pointer is cleared, the record stays."""
    from routers import crm

    lead_id = await _make_lead(db)
    await db[MESSAGES].insert_one({"lead_id": lead_id, "status": "sent",
                                   "to_email": "hi@acme.example"})
    await db[MESSAGES].insert_one({"lead_id": lead_id, "status": "awaiting_approval",
                                   "to_email": "hi@acme.example"})

    await crm.delete_lead(lead_id, request=None, user=USER)

    remaining = await db[MESSAGES].find({}).to_list(None)
    assert [m["status"] for m in remaining] == ["sent"]
    assert remaining[0]["lead_id"] is None
    assert remaining[0]["lead_deleted"] is True


@pytest.mark.asyncio
async def test_a_contact_promoted_to_a_client_survives_its_lead(db):
    from routers import crm

    lead_id = await _make_lead(db)
    await db.contacts.insert_one({"lead_id": lead_id, "client_id": "c1", "name": "Real customer"})
    await db.contacts.insert_one({"lead_id": lead_id, "client_id": None, "name": "Just a lead"})

    await crm.delete_lead(lead_id, request=None, user=USER)

    survivors = [c["name"] for c in await db.contacts.find({}).to_list(None)]
    assert survivors == ["Real customer"]


# --- The public endpoints -----------------------------------------------------

@pytest.mark.asyncio
async def test_the_capture_webhook_cannot_inject_a_won_deal(db):
    """Unauthenticated. Posting stage=won produced a deal in the won column
    that never ran the automation - a win with nothing behind it, inflating
    the conversion rate on every dashboard that reads the funnel."""
    from routers import crm

    await crm.webhook_lead_capture(
        crm.LeadCreate(company="Injected", stage="won", owner_id="someone-else"),
        request=None,
    )

    lead = await db.leads.find_one({"company": "Injected"})
    assert lead["stage"] == "prospect"
    assert lead["owner_id"] is None
    assert await db.clients.count_documents({}) == 0


@pytest.mark.asyncio
async def test_the_capture_webhook_is_throttled(db):
    from fastapi import HTTPException
    from routers import crm

    for n in range(crm.WEBHOOK_RATE_LIMIT):
        await crm.webhook_lead_capture(crm.LeadCreate(company=f"Co {n}"), request=None)

    with pytest.raises(HTTPException) as exc:
        await crm.webhook_lead_capture(crm.LeadCreate(company="One too many"), request=None)
    assert exc.value.status_code == 429


#: `.test` is a reserved TLD that pydantic's EmailStr refuses outright, and the
#: lead form validates its input. Real-looking address, nobody's real inbox.
SUBMITTER = "dev@example.com"


@pytest_asyncio.fixture
async def quiet_form(db, monkeypatch):
    """A live form with the outbound side stubbed.

    The WhatsApp notify and the background AI draft are exactly the two things
    a submission costs money for, so they are the two the test must not fire.
    """
    import whatsapp_service

    async def _silent(*args, **kwargs):
        return None

    monkeypatch.setattr(whatsapp_service, "notify_admin", _silent)
    await db.leadform_settings.insert_one({"key": "main", "slug": "abc",
                                           "enabled": True})
    return db


@pytest.mark.asyncio
async def test_the_lead_form_does_not_bill_twice_for_one_person(quiet_form):
    """One submission writes three documents, notifies every admin, sends a
    WhatsApp message and spends an LLM call. Someone clicking submit twice
    because nothing visibly happened must not buy a second round of that."""
    from routers import leadform

    payload = leadform.LeadFormSubmit(name="Dev", email=SUBMITTER, company="Acme")
    first = await leadform.public_leadform_submit("abc", payload, request=None)
    second = await leadform.public_leadform_submit("abc", payload, request=None)

    assert await quiet_form.leads.count_documents({}) == 1
    # Recorded against the existing lead rather than dropped, and the reply is
    # identical - a submitter must not be able to tell from the response
    # whether they are already in the CRM.
    assert await quiet_form.lead_activities.count_documents({}) == 2
    assert first == second


@pytest.mark.asyncio
async def test_the_lead_form_is_throttled_per_address(quiet_form):
    from fastapi import HTTPException
    from routers import leadform

    # Aged out of the dedupe window, so each submission is a genuinely new
    # lead and it is the throttle being tested rather than the deduplication.
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    for n in range(leadform.FORM_EMAIL_RATE_LIMIT):
        await leadform.public_leadform_submit(
            "abc",
            leadform.LeadFormSubmit(name="Dev", email=SUBMITTER, company=f"Acme {n}"),
            request=None,
        )
        await quiet_form.leads.update_many({}, {"$set": {"created_at": old}})

    with pytest.raises(HTTPException) as exc:
        await leadform.public_leadform_submit(
            "abc",
            leadform.LeadFormSubmit(name="Dev", email=SUBMITTER, company="Again"),
            request=None,
        )
    assert exc.value.status_code == 429


# --- CSV import ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_importing_the_same_csv_twice_does_not_double_the_pipeline(db):
    from fastapi import UploadFile
    from routers import crm

    def upload():
        return UploadFile(filename="leads.csv",
                          file=io.BytesIO(b"company,email\nAcme,hi@acme.example\n"))

    first = await crm.import_leads_csv(file=upload(), user=USER)
    second = await crm.import_leads_csv(file=upload(), user=USER)

    assert first["imported"] == 1
    assert second["imported"] == 0
    assert second["skipped_duplicates"] == 1
    assert await db.leads.count_documents({}) == 1


@pytest.mark.asyncio
async def test_an_unrecognised_stage_in_a_csv_falls_back_to_prospect(db):
    """A typo'd stage is a lead that renders in no column at all."""
    from fastapi import UploadFile
    from routers import crm

    await crm.import_leads_csv(
        file=UploadFile(filename="leads.csv",
                        file=io.BytesIO(b"company,stage\nAcme,definitely-not-a-stage\n")),
        user=USER,
    )
    assert (await db.leads.find_one({"company": "Acme"}))["stage"] == "prospect"


# --- Partial updates ----------------------------------------------------------

@pytest.mark.asyncio
async def test_a_field_can_be_cleared(db):
    """The update dropped every null, so no field could be emptied through the
    API - removing a stale email address was impossible from any surface."""
    from routers import crm

    lead_id = await _make_lead(db, email="stale@acme.example")
    updated = await crm.update_lead(lead_id, crm.LeadUpdate(email=None), user=USER)
    assert updated["email"] is None


@pytest.mark.asyncio
async def test_an_omitted_field_is_left_alone(db):
    from routers import crm

    lead_id = await _make_lead(db, email="keep@acme.example")
    updated = await crm.update_lead(lead_id, crm.LeadUpdate(company="Renamed"), user=USER)
    assert updated["company"] == "Renamed"
    assert updated["email"] == "keep@acme.example"


# --- Malformed ids ------------------------------------------------------------

def test_a_malformed_id_is_a_bad_request_not_a_server_error():
    """Nothing caught the bare ValueError this used to raise, so every route
    taking an id answered 500 and logged a stack trace for a typo'd URL."""
    from database import InvalidIdError, to_object_id

    with pytest.raises(InvalidIdError):
        to_object_id("not-an-object-id")

    # Still a ValueError: callers that predate the typed error catch that.
    assert issubclass(InvalidIdError, ValueError)

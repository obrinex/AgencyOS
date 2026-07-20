"""Integration tests for the repository + service layer, against a real-ish DB.

Everything else in tests/sdr is pure-domain. This file exercises the parts
that actually touch Mongo: upsert-with-merge, dedupe against storage, lead
creation, pagination and the CSV import path end-to-end.

Uses mongomock_motor rather than a live server so CI needs no database.
Caveat worth stating: mongomock does not enforce unique indexes, so the
uniqueness of `dedupe_key` is not proven here - the application-level dedupe
is what these tests cover. The index is the backstop for races, and only a
real MongoDB will demonstrate it.

`database.py` reads os.environ["MONGO_URL"] at import time, so the env vars
and the client patch both have to be in place before anything imports it.
"""

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "sdr_test")


@pytest_asyncio.fixture
async def db(monkeypatch):
    """A fresh in-memory database, with every module that holds a `db`
    reference repointed at it."""
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    database = client["sdr_test"]

    import database as database_module
    monkeypatch.setattr(database_module, "db", database)

    # These modules did `from database import db`, so they hold their own
    # reference to the original object and need patching individually.
    from sdr.repositories import base, companies, leads, overview, settings
    from sdr.services import discovery
    for module in (base, companies, leads, overview, settings, discovery):
        if hasattr(module, "db"):
            monkeypatch.setattr(module, "db", database)

    return database


USER = {"id": "user-1", "role": "admin"}


def company(name, **overrides):
    base_record = {
        "name": name,
        "city": "Pune",
        "country_code": "IN",
        "industry": "dental",
        "discovery_source": "osm_overpass",
    }
    base_record.update(overrides)
    return base_record


# --- Upsert and dedupe against storage ----------------------------------------

@pytest.mark.asyncio
async def test_inserts_new_companies(db):
    from sdr.repositories import companies as repo

    result = await repo.upsert_many([
        company("Acme Dental", domain="acme.in"),
        company("Zenith Motors", domain="zenith.in", industry="car_repair"),
    ])
    assert result["inserted"] == 2
    assert await repo.count_companies() == 2


@pytest.mark.asyncio
async def test_rerunning_the_same_discovery_does_not_duplicate(db):
    """The behaviour that stops one business being pitched twice."""
    from sdr.repositories import companies as repo

    records = [company("Acme Dental", domain="https://www.acme.in")]
    await repo.upsert_many(records)
    second = await repo.upsert_many(records)

    assert second["inserted"] == 0
    assert await repo.count_companies() == 1


@pytest.mark.asyncio
async def test_a_second_source_merges_rather_than_duplicating(db):
    from sdr.repositories import companies as repo

    await repo.upsert_many([company("Acme Dental Pvt Ltd", domain="acme.in")])
    result = await repo.upsert_many([
        company("Acme Dental", domain="www.acme.in",
                primary_email="hi@acme.in", google_rating=4.6,
                discovery_source="google_places"),
    ])

    assert result["merged"] == 1
    assert await repo.count_companies() == 1

    listed = await repo.list_companies()
    stored = listed["items"][0]
    assert stored["primary_email"] == "hi@acme.in"
    assert stored["google_rating"] == 4.6


@pytest.mark.asyncio
async def test_verified_email_survives_a_later_unverified_write(db):
    from sdr.repositories import companies as repo

    await repo.upsert_many([
        company("Acme", domain="acme.in", primary_email="real@acme.in",
                email_verification_status="valid", discovery_source="manual"),
    ])
    await repo.upsert_many([
        company("Acme", domain="acme.in", primary_email="scraped@acme.in",
                discovery_source="osm_overpass"),
    ])

    stored = (await repo.list_companies())["items"][0]
    assert stored["primary_email"] == "real@acme.in"


@pytest.mark.asyncio
async def test_normalisation_is_applied_on_write(db):
    from sdr.repositories import companies as repo

    await repo.upsert_many([
        company("Acme Dental Pvt. Ltd.",
                domain="HTTPS://WWW.Acme.in/contact?utm=x",
                phone_e164="020-1234-5678"),
    ])
    stored = (await repo.list_companies())["items"][0]

    assert stored["domain"] == "acme.in"
    assert stored["name_normalized"] == "acme dental"
    assert stored["phone_e164"] == "+912012345678"
    assert stored["dedupe_key"] == "d:acme.in"
    assert stored["timezone"]  # resolved from the country registry


@pytest.mark.asyncio
async def test_data_quality_score_reflects_completeness(db):
    from sdr.repositories import companies as repo

    await repo.upsert_many([company("Sparse")])
    await repo.upsert_many([
        company("Complete", domain="complete.in", primary_email="a@complete.in",
                phone_e164="+912012345678", description="A clinic",
                google_rating=4.5, employee_count=10),
    ])
    listed = await repo.list_companies()
    by_name = {c["name"]: c for c in listed["items"]}
    assert by_name["Complete"]["data_quality_score"] > by_name["Sparse"]["data_quality_score"]


# --- The Phase 2 gate: a real bulk import -------------------------------------

@pytest.mark.asyncio
async def test_imports_a_thousand_rows_and_dedupes_them(db):
    """The Phase 2 gate: import 1,000 leads, dedupe, filter, view.

    The fixture deliberately contains 200 exact duplicates, so a correct run
    stores 1,000 companies from 1,200 input rows.
    """
    from sdr.providers import csv_import
    from sdr.repositories import companies as repo
    from sdr.repositories import leads as leads_repo
    from sdr.services import discovery

    rows = ["Company,Website,City,Country,Email,Employees"]
    for index in range(1000):
        rows.append(
            f"Business {index} Pvt Ltd,https://www.business{index}.in,"
            f"Pune,IN,hi@business{index}.in,{5 + index % 40}"
        )
    for index in range(200):  # duplicates, differently formatted
        rows.append(
            f"Business {index},business{index}.in,Pune,IN,,{5 + index % 40}"
        )
    content = "\n".join(rows) + "\n"

    parsed = csv_import.parse(content)
    assert parsed["report"]["rows_accepted"] == 1200

    result = await discovery.import_companies(
        parsed["records"], user=USER, create_leads=True
    )

    assert result["companies"]["inserted"] == 1000
    assert result["companies"]["deduped_in_batch"] == 200
    assert await repo.count_companies() == 1000
    assert result["leads"]["created"] == 1000

    # Filter
    filtered = await repo.list_companies(search="Business 42", limit=50)
    assert any(c["name"].startswith("Business 42") for c in filtered["items"])

    # Paginate - keyset, not skip/limit
    first = await leads_repo.list_leads(limit=50)
    assert len(first["items"]) == 50
    assert first["has_more"] is True

    second = await leads_repo.list_leads(limit=50, cursor=first["next_cursor"])
    assert len(second["items"]) == 50
    first_ids = {item["id"] for item in first["items"]}
    second_ids = {item["id"] for item in second["items"]}
    assert not (first_ids & second_ids), "Pages must not overlap"


# --- Leads --------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lead_creation_is_idempotent_per_company(db):
    """Re-running discovery must not create a second lead for one business."""
    from sdr.repositories import companies as repo
    from sdr.repositories import leads as leads_repo

    await repo.upsert_many([company("Acme", domain="acme.in")])
    stored = (await repo.list_companies())["items"]

    first = await leads_repo.create_many_from_companies(stored)
    second = await leads_repo.create_many_from_companies(stored)

    assert first["created"] == 1
    assert second["created"] == 0
    assert second["already_existed"] == 1


@pytest.mark.asyncio
async def test_created_lead_matches_the_host_crm_shape(db):
    """An SDR lead has to be a normal CRM lead, or it will not render on the
    pipeline board or convert through run_won_automation."""
    from sdr.repositories import companies as repo
    from sdr.repositories import leads as leads_repo

    await repo.upsert_many([
        company("Acme Dental", domain="acme.in", primary_email="hi@acme.in",
                phone_e164="+912012345678"),
    ])
    stored = (await repo.list_companies())["items"]
    await leads_repo.create_many_from_companies(stored, owner_id="user-1")

    lead = (await leads_repo.list_leads())["items"][0]
    for field in ("company", "stage", "score", "tags", "source", "created_at", "owner_id"):
        assert field in lead, f"missing host CRM field: {field}"
    assert lead["stage"] == "prospect"
    assert lead["sdr_managed"] is True
    assert "ai-sdr" in lead["tags"]


@pytest.mark.asyncio
async def test_lead_creation_writes_an_activity(db):
    from sdr.repositories import companies as repo
    from sdr.repositories import leads as leads_repo

    await repo.upsert_many([company("Acme", domain="acme.in")])
    stored = (await repo.list_companies())["items"]
    await leads_repo.create_many_from_companies(stored)

    lead = (await leads_repo.list_leads())["items"][0]
    activities = await leads_repo.activities(lead["id"])
    assert len(activities) == 1
    assert "Discovered by AI SDR" in activities[0]["content"]


@pytest.mark.asyncio
async def test_stage_transition_is_validated_and_recorded(db):
    from sdr.errors import IllegalTransitionError
    from sdr.repositories import companies as repo
    from sdr.repositories import leads as leads_repo

    await repo.upsert_many([company("Acme", domain="acme.in")])
    stored = (await repo.list_companies())["items"]
    await leads_repo.create_many_from_companies(stored)
    lead_id = (await leads_repo.list_leads())["items"][0]["id"]

    moved = await leads_repo.transition_stage(lead_id, "qualified", actor="ai")
    assert moved["stage"] == "qualified"
    assert moved["previous_stage"] == "prospect"
    assert moved["stage_entered_at"]

    activities = await leads_repo.activities(lead_id)
    assert any(a["type"] == "stage_change" for a in activities)

    with pytest.raises(IllegalTransitionError):
        await leads_repo.transition_stage(lead_id, "won", actor="ai")


@pytest.mark.asyncio
async def test_losing_a_lead_requires_a_reason(db):
    from sdr.errors import ValidationError
    from sdr.repositories import companies as repo
    from sdr.repositories import leads as leads_repo

    await repo.upsert_many([company("Acme", domain="acme.in")])
    stored = (await repo.list_companies())["items"]
    await leads_repo.create_many_from_companies(stored)
    lead_id = (await leads_repo.list_leads())["items"][0]["id"]
    await leads_repo.transition_stage(lead_id, "contacted", actor="ai")

    with pytest.raises(ValidationError):
        await leads_repo.transition_stage(lead_id, "lost", actor="ai")

    lost = await leads_repo.transition_stage(
        lead_id, "lost", actor="ai", reason="no_response"
    )
    assert lost["lost_reason"] == "no_response"


@pytest.mark.asyncio
async def test_soft_deleted_leads_disappear_from_lists_but_survive_in_storage(db):
    from sdr.repositories import companies as repo
    from sdr.repositories import leads as leads_repo

    await repo.upsert_many([company("Acme", domain="acme.in")])
    stored = (await repo.list_companies())["items"]
    await leads_repo.create_many_from_companies(stored)
    lead_id = (await leads_repo.list_leads())["items"][0]["id"]

    await leads_repo.soft_delete(lead_id)
    assert (await leads_repo.list_leads())["items"] == []

    raw = await db.leads.find_one({})
    assert raw is not None and raw["deleted_at"] is not None


@pytest.mark.asyncio
async def test_scope_still_returns_documents_written_before_this_module(db):
    """`scope()` filters deleted_at: None, which in MongoDB also matches
    documents where the field is absent. Thousands of pre-existing leads
    depend on that - this test exists so nobody 'fixes' it to $exists."""
    from sdr.repositories import leads as leads_repo

    await db.leads.insert_one({
        "company": "Legacy Lead", "stage": "prospect", "sdr_managed": True,
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    listed = await leads_repo.list_leads()
    assert [item["company"] for item in listed["items"]] == ["Legacy Lead"]


@pytest.mark.asyncio
async def test_non_sdr_leads_cannot_be_deleted_through_this_module(db):
    from sdr.errors import ValidationError
    from sdr.repositories import leads as leads_repo

    result = await db.leads.insert_one({
        "company": "Manual CRM Lead", "stage": "prospect",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    with pytest.raises(ValidationError):
        await leads_repo.soft_delete(str(result.inserted_id))


@pytest.mark.asyncio
async def test_score_is_persisted_with_its_breakdown_and_version(db):
    from sdr.domain import scoring
    from sdr.repositories import companies as repo
    from sdr.repositories import leads as leads_repo

    await repo.upsert_many([company("Acme", domain="acme.in")])
    stored = (await repo.list_companies())["items"]
    await leads_repo.create_many_from_companies(stored)
    lead = (await leads_repo.list_leads())["items"][0]

    scored = scoring.score_lead(lead, stored[0])
    updated = await leads_repo.apply_score(lead["id"], scored)

    assert updated["score"] == scored["score"]
    assert updated["score_version"] == scoring.SCORING_VERSION
    assert updated["score_breakdown"]


# --- Discovery run bookkeeping ------------------------------------------------

@pytest.mark.asyncio
async def test_import_records_a_discovery_run(db):
    from sdr.providers import csv_import
    from sdr.services import discovery

    parsed = csv_import.parse("Company,Website\nAcme,acme.in\n")
    result = await discovery.import_companies(parsed["records"], user=USER, create_leads=False)

    runs = await discovery.list_runs()
    assert len(runs) == 1
    assert runs[0]["id"] == result["discovery_run_id"]
    assert runs[0]["status"] == "completed"
    assert runs[0]["inserted_count"] == 1


@pytest.mark.asyncio
async def test_filters_are_applied_on_import_and_reported(db):
    """An operator imports a broad export and keeps only their ICP."""
    from sdr.dto.filters import DiscoveryFilters
    from sdr.providers import csv_import
    from sdr.repositories import companies as repo
    from sdr.services import discovery

    content = (
        "Company,City,Country,Industry\n"
        "Pune Dental,Pune,IN,dental\n"
        "Mumbai Dental,Mumbai,IN,dental\n"
    )
    parsed = csv_import.parse(content)
    result = await discovery.import_companies(
        parsed["records"], user=USER, create_leads=False,
        filters=DiscoveryFilters(geo={"cities": ["Pune"]}),
    )

    assert result["kept"] == 1
    assert result["filtered_out"] == {"geo.cities": 1}
    assert await repo.count_companies() == 1

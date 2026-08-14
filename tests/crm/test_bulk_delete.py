"""Delete-all in the pipeline. Irreversible, so the guards are the feature.

There is no restore. Everything here exists to make sure the only way to lose
data is to have meant it.

The queries are asserted by shape rather than executed - the suite is
deliberately I/O-free for these cases. That is a weaker test than running it
against Mongo, but it is not a decorative one: these two dicts *are* the
blast radius, and editing either without reading the reasoning trips this.
"""
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "crm_test")

from routers import crm  # noqa: E402


# --- What gets matched --------------------------------------------------------

def test_won_leads_are_excluded_by_default():
    """A won lead already produced a client, a project and an invoice. Deleting
    it undoes none of that - it removes the deal those records point back to."""
    assert crm.bulk_delete_query(include_won=False) == {
        "stage": {"$ne": "won"}, "deleted_at": None,
    }


def test_won_leads_go_only_when_explicitly_asked_for():
    assert crm.bulk_delete_query(include_won=True) == {"deleted_at": None}


def test_already_deleted_leads_are_never_matched():
    """Soft-deleted leads are filtered out of every read, so the delete-all
    count has to match what the board shows - otherwise the confirmation number
    is a different number from the one that gets destroyed."""
    for include_won in (True, False):
        assert crm.bulk_delete_query(include_won)["deleted_at"] is None


def test_a_contact_promoted_to_a_client_survives_its_lead():
    """`client_id` means the deal closed and the contact belongs to a live
    client now. Deleting it would take a real customer's details with it."""
    query = crm.orphaned_contacts_query(["a", "b"])
    assert query["lead_id"] == {"$in": ["a", "b"]}
    assert query["$or"] == [{"client_id": None}, {"client_id": {"$exists": False}}]


def test_contacts_are_scoped_to_the_deleted_leads_only():
    """Without the lead_id filter this empties the whole contacts collection."""
    assert "lead_id" in crm.orphaned_contacts_query(["x"])


# --- The confirmation gate ----------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("typed", ["", "delete", "Delete", "OK", "yes", "DELETE ", " DELETE"])
async def test_anything_but_the_exact_phrase_is_refused(typed):
    """Refused before any database call, so a near-miss cannot half-run.

    Case and whitespace both count. "delete" being accepted would make the
    dialog a formality."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await crm.bulk_delete_leads(
            crm.BulkDeleteLeads(confirm=typed, include_won=False),
            request=None,
            user={"id": "u1", "role": "admin"},
        )
    assert exc.value.status_code == 400
    assert crm.BULK_DELETE_PHRASE in exc.value.detail


def test_the_phrase_is_not_something_typed_by_habit():
    """OK / yes / y are muscle memory; the phrase has to interrupt."""
    assert crm.BULK_DELETE_PHRASE == "DELETE"
    assert crm.BULK_DELETE_PHRASE not in ("OK", "ok", "yes", "y", "confirm")


# --- Who can call it ----------------------------------------------------------

def test_bulk_delete_is_admin_only_not_staff():
    """team_member passes require_staff. Emptying the pipeline is not a
    team_member action, and the single-lead delete already covers their case."""
    from auth_utils import require_admin, require_staff

    for name in ("bulk_delete_leads", "preview_bulk_delete"):
        route = next(r for r in crm.router.routes if getattr(r, "name", None) == name)
        guards = [d.call for d in route.dependant.dependencies]
        assert require_admin in guards, f"{name} must be admin-only"
        assert require_staff not in guards, f"{name} must not accept team_member"


def test_delete_selected_is_staff_level_not_admin():
    """Deliberately lighter than delete-all. Picking six leads by hand is
    already the confirmation, and making the everyday action as heavy as the
    nuclear one only trains people to reach for the nuclear one."""
    from auth_utils import require_admin, require_staff

    route = next(r for r in crm.router.routes
                 if getattr(r, "name", None) == "delete_selected_leads")
    guards = [d.call for d in route.dependant.dependencies]
    assert require_staff in guards
    assert require_admin not in guards


@pytest.mark.asyncio
async def test_deleting_an_empty_selection_is_refused():
    """Reaches no database call. An empty list would otherwise match nothing
    and report cheerful success, which reads as "your leads are gone"."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await crm.delete_selected_leads(
            crm.DeleteSelectedLeads(lead_ids=[]),
            request=None, user={"id": "u1", "role": "admin"},
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_an_oversized_selection_is_refused():
    """A 5000-id list is a script, not a person clicking checkboxes."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await crm.delete_selected_leads(
            crm.DeleteSelectedLeads(lead_ids=[f"id{n}" for n in range(501)]),
            request=None, user={"id": "u1", "role": "admin"},
        )
    assert exc.value.status_code == 400


def test_single_lead_delete_is_still_open_to_staff():
    """The counterpart. Restricting the everyday action would push people to
    reach for the bulk one, which is the opposite of the intent."""
    from auth_utils import require_staff

    route = next(r for r in crm.router.routes if getattr(r, "name", None) == "delete_lead")
    assert require_staff in [d.call for d in route.dependant.dependencies]

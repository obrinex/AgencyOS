"""The Founding Circle: scoring, caps, and who can see what.

The rules worth testing here are the ones that cost something when they break:
a seat given away twice, an application lost, a member reading another
member's assistant thread, or the public learning who is in the circle.
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
os.environ.setdefault("DB_NAME", "founding_test")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-hmac")

import founding  # noqa: E402

ADMIN = {"id": "u-admin", "role": "admin"}

GOOD_ANSWERS = {
    "company": "Acme", "one_liner": "We do a thing.",
    "revenue_band": "5l_to_20l", "tenure_band": "18m_to_3y",
    "team_band": "2_to_5", "commitment_band": "5_to_10",
    "bottleneck": "Lead flow is inconsistent.",
    "already_tried": "Cold email and two contractors.",
    "first_90_days": "A repeatable pipeline.",
    # One social is enough — see `SOCIAL_KEYS`. Each is optional alone, but an
    # application with no way to look the person up cannot be scored on
    # credibility, so the set is required together.
    "linkedin": "https://linkedin.com/in/example",
}


@pytest_asyncio.fixture
async def db(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient

    database = AsyncMongoMockClient()["founding_test"]

    import auth_utils
    import database as database_module
    import email_service
    import rate_limit
    from routers import founding as router

    monkeypatch.setattr(database_module, "db", database)
    for module in (router, rate_limit, auth_utils, email_service):
        if hasattr(module, "db"):
            monkeypatch.setattr(module, "db", database)

    async def _silent(*a, **k):
        return None
    for name in ("send_founding_received_email", "send_founding_approved_email",
                 "send_founding_rejected_email"):
        monkeypatch.setattr(email_service, name, _silent)

    # Every call here arrives with request=None, so the limiter buckets them
    # all together as one caller and the fourth application 429s. Real traffic
    # comes from many addresses; these tests are about the round and seat
    # rules. The throttle gets its own test below, with the real limiter.
    monkeypatch.setattr(router, "check_rate_limit", _silent)
    return database


async def _apply(email="a@example.com", name="Dev", **overrides):
    from routers import founding as router

    answers = {**GOOD_ANSWERS, **overrides}
    return await router.public_apply(
        router.ApplicationSubmit(name=name, email=email, answers=answers),
        request=None)


# --- Scoring ------------------------------------------------------------------

def test_the_score_adds_up_to_one_hundred():
    """65 automatic + 35 judgement. If a band is retuned without adjusting the
    rest, the total silently stops being out of 100 and every past score
    becomes incomparable."""
    assert founding.AUTOMATIC_MAX == 65
    assert sum(founding.QUALITATIVE_MAX.values()) == 35
    assert founding.TOTAL_MAX == 100


def test_the_best_possible_application_scores_full_marks():
    best = {"revenue_band": "over_20l", "tenure_band": "over_3y",
            "team_band": "over_20", "commitment_band": "over_10"}
    perfect = {k: v for k, v in founding.QUALITATIVE_MAX.items()}
    assert founding.total_score(best, perfect)["total"] == 100


def test_an_unknown_band_scores_zero_rather_than_crashing():
    """Means the form and this module disagree - a bug, but not a reason to
    lose an application."""
    score = founding.automatic_score({"revenue_band": "somethingelse"})
    assert score["parts"]["revenue"] == 0


def test_ratings_cannot_exceed_their_axis():
    """The API clamps too, but the arithmetic must not depend on it."""
    inflated = founding.qualitative_score({"clarity": 999, "fit": 999})
    assert inflated["parts"]["clarity"] == 10
    assert inflated["parts"]["fit"] == 5


def test_an_unreviewed_application_is_marked_as_such():
    """Otherwise a fresh application and one you judged poor both read as a low
    number, and only one of them means anything."""
    assert founding.total_score(GOOD_ANSWERS, {})["reviewed"] is False
    assert founding.total_score(GOOD_ANSWERS, {"clarity": 1})["reviewed"] is True


def test_commitment_does_not_reward_over_promising():
    """Flat at the top on purpose - scoring the biggest promise highest selects
    for people who will say anything."""
    assert founding.COMMITMENT_POINTS["5_to_10"] == founding.COMMITMENT_POINTS["over_10"]


# --- Validation ---------------------------------------------------------------

def test_every_missing_required_answer_is_reported_at_once():
    """One trip through the form, not one fault per reload.

    The extra problem beyond `REQUIRED_KEYS` is the socials rule: each of those
    fields is optional by itself, so none of them is in `REQUIRED_KEYS`, but
    leaving all four empty is still a fault.
    """
    problems = founding.validate_answers({})
    assert len(problems) == len(founding.REQUIRED_KEYS) + 1


def test_a_valid_application_has_no_problems():
    assert founding.validate_answers(GOOD_ANSWERS) == []


def test_an_application_with_no_way_to_find_them_is_refused():
    """Every social blank means the credibility axis has nothing to read, and
    ten points would become an automatic zero nobody could explain."""
    answers = {k: v for k, v in GOOD_ANSWERS.items() if k not in founding.SOCIAL_KEYS}
    problems = founding.validate_answers(answers)
    assert any("find you" in p for p in problems)


def test_any_single_social_is_enough():
    base = {k: v for k, v in GOOD_ANSWERS.items() if k not in founding.SOCIAL_KEYS}
    for key in founding.SOCIAL_KEYS:
        assert founding.validate_answers({**base, key: "something"}) == []


def test_a_rating_entered_under_the_old_axis_name_still_counts():
    """`work_quality` became `credibility`. Applications rated before the
    rename must keep their ten points, or every past decision stops
    reproducing — which is how a scored process loses its authority."""
    old = founding.qualitative_score({"work_quality": 10})
    assert old["parts"]["credibility"] == 10
    # The new name wins where both somehow exist.
    both = founding.qualitative_score({"work_quality": 3, "credibility": 9})
    assert both["parts"]["credibility"] == 9


# --- Seats --------------------------------------------------------------------

def test_seats_run_out_at_ten():
    assert founding.can_approve(9) is True
    assert founding.can_approve(10) is False
    assert founding.seats_remaining(10) == 0
    assert founding.seats_remaining(99) == 0


@pytest.mark.asyncio
async def test_the_eleventh_approval_is_refused(db):
    """The check re-counts immediately before writing. Two people reviewing at
    once would otherwise both see one seat left and both take it."""
    from fastapi import HTTPException
    from routers import founding as router

    for n in range(founding.SEATS_PER_INTAKE):
        await db[router.APPLICATIONS].insert_one(
            {"status": founding.APPROVED, "round": founding.round_key(),
             "email": f"in{n}@example.com"})
    await _apply(email="eleventh@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "eleventh@example.com"})

    with pytest.raises(HTTPException) as exc:
        await router.decide(str(doc["_id"]), router.Decision(decision="approved"),
                            request=None, user=ADMIN)
    assert exc.value.status_code == 409
    assert "seats in this intake are" in exc.value.detail


# --- Rounds -------------------------------------------------------------------

def test_a_round_closes_when_it_fills():
    assert founding.should_close(100, founding.ROUND_OPEN, "2026-Q3", "2026-Q3") \
        == founding.CLOSED_BY_CAP
    assert founding.should_close(99, founding.ROUND_OPEN, "2026-Q3", "2026-Q3") is None


def test_an_intake_closes_when_its_quarter_ends():
    """An under-subscribed intake must not roll into the next one and quietly
    become a six-month intake."""
    assert founding.should_close(4, founding.ROUND_OPEN, "2026-Q4", "2026-Q3") \
        == founding.CLOSED_BY_QUARTER


def test_intakes_are_quarterly():
    from datetime import datetime, timezone

    assert founding.round_key(datetime(2026, 1, 5, tzinfo=timezone.utc)) == "2026-Q1"
    assert founding.round_key(datetime(2026, 8, 14, tzinfo=timezone.utc)) == "2026-Q3"
    assert founding.round_key(datetime(2026, 12, 31, tzinfo=timezone.utc)) == "2026-Q4"
    assert founding.quarter_months("2026-Q3") == (7, 8, 9)


@pytest.mark.asyncio
async def test_seats_reopen_each_quarter(db):
    """Ten seats per intake, not ten ever. A full previous quarter must not
    block this one - that is the whole point of a quarterly intake."""
    from routers import founding as router

    for n in range(founding.SEATS_PER_INTAKE):
        await db[router.APPLICATIONS].insert_one(
            {"status": founding.APPROVED, "round": "2025-Q1",
             "email": f"old{n}@example.com"})

    assert await router._total_members() == 10
    assert await router._approved_in_round(founding.round_key()) == 0

    await _apply(email="thisquarter@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "thisquarter@example.com"})
    result = await router.decide(str(doc["_id"]), router.Decision(decision="approved"),
                                 request=None, user=ADMIN)
    assert result["status"] == founding.APPROVED
    assert result["seats_remaining"] == 9


@pytest.mark.asyncio
async def test_the_hundredth_application_closes_the_round(db):
    from routers import founding as router

    await db[router.ROUNDS].insert_one({
        "key": founding.round_key(), "status": founding.ROUND_OPEN,
        "received": 0, "closed_reason": None})
    for n in range(founding.ROUND_APPLICATION_CAP):
        await _apply(email=f"a{n}@example.com")

    rnd = await db[router.ROUNDS].find_one({"key": founding.round_key()})
    assert rnd["status"] == founding.ROUND_CLOSED
    assert rnd["closed_reason"] == founding.CLOSED_BY_CAP


@pytest.mark.asyncio
async def test_the_public_application_endpoint_is_throttled(db, monkeypatch):
    """Unauthenticated, writes a document and sends an email. Restores the real
    limiter that the fixture stubs out."""
    from fastapi import HTTPException
    from rate_limit import check_rate_limit
    from routers import founding as router

    monkeypatch.setattr(router, "check_rate_limit", check_rate_limit)
    for n in range(router.APPLY_RATE_LIMIT):
        await _apply(email=f"t{n}@example.com")

    with pytest.raises(HTTPException) as exc:
        await _apply(email="one-too-many@example.com")
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_a_closed_round_refuses_new_applications(db):
    from fastapi import HTTPException
    from routers import founding as router

    await db[router.ROUNDS].insert_one({
        "key": founding.round_key(), "status": founding.ROUND_CLOSED,
        "received": 100, "closed_reason": founding.CLOSED_BY_CAP})
    with pytest.raises(HTTPException) as exc:
        await _apply(email="late@example.com")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_applying_twice_in_a_round_does_not_create_two_applications(db):
    """And the second reply is identical to the first - a different message
    would confirm to a stranger that an address is already in the system."""
    from routers import founding as router

    first = await _apply(email="dup@example.com")
    second = await _apply(email="dup@example.com")
    assert first == second
    assert await db[router.APPLICATIONS].count_documents({"email": "dup@example.com"}) == 1


# --- Nothing about the circle is public ---------------------------------------

@pytest.mark.asyncio
async def test_the_public_form_reveals_no_members_and_no_seat_count(db):
    """"Anonymous" means the ten people are never published. A public
    "3 seats left" is a countdown on a private group."""
    from routers import founding as router

    await db[router.APPLICATIONS].insert_one(
        {"status": founding.APPROVED, "name": "A Member", "email": "m@example.com"})
    body = await router.public_form()

    text = repr(body)
    assert "A Member" not in text
    assert "seats_remaining" not in body
    assert set(body) == {"open", "round", "questions", "band_labels",
                         "closes", "decision_by"}


def test_listing_members_is_staff_only():
    from auth_utils import require_staff
    from routers import founding as router

    route = next(r for r in router.router.routes
                 if getattr(r, "name", None) == "list_members")
    assert require_staff in [d.call for d in route.dependant.dependencies]


def test_deciding_a_seat_is_admin_only():
    """A seat in a ten-person circle is not a team_member decision."""
    from auth_utils import require_admin, require_staff
    from routers import founding as router

    route = next(r for r in router.router.routes
                 if getattr(r, "name", None) == "decide")
    guards = [d.call for d in route.dependant.dependencies]
    assert require_admin in guards
    assert require_staff not in guards


def test_the_member_portal_does_not_accept_clients():
    """A founding member is not a client and must not inherit the client
    portal's routes. Exact role match in both directions.

    The assistant and the membership record are members-only: staff do not get
    a personal assistant thread, and there is no membership to read for them.
    The community room is wider on purpose - see the test below.
    """
    from routers import founding as router

    assert router.FOUNDING_ROLE == "founding"
    assert router.FOUNDING_ROLE != "client"
    for name in ("assistant_ask", "assistant_history", "my_membership"):
        route = next(r for r in router.router.routes
                     if getattr(r, "name", None) == name)
        assert router.require_founding in [d.call for d in route.dependant.dependencies], name


# --- Invites ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_invite_link_works_once(db):
    """A forwarded approval email must not mint a second account."""
    from fastapi import HTTPException
    from routers import founding as router

    await _apply(email="new@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "new@example.com"})
    await router.decide(str(doc["_id"]), router.Decision(decision="approved"),
                        request=None, user=ADMIN)
    approved = await db[router.APPLICATIONS].find_one({"_id": doc["_id"]})
    token = approved["invite_token"]

    await router.accept_invite(
        router.AcceptInvite(token=token, password="a-long-enough-password"),
        request=None)
    user = await db.users.find_one({"email": "new@example.com"})
    assert user["role"] == "founding"

    with pytest.raises(HTTPException) as exc:
        await router.accept_invite(
            router.AcceptInvite(token=token, password="another-long-password"),
            request=None)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_a_rejection_issues_no_invite_token(db):
    from routers import founding as router

    await _apply(email="no@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "no@example.com"})
    await router.decide(str(doc["_id"]), router.Decision(decision="rejected"),
                        request=None, user=ADMIN)
    after = await db[router.APPLICATIONS].find_one({"_id": doc["_id"]})
    assert after["status"] == founding.REJECTED
    assert after["invite_token"] is None


@pytest.mark.asyncio
async def test_an_application_cannot_be_decided_twice(db):
    from fastapi import HTTPException
    from routers import founding as router

    await _apply(email="once@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "once@example.com"})
    await router.decide(str(doc["_id"]), router.Decision(decision="rejected"),
                        request=None, user=ADMIN)
    with pytest.raises(HTTPException) as exc:
        await router.decide(str(doc["_id"]), router.Decision(decision="approved"),
                            request=None, user=ADMIN)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_a_failed_decision_email_still_records_the_decision(db, monkeypatch):
    """The decision is committed before the send. Otherwise a mail outage
    leaves someone approved in the UI, un-emailed, and re-decidable."""
    import email_service
    from routers import founding as router

    async def _boom(*a, **k):
        raise RuntimeError("resend is down")
    monkeypatch.setattr(email_service, "send_founding_rejected_email", _boom)

    await _apply(email="mailfail@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "mailfail@example.com"})
    result = await router.decide(str(doc["_id"]),
                                 router.Decision(decision="rejected"),
                                 request=None, user=ADMIN)

    assert result["email_sent"] is False
    after = await db[router.APPLICATIONS].find_one({"_id": doc["_id"]})
    assert after["status"] == founding.REJECTED


# --- Member access control ----------------------------------------------------

@pytest.mark.asyncio
async def test_revoking_access_keeps_the_seat(db):
    """Revoke and remove are different powers. Revoking suspends the login;
    the seat stays theirs until it is explicitly returned."""
    from routers import founding as router

    await _apply(email="member@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "member@example.com"})
    await router.decide(str(doc["_id"]), router.Decision(decision="approved"),
                        request=None, user=ADMIN)
    approved = await db[router.APPLICATIONS].find_one({"_id": doc["_id"]})
    await router.accept_invite(
        router.AcceptInvite(token=approved["invite_token"], password="a-long-password"),
        request=None)

    before = await db[router.APPLICATIONS].count_documents({"status": founding.APPROVED})
    await router.set_member_access(str(doc["_id"]), router.AccessChange(active=False),
                                   request=None, user=ADMIN)

    user_row = await db.users.find_one({"email": "member@example.com"})
    assert user_row["is_active"] is False
    assert await db[router.APPLICATIONS].count_documents({"status": founding.APPROVED}) == before

    members = await router.list_members(user=ADMIN)
    assert members[0]["access"] == "revoked"

    await router.set_member_access(str(doc["_id"]), router.AccessChange(active=True),
                                   request=None, user=ADMIN)
    assert (await router.list_members(user=ADMIN))[0]["access"] == "active"


@pytest.mark.asyncio
async def test_removing_a_member_returns_the_seat(db):
    from routers import founding as router

    await _apply(email="leaving@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "leaving@example.com"})
    await router.decide(str(doc["_id"]), router.Decision(decision="approved"),
                        request=None, user=ADMIN)
    assert founding.seats_remaining(await router._approved_in_round()) == 9

    result = await router.remove_member(str(doc["_id"]), request=None, user=ADMIN)
    assert result["seats_remaining"] == 10
    assert await db.users.find_one({"email": "leaving@example.com"}) is None


@pytest.mark.asyncio
async def test_access_cannot_be_changed_before_the_invite_is_accepted(db):
    """There is no login to enable or disable yet, and pretending otherwise
    would report success while changing nothing."""
    from fastapi import HTTPException
    from routers import founding as router

    await _apply(email="notyet@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "notyet@example.com"})
    await router.decide(str(doc["_id"]), router.Decision(decision="approved"),
                        request=None, user=ADMIN)

    with pytest.raises(HTTPException) as exc:
        await router.set_member_access(str(doc["_id"]), router.AccessChange(active=False),
                                       request=None, user=ADMIN)
    assert exc.value.status_code == 409
    assert (await router.list_members(user=ADMIN))[0]["access"] == "pending"


@pytest.mark.asyncio
async def test_a_reinvite_invalidates_the_previous_link(db):
    """Otherwise a forwarded original keeps working alongside the replacement."""
    from routers import founding as router

    await _apply(email="lost@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "lost@example.com"})
    await router.decide(str(doc["_id"]), router.Decision(decision="approved"),
                        request=None, user=ADMIN)
    first = (await db[router.APPLICATIONS].find_one({"_id": doc["_id"]}))["invite_token"]

    await router.reinvite_member(str(doc["_id"]), user=ADMIN)
    second = (await db[router.APPLICATIONS].find_one({"_id": doc["_id"]}))["invite_token"]
    assert second and second != first


def test_managing_members_is_admin_only():
    from auth_utils import require_admin, require_staff
    from routers import founding as router

    for name in ("set_member_access", "remove_member", "reinvite_member"):
        route = next(r for r in router.router.routes if getattr(r, "name", None) == name)
        guards = [d.call for d in route.dependant.dependencies]
        assert require_admin in guards, name
        assert require_staff not in guards, name


# --- The community room -------------------------------------------------------

@pytest.mark.asyncio
async def test_staff_post_as_the_house_not_under_their_own_name(db):
    """A member must be able to tell a founder from the agency at a glance."""
    from routers import founding as router

    posted = await router.post_chat(router.ChatPost(body="Welcome, all."), user=ADMIN)
    assert posted["author_name"] == "Obrinex"
    assert posted["is_host"] is True


def test_the_community_room_is_closed_to_clients():
    """Members and staff only. A client role must not reach it."""
    from routers import founding as router

    for name in ("read_chat", "post_chat"):
        route = next(r for r in router.router.routes if getattr(r, "name", None) == name)
        assert router.require_circle in [d.call for d in route.dependant.dependencies], name
    assert "client" not in router.require_circle.__closure__[0].cell_contents


# --- Deleting an application --------------------------------------------------

def test_deleting_an_application_is_admin_only():
    """Same bar as deciding one. A team member reviewing applications must not
    be able to erase the evidence of one."""
    import inspect
    from routers import founding as router
    from auth_utils import require_admin

    dependency = inspect.signature(router.delete_application).parameters["user"].default
    assert dependency.dependency is require_admin


@pytest.mark.asyncio
async def test_deleting_an_application_removes_the_row(db):
    from routers import founding as router

    await _apply(email="spam@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "spam@example.com"})

    result = await router.delete_application(str(doc["_id"]), request=None, user=ADMIN)

    assert result["deleted"] is True
    assert await db[router.APPLICATIONS].find_one({"email": "spam@example.com"}) is None


@pytest.mark.asyncio
async def test_deleting_recounts_the_round_rather_than_decrementing(db):
    """`received` decides when an intake closes on its cap, so it has to match
    the collection - not a number nudged down by one and left to drift."""
    from routers import founding as router

    for n in range(3):
        await _apply(email=f"r{n}@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "r1@example.com"})

    result = await router.delete_application(str(doc["_id"]), request=None, user=ADMIN)

    assert result["received"] == 2
    stored = await db[router.ROUNDS].find_one({"key": founding.round_key()})
    assert stored["received"] == 2


@pytest.mark.asyncio
async def test_deleting_a_member_frees_the_seat_and_their_login(db):
    """An approved application may hold a portal account. Deleting the row and
    leaving the user would strand a login that resolves to no membership."""
    from routers import founding as router

    user_id = (await db.users.insert_one({"email": "member@example.com",
                                          "role": "founding"})).inserted_id
    await _apply(email="member@example.com")
    doc = await db[router.APPLICATIONS].find_one({"email": "member@example.com"})
    await db[router.APPLICATIONS].update_one(
        {"_id": doc["_id"]},
        {"$set": {"status": founding.APPROVED, "portal_user_id": str(user_id)}})

    assert await router._approved_in_round() == 1

    result = await router.delete_application(str(doc["_id"]), request=None, user=ADMIN)

    assert result["was_status"] == founding.APPROVED
    assert result["had_account"] is True
    assert result["seats_remaining"] == founding.SEATS_PER_INTAKE
    assert await db.users.find_one({"_id": user_id}) is None


@pytest.mark.asyncio
async def test_deleting_reopens_an_intake_that_closed_on_its_cap(db):
    """Clearing spam out of a full round is the reason to want this at all."""
    from routers import founding as router

    key = founding.round_key()
    for n in range(founding.ROUND_APPLICATION_CAP):
        await db[router.APPLICATIONS].insert_one(
            {"round": key, "email": f"c{n}@example.com", "status": founding.PENDING})
    await db[router.ROUNDS].insert_one(
        {"key": key, "status": founding.ROUND_CLOSED,
         "closed_reason": founding.CLOSED_BY_CAP,
         "received": founding.ROUND_APPLICATION_CAP})
    doc = await db[router.APPLICATIONS].find_one({"email": "c0@example.com"})

    result = await router.delete_application(str(doc["_id"]), request=None, user=ADMIN)

    assert result["round_reopened"] is True
    stored = await db[router.ROUNDS].find_one({"key": key})
    assert stored["status"] == founding.ROUND_OPEN
    assert stored["closed_reason"] is None


@pytest.mark.asyncio
async def test_deleting_does_not_reopen_an_intake_whose_quarter_ended(db):
    """A finished quarter is not a fault a deletion can repair."""
    from routers import founding as router

    old = "2026-Q1"
    await db[router.APPLICATIONS].insert_one(
        {"round": old, "email": "old@example.com", "status": founding.PENDING})
    await db[router.ROUNDS].insert_one(
        {"key": old, "status": founding.ROUND_CLOSED,
         "closed_reason": founding.CLOSED_BY_QUARTER, "received": 1})
    doc = await db[router.APPLICATIONS].find_one({"email": "old@example.com"})

    result = await router.delete_application(str(doc["_id"]), request=None, user=ADMIN)

    assert result["round_reopened"] is False
    stored = await db[router.ROUNDS].find_one({"key": old})
    assert stored["status"] == founding.ROUND_CLOSED


@pytest.mark.asyncio
async def test_deleting_something_that_is_not_there_is_a_404(db):
    """Including a malformed id — `to_object_id` raises on those, and an
    unhandled raise would be a 500 for what is plainly a not-found."""
    from fastapi import HTTPException
    from routers import founding as router

    for bad in ("not-an-object-id", "6712aaaaaaaaaaaaaaaaaaaa"):
        with pytest.raises(HTTPException) as exc:
            await router.delete_application(bad, request=None, user=ADMIN)
        assert exc.value.status_code == 404


# --- Member profiles, directory and projects ----------------------------------

async def _member_with_profile(db, email="m@example.com", name="Mem"):
    """An approved member and the user record that reaches their portal."""
    from routers import founding as router

    await _apply(email=email, name=name)
    doc = await db[router.APPLICATIONS].find_one({"email": email})
    await db[router.APPLICATIONS].update_one(
        {"_id": doc["_id"]}, {"$set": {"status": founding.APPROVED}})
    return ({"id": f"u-{email}", "role": "founding",
             "founding_application_id": str(doc["_id"])}, doc)


@pytest.mark.asyncio
async def test_contact_details_are_hidden_from_other_members_by_default(db):
    """They gave us a phone number to be assessed, not to be published to nine
    strangers. Nothing shareable appears until its own flag is turned on."""
    from routers import founding as router

    user, _ = await _member_with_profile(db)
    await router.my_profile(user=user)  # seeds the profile from the application

    listing = await router.directory(user=user)
    person = next(p for p in listing if p["name"] == "Mem")

    assert person["company"] == "Acme"          # always on - it is a directory
    assert person["linkedin"] == ""             # supplied, but not shared
    assert person["email"] == ""
    assert person["phone"] == ""


@pytest.mark.asyncio
async def test_a_member_can_choose_what_to_share(db):
    from routers import founding as router

    user, _ = await _member_with_profile(db)
    await router.my_profile(user=user)
    await router.update_my_profile(
        router.ProfileUpdate(visibility={"linkedin": True}), user=user)

    person = next(p for p in await router.directory(user=user) if p["name"] == "Mem")
    assert person["linkedin"] == "https://linkedin.com/in/example"
    assert person["phone"] == ""  # still off - one flag does not open the rest


@pytest.mark.asyncio
async def test_an_unknown_visibility_key_cannot_be_smuggled_in(db):
    """A flag nothing reads would be believed to be doing something."""
    from routers import founding as router

    user, _ = await _member_with_profile(db)
    await router.my_profile(user=user)
    saved = await router.update_my_profile(
        router.ProfileUpdate(visibility={"linkedin": True, "salary": True}), user=user)

    assert "salary" not in saved["visibility"]
    assert set(saved["visibility"]) == set(router.SHAREABLE)


@pytest.mark.asyncio
async def test_editing_a_profile_never_rewrites_the_application(db):
    """The application is the record of what they said to get in. If editing a
    profile could change it, the score would stop matching the answers."""
    from routers import founding as router

    user, application = await _member_with_profile(db)
    await router.my_profile(user=user)
    await router.update_my_profile(
        router.ProfileUpdate(headline="Something else entirely"), user=user)

    fresh = await db[router.APPLICATIONS].find_one({"_id": application["_id"]})
    assert fresh["answers"]["one_liner"] == "We do a thing."


@pytest.mark.asyncio
async def test_projects_are_listed_with_who_is_building_them(db):
    from routers import founding as router

    user, _ = await _member_with_profile(db)
    await router.my_profile(user=user)
    await router.update_my_profile(
        router.ProfileUpdate(projects=[
            router.ProjectEntry(title="Warehouse robots", status="Building"),
        ]), user=user)

    rows = await router.projects(user=user)
    assert rows[0]["title"] == "Warehouse robots"
    assert rows[0]["owner"] == "Mem"


@pytest.mark.asyncio
async def test_an_unlisted_member_keeps_their_name_and_loses_everything_else(db):
    """Opting out of the directory is not the same as leaving the circle."""
    from routers import founding as router

    user, _ = await _member_with_profile(db)
    await router.my_profile(user=user)
    await router.update_my_profile(
        router.ProfileUpdate(listed=False, headline="Hidden",
                             projects=[router.ProjectEntry(title="Secret")]),
        user=user)

    person = next(p for p in await router.directory(user=user) if p["name"] == "Mem")
    assert person["headline"] == ""
    assert person["projects"] == []
    assert await router.projects(user=user) == []


# --- Referrals ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_referral_tags_the_application_without_helping_it(db):
    """Knowing a member gets your application read, not accepted. A referral
    that bought points would make the circle a place you get into by knowing
    someone."""
    from routers import founding as router

    user, member = await _member_with_profile(db, email="ref@example.com", name="Ref")
    created = await router.create_referral(
        router.ReferralCreate(label="A friend", note="Sharp operator"), user=user)

    await router.public_apply(
        router.ApplicationSubmit(name="Guest", email="guest@example.com",
                                 answers=GOOD_ANSWERS, referral=created["code"]),
        request=None)

    doc = await db[router.APPLICATIONS].find_one({"email": "guest@example.com"})
    assert doc["referred_by"] == "Ref"
    assert doc["referral_note"] == "Sharp operator"
    # Same score it would have had arriving cold.
    assert doc["score"]["total"] == founding.total_score(GOOD_ANSWERS, {})["total"]


@pytest.mark.asyncio
async def test_an_invitation_can_only_produce_one_application(db):
    """It did its job the moment it produced an application; left live, one
    link would introduce a queue."""
    from routers import founding as router

    user, _ = await _member_with_profile(db, email="ref2@example.com", name="Ref")
    code = (await router.create_referral(router.ReferralCreate(), user=user))["code"]

    await router.public_apply(
        router.ApplicationSubmit(name="First", email="first@example.com",
                                 answers=GOOD_ANSWERS, referral=code), request=None)
    await router.public_apply(
        router.ApplicationSubmit(name="Second", email="second@example.com",
                                 answers=GOOD_ANSWERS, referral=code), request=None)

    second = await db[router.APPLICATIONS].find_one({"email": "second@example.com"})
    assert second["referred_by"] is None
    assert (await router.check_referral(code))["valid"] is False


@pytest.mark.asyncio
async def test_a_stale_invitation_does_not_cost_someone_their_answers(db):
    """The applicant did nothing wrong. Losing eleven answers over an expired
    link would be absurd."""
    from routers import founding as router

    await router.public_apply(
        router.ApplicationSubmit(name="Guest", email="stale@example.com",
                                 answers=GOOD_ANSWERS, referral="not-a-real-code"),
        request=None)

    doc = await db[router.APPLICATIONS].find_one({"email": "stale@example.com"})
    assert doc is not None
    assert doc["referred_by"] is None


@pytest.mark.asyncio
async def test_checking_a_code_reveals_nothing_about_members(db):
    """Public endpoint. An unknown code and a spent one must look identical, or
    it becomes a way to enumerate the circle."""
    from routers import founding as router

    assert await router.check_referral("nonsense") == {"valid": False}


@pytest.mark.asyncio
async def test_a_member_cannot_revoke_someone_elses_invitation(db):
    from fastapi import HTTPException
    from routers import founding as router

    one, _ = await _member_with_profile(db, email="one@example.com", name="One")
    two, _ = await _member_with_profile(db, email="two@example.com", name="Two")
    await router.create_referral(router.ReferralCreate(), user=one)
    mine = (await router.my_referrals(user=one))[0]

    with pytest.raises(HTTPException) as exc:
        await router.revoke_referral(mine["id"], user=two)
    assert exc.value.status_code == 404

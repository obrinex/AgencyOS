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
    """One trip through the form, not one fault per reload."""
    problems = founding.validate_answers({})
    assert len(problems) == len(founding.REQUIRED_KEYS)


def test_a_valid_application_has_no_problems():
    assert founding.validate_answers(GOOD_ANSWERS) == []


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

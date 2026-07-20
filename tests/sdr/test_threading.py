"""Threading identity on outbound mail.

The point of these tests is a property that cannot be recovered after the
fact: if a message goes out without a `Message-ID` we chose, the reply it
earns carries an id we have no record of, and no amount of later work can
match the two. Everything here guards that one seam.

The second concern is the inverse - threading under a parent the recipient
never actually received (a rejected draft, a simulated rehearsal), which
produces an orphan reference rather than a conversation.
"""

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "sdr_test")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-hmac")

from test_campaign_flow import (  # noqa: E402  - shared fixtures and helpers
    USER, _force_due, _make_running_campaign, _seed_lead, db, ready, stub_llm,
)


# --- The pure part ------------------------------------------------------------

def test_a_message_id_is_deterministic_and_domain_matched():
    from sdr.domain import email_threading

    minted = email_threading.message_id_for("abc123", "hello@sender.example")
    assert minted == "<sdr-abc123@sender.example>"
    # Same row, same header - so a reply can be matched by re-deriving it.
    assert minted == email_threading.message_id_for("abc123", "HELLO@Sender.Example")


def test_a_message_id_refuses_to_be_minted_without_a_domain():
    from sdr.domain import email_threading

    with pytest.raises(ValueError):
        email_threading.message_id_for("abc123", "not-an-address")
    with pytest.raises(ValueError):
        email_threading.message_id_for("", "hello@sender.example")


def test_a_first_touch_has_no_parent():
    from sdr.domain import email_threading

    assert email_threading.chain(None) == (None, [])
    assert email_threading.headers(own_message_id="<a@x>") == {"Message-ID": "<a@x>"}


def test_references_accumulate_down_the_chain():
    from sdr.domain import email_threading

    first = {"email_message_id": "<a@x>", "references": []}
    in_reply_to, references = email_threading.chain(first)
    assert in_reply_to == "<a@x>"
    assert references == ["<a@x>"]

    second = {"email_message_id": "<b@x>", "references": references}
    in_reply_to, references = email_threading.chain(second)
    assert in_reply_to == "<b@x>"
    assert references == ["<a@x>", "<b@x>"]

    assert email_threading.headers(
        own_message_id="<c@x>", in_reply_to=in_reply_to, references=references,
    ) == {
        "Message-ID": "<c@x>",
        "In-Reply-To": "<b@x>",
        "References": "<a@x> <b@x>",
    }


def test_a_parent_without_an_id_is_treated_as_no_parent():
    """Half a chain is worse than none - it points at an id the recipient's
    client has never seen. Covers every message sent before this existed."""
    from sdr.domain import email_threading

    assert email_threading.chain({"email_message_id": None}) == (None, [])
    assert email_threading.chain({}) == (None, [])


def test_an_empty_in_reply_to_header_is_omitted_rather_than_sent_blank():
    from sdr.domain import email_threading

    result = email_threading.headers(
        own_message_id="<a@x>", in_reply_to=None, references=[]
    )
    assert "In-Reply-To" not in result
    assert "References" not in result


# --- On the wire --------------------------------------------------------------

async def _send_live(db, monkeypatch, captured, message_id):
    """Dispatch one approved message live, capturing the provider call."""
    from sdr.agents.base.agent import AgentContext
    from sdr.agents.outreach.agent import OutreachSendAgent
    from sdr.providers import email_resend

    async def capture(**kwargs):
        captured.update(kwargs)
        return {"provider_message_id": f"re_{kwargs['subject'][:6]}"}

    monkeypatch.setattr(email_resend, "send", capture)
    await _force_due(db, message_id)
    return await OutreachSendAgent().run({"message_id": message_id}, AgentContext())


@pytest.mark.asyncio
async def test_a_live_send_carries_a_message_id_we_control(db, ready, monkeypatch, stub_llm):
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.repositories import settings as settings_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    await settings_repo.update_settings({"send_mode": "live"})
    _, lead = await _seed_lead()
    await _make_running_campaign([lead["id"]])
    await campaigns_service.tick()
    await jobs.drain()
    draft = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]
    await campaigns_service.approve_message(draft["id"], user=USER)

    captured = {}
    result = await _send_live(db, monkeypatch, captured, draft["id"])
    assert result.output["sent"] is True

    expected = f"<sdr-{draft['id']}@sender.example>"
    assert captured["headers"]["Message-ID"] == expected
    # A first touch threads under nothing.
    assert "In-Reply-To" not in captured["headers"]
    assert "References" not in captured["headers"]

    # And it is on the row, which is what an inbound reply will be matched to.
    stored = await campaigns_repo.get_message(draft["id"])
    assert stored["email_message_id"] == expected
    assert stored["in_reply_to"] is None
    assert stored["references"] == []
    assert await campaigns_repo.find_by_email_message_id(expected) is not None


@pytest.mark.asyncio
async def test_a_follow_up_threads_under_the_message_it_follows(db, ready, monkeypatch, stub_llm):
    """The reason this matters beyond matching: a follow-up that threads reads
    as a conversation rather than a second cold email."""
    from sdr.collections import ENROLLMENTS
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.repositories import settings as settings_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    await settings_repo.update_settings({"send_mode": "live"})
    _, lead = await _seed_lead()
    await _make_running_campaign([lead["id"]])

    # Step 1: draft, approve, send.
    await campaigns_service.tick()
    await jobs.drain()
    first = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]
    await campaigns_service.approve_message(first["id"], user=USER)
    await _send_live(db, monkeypatch, {}, first["id"])
    first_id = (await campaigns_repo.get_message(first["id"]))["email_message_id"]

    # Step 2 comes due.
    await db[ENROLLMENTS].update_many(
        {}, {"$set": {"next_touch_at": "2020-01-01T00:00:00+00:00"}}
    )
    await campaigns_service.tick()
    await jobs.drain()
    second = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]
    assert second["step_index"] == 1
    await campaigns_service.approve_message(second["id"], user=USER)

    captured = {}
    await _send_live(db, monkeypatch, captured, second["id"])

    assert captured["headers"]["In-Reply-To"] == first_id
    assert captured["headers"]["References"] == first_id
    assert captured["headers"]["Message-ID"] == f"<sdr-{second['id']}@sender.example>"

    stored = await campaigns_repo.get_message(second["id"])
    assert stored["in_reply_to"] == first_id
    assert stored["references"] == [first_id]


@pytest.mark.asyncio
async def test_a_real_send_never_threads_under_a_simulated_one(db, ready, monkeypatch, stub_llm):
    """A rehearsal is marked `sent`, but no mail left the building. Threading a
    real follow-up under it would reference an id the recipient never saw."""
    from sdr.collections import ENROLLMENTS
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.repositories import settings as settings_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    _, lead = await _seed_lead()
    await _make_running_campaign([lead["id"]])

    # Step 1 goes out in simulate mode - the shipped default.
    await campaigns_service.tick()
    await jobs.drain()
    first = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]
    await campaigns_service.approve_message(first["id"], user=USER)
    await _force_due(db, first["id"])
    await campaigns_service.tick()
    await jobs.drain()
    simulated = await campaigns_repo.get_message(first["id"])
    assert simulated["simulated"] is True
    # The rehearsal still records what would have gone out.
    assert simulated["email_message_id"]

    # Now go live for step 2.
    await settings_repo.update_settings({"send_mode": "live"})
    await db[ENROLLMENTS].update_many(
        {}, {"$set": {"next_touch_at": "2020-01-01T00:00:00+00:00"}}
    )
    await campaigns_service.tick()
    await jobs.drain()
    second = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]
    await campaigns_service.approve_message(second["id"], user=USER)

    captured = {}
    await _send_live(db, monkeypatch, captured, second["id"])

    assert "In-Reply-To" not in captured["headers"]
    assert "References" not in captured["headers"]


# --- Reply-To -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_reply_to_is_sent_unless_one_is_configured(db, ready, monkeypatch, stub_llm):
    """Default None on purpose: a Reply-To pointing at a mailbox that does not
    exist bounces the prospect's answer, which is worse than not setting it."""
    from sdr.repositories import campaigns as campaigns_repo
    from sdr.repositories import settings as settings_repo
    from sdr.services import campaigns as campaigns_service
    from sdr.services import jobs

    await settings_repo.update_settings({"send_mode": "live"})
    _, lead = await _seed_lead()
    await _make_running_campaign([lead["id"]])
    await campaigns_service.tick()
    await jobs.drain()
    draft = (await campaigns_repo.list_messages(status="awaiting_approval"))["items"][0]
    await campaigns_service.approve_message(draft["id"], user=USER)

    captured = {}
    await _send_live(db, monkeypatch, captured, draft["id"])
    assert captured["reply_to"] is None

    # Configured, it reaches the provider.
    await settings_repo.update_settings({"reply_to_address": "replies@sender.example"})
    settings = await settings_repo.get_settings()
    assert settings["reply_to_address"] == "replies@sender.example"

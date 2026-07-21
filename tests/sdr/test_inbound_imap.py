"""IMAP ingestion.

The guarantee worth testing hardest is that this never modifies the mailbox.
`jagjot@obrinexagency.space` is a real inbox somebody reads by hand; if
polling marked messages as read, new mail would silently stop looking new to
the person who owns it. That is a worse failure than anything polling fixes,
and it is invisible until someone misses a reply.

Second is the UID cursor. It must advance only after a batch is ingested — the
opposite ordering drops replies on a crash, and a dropped reply is a person
who answered and never heard back.
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

from test_campaign_flow import (  # noqa: E402  - shared fixtures
    db, ready, stub_llm,
)

RAW_REPLY = b"""From: Dr Priya Kumar <owner@kumar1.example>
To: jagjot@obrinexagency.space
Subject: Re: your booking page
Message-ID: <reply-99@kumar1.example>
In-Reply-To: <sdr-abc123@obrinexagency.space>
References: <sdr-abc123@obrinexagency.space>
Content-Type: text/plain; charset="utf-8"

Sounds interesting - can we talk Thursday?
"""

RAW_OOO = b"""From: auto@kumar1.example
To: jagjot@obrinexagency.space
Subject: =?utf-8?B?QXV0b21hdGljIHJlcGx5OiBvdXQgb2Ygb2ZmaWNl?=
Message-ID: <ooo-1@kumar1.example>
Auto-Submitted: auto-replied
Content-Type: text/plain; charset="utf-8"

I am on leave until 5 August.
"""

RAW_MULTIPART = b"""From: someone@kumar1.example
To: jagjot@obrinexagency.space
Subject: Re: hello
Message-ID: <multi-1@kumar1.example>
Content-Type: multipart/alternative; boundary="BOUND"

--BOUND
Content-Type: text/plain; charset="utf-8"

The plain text part.
--BOUND
Content-Type: text/html; charset="utf-8"

<html><body><p>The HTML part.</p></body></html>
--BOUND--
"""


# --- Parsing ------------------------------------------------------------------

def test_a_raw_message_normalizes_to_the_same_shape_as_the_webhook():
    """Matching, classification and wiring must never learn which transport
    delivered the mail."""
    from sdr.providers import inbound_cloudflare, inbound_imap

    parsed = inbound_imap.normalize(RAW_REPLY)

    assert parsed["from_email"] == "owner@kumar1.example"
    assert parsed["ingest_key"] == "<reply-99@kumar1.example>"
    assert parsed["in_reply_to"] == "<sdr-abc123@obrinexagency.space>"
    assert "Thursday" in parsed["text_body"]
    assert parsed["provider"] == "imap"

    # Same keys as the Cloudflare adapter produces.
    webhook = inbound_cloudflare.normalize({
        "from": "a@b.example", "to": "c@d.example", "subject": "x",
        "text": "y", "headers": {"Message-ID": "<z@x>"},
    })
    assert set(parsed) == set(webhook)


def test_encoded_headers_are_decoded():
    """Subjects arrive RFC 2047-encoded. An undecoded one would defeat the
    out-of-office subject patterns entirely."""
    from sdr.providers import inbound_imap

    parsed = inbound_imap.normalize(RAW_OOO)
    assert parsed["subject"] == "Automatic reply: out of office"
    assert parsed["headers"]["Auto-Submitted"] == "auto-replied"


def test_the_machine_check_still_fires_on_an_imap_message():
    """End of the chain that matters: decoded subject plus headers must still
    produce out_of_office, not a false human reply."""
    from sdr.domain import inbound
    from sdr.providers import inbound_imap

    parsed = inbound_imap.normalize(RAW_OOO)
    assert inbound.detect_machine_reply(
        headers=parsed["headers"], subject=parsed["subject"],
        from_email=parsed["from_email"],
    ) == "out_of_office"


def test_the_plain_text_part_is_preferred_over_html():
    from sdr.providers import inbound_imap

    parsed = inbound_imap.normalize(RAW_MULTIPART)
    assert "The plain text part." in parsed["text_body"]
    assert "<p>" not in parsed["text_body"]


def test_a_message_without_an_id_yields_no_ingest_key():
    """Without one there is no idempotency key, so the service must skip it
    rather than risk processing the same reply on every poll."""
    from sdr.providers import inbound_imap

    parsed = inbound_imap.normalize(
        b"From: a@b.example\nSubject: hi\n\nbody\n"
    )
    assert parsed["ingest_key"] is None


# --- The mailbox is somebody else's -------------------------------------------

class _FakeIMAP:
    """Records every command so the test can assert what was NOT sent."""

    def __init__(self, messages, uidvalidity=b"1"):
        self.messages = messages          # {uid: raw}
        self.commands = []
        self.selected_readonly = None
        self._uidvalidity = uidvalidity

    def login(self, user, password):
        self.commands.append(("login", user))
        return "OK", [b""]

    def select(self, mailbox, readonly=False):
        self.selected_readonly = readonly
        self.commands.append(("select", mailbox, readonly))
        return "OK", [b"1"]

    def status(self, mailbox, what):
        return "OK", [b'"INBOX" (UIDVALIDITY ' + self._uidvalidity + b")"]

    def uid(self, command, *args):
        self.commands.append(("uid", command) + tuple(args))
        if command == "search":
            return "OK", [b" ".join(str(u).encode() for u in sorted(self.messages))]
        if command == "fetch":
            uid = int(args[0])
            return "OK", [(b"", self.messages[uid])]
        if command == "store":
            raise AssertionError("polling must never change message flags")
        return "OK", [b""]

    def logout(self):
        self.commands.append(("logout",))
        return "OK", [b""]


@pytest.mark.asyncio
async def test_polling_never_marks_anything_read(monkeypatch):
    """The guarantee. A human reads this inbox; hiding their new mail is a
    worse bug than anything polling solves."""
    from sdr.providers import inbound_imap

    fake = _FakeIMAP({7: RAW_REPLY})
    monkeypatch.setattr(inbound_imap, "_connect", lambda: fake)

    await inbound_imap.fetch_new(last_uid=0)

    # SELECT was read-only, and the fetch used PEEK.
    assert fake.selected_readonly is True
    fetches = [c for c in fake.commands if c[:2] == ("uid", "fetch")]
    assert fetches, "nothing was fetched"
    assert all("BODY.PEEK[]" in c[-1] for c in fetches), \
        "must use BODY.PEEK, which preserves the unread flag"
    # And nothing ever tried to set a flag.
    assert not [c for c in fake.commands if c[:2] == ("uid", "store")]


@pytest.mark.asyncio
async def test_only_messages_newer_than_the_cursor_are_returned(monkeypatch):
    """`UID n:*` always returns the newest message even when nothing is newer,
    so the filter is load-bearing, not defensive."""
    from sdr.providers import inbound_imap

    fake = _FakeIMAP({5: RAW_REPLY})
    monkeypatch.setattr(inbound_imap, "_connect", lambda: fake)

    batch = await inbound_imap.fetch_new(last_uid=5)
    assert batch["messages"] == []
    assert batch["last_uid"] == 5


@pytest.mark.asyncio
async def test_a_large_backlog_is_truncated_and_says_so(monkeypatch):
    """Vercel gives the tick 60 seconds. A backlog drains over several polls
    rather than timing out on one - but silence would read as a quiet inbox."""
    from sdr.providers import inbound_imap

    fake = _FakeIMAP({uid: RAW_REPLY for uid in range(1, 40)})
    monkeypatch.setattr(inbound_imap, "_connect", lambda: fake)

    batch = await inbound_imap.fetch_new(last_uid=0, limit=10)
    assert len(batch["messages"]) == 10
    assert batch["truncated"] is True
    assert batch["last_uid"] == 10


@pytest.mark.asyncio
async def test_a_renumbered_mailbox_skips_forward_instead_of_replaying(monkeypatch):
    """UIDVALIDITY changing means old UIDs are meaningless. Replaying the
    inbox would re-stop sequences and re-suppress addresses; missing a message
    is the lesser harm."""
    from sdr.providers import inbound_imap

    fake = _FakeIMAP({1: RAW_REPLY, 2: RAW_OOO}, uidvalidity=b"999")
    monkeypatch.setattr(inbound_imap, "_connect", lambda: fake)

    batch = await inbound_imap.fetch_new(last_uid=50, uidvalidity=1)

    assert batch["messages"] == []
    assert batch["uidvalidity"] == 999
    assert batch["last_uid"] == 2   # resumes from the end


# --- The service ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_polling_is_off_until_it_is_configured(db, ready, stub_llm):
    """A fresh install must do nothing rather than fail every tick."""
    from sdr.services import inbound as inbound_service

    result = await inbound_service.poll_imap()
    assert result["skipped"] is True


@pytest.mark.asyncio
async def test_a_polled_reply_runs_the_same_pipeline_as_a_webhook(
        db, ready, monkeypatch, stub_llm):
    from sdr.providers import inbound_imap
    from sdr.repositories import inbound as inbound_repo
    from sdr.repositories import settings as settings_repo
    from sdr.services import inbound as inbound_service

    await settings_repo.update_settings({"inbound_mode": "imap"})
    monkeypatch.setenv("IMAP_HOST", "imap.hostinger.com")
    monkeypatch.setenv("IMAP_USER", "jagjot@obrinexagency.space")
    monkeypatch.setenv("IMAP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr(inbound_imap, "_connect",
                        lambda: _FakeIMAP({3: RAW_OOO}))

    result = await inbound_service.poll_imap()

    assert result["processed"] == 1
    stored = (await inbound_repo.list_inbound())["items"][0]
    # Classified deterministically from headers, exactly as via the webhook.
    assert stored["category"] == "out_of_office"
    assert stored["category_source"] == "headers"

    # The cursor advanced, so the next poll will not re-fetch it.
    settings = await settings_repo.get_settings()
    assert settings["inbound_imap_last_uid"] == 3


@pytest.mark.asyncio
async def test_the_same_message_twice_is_processed_once(
        db, ready, monkeypatch, stub_llm):
    """A crash mid-poll re-fetches by design - the cursor only advances after
    ingestion. That is safe only because ingest_key dedupes."""
    from sdr.providers import inbound_imap
    from sdr.repositories import settings as settings_repo
    from sdr.services import inbound as inbound_service

    await settings_repo.update_settings({"inbound_mode": "imap"})
    monkeypatch.setenv("IMAP_HOST", "imap.hostinger.com")
    monkeypatch.setenv("IMAP_USER", "jagjot@obrinexagency.space")
    monkeypatch.setenv("IMAP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr(inbound_imap, "_connect",
                        lambda: _FakeIMAP({4: RAW_OOO}))

    first = await inbound_service.poll_imap()
    # Rewind the cursor, as a crash before the settings write would.
    await settings_repo.update_settings({"inbound_imap_last_uid": 0})
    second = await inbound_service.poll_imap()

    assert first["processed"] == 1
    assert second["processed"] == 0     # deduped, not reprocessed
    assert second["fetched"] == 1


@pytest.mark.asyncio
async def test_an_unreachable_mailbox_is_recorded_not_swallowed(
        db, ready, monkeypatch, stub_llm):
    """Silent inbound failure is the exact thing this module exists to
    prevent."""
    from sdr.providers import inbound_imap
    from sdr.repositories import settings as settings_repo
    from sdr.services import inbound as inbound_service

    await settings_repo.update_settings({"inbound_mode": "imap"})
    monkeypatch.setenv("IMAP_HOST", "imap.hostinger.com")
    monkeypatch.setenv("IMAP_USER", "jagjot@obrinexagency.space")
    monkeypatch.setenv("IMAP_PASSWORD", "wrong")

    def _boom():
        raise OSError("connection refused")

    monkeypatch.setattr(inbound_imap, "_connect", _boom)

    result = await inbound_service.poll_imap()

    assert result["failed"] is True
    settings = await settings_repo.get_settings()
    assert "connection refused" in settings["inbound_last_error"]
    assert settings["inbound_last_polled_at"]

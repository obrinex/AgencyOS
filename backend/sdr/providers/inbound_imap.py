"""Inbound mail by polling an IMAP mailbox.

The alternative to Cloudflare Email Routing, and the right choice when the
reply address is a real mailbox somebody also reads by hand. Routing mail to a
Worker means rewriting MX, which silently stops that mailbox receiving
anything. Polling changes nothing about how the mailbox works.

**The design constraint that follows from that:** a human is reading this
inbox. So this module is a guest in someone else's mailbox and behaves like
one — it never sets `\\Seen`, never moves anything, never deletes. Marking
messages read would quietly hide new mail from the person who owns the inbox,
which is a worse bug than anything it would fix.

Progress is tracked by IMAP UID instead, stored in SDR settings. UIDs are
monotonic within a mailbox, so "everything above the last one I saw" is exact,
and reading a message by hand does not change it.

Uses `imaplib` and `email` from the standard library: this runs on a
serverless cold start, and a new dependency costs latency on every invocation.
"""

import email
import imaplib
import logging
import os
from email import policy

logger = logging.getLogger(__name__)

PROVIDER = "imap"

#: How many messages one poll will handle. Vercel gives the whole request 60
#: seconds and the drain does other work too, so this stays well short of it.
#: A backlog drains over consecutive polls rather than timing out on one.
MAX_PER_POLL = 25

#: UIDVALIDITY changing means the server has renumbered the mailbox and old
#: UIDs mean nothing. Rare, but silently reprocessing the entire inbox because
#: of it would re-stop sequences and re-suppress addresses.
_UIDVALIDITY_KEY = "inbound_imap_uidvalidity"
_LAST_UID_KEY = "inbound_imap_last_uid"


def is_configured() -> bool:
    return bool(
        os.environ.get("IMAP_HOST")
        and os.environ.get("IMAP_USER")
        and os.environ.get("IMAP_PASSWORD")
    )


def _connect():
    host = os.environ["IMAP_HOST"]
    port = int(os.environ.get("IMAP_PORT") or 993)
    client = imaplib.IMAP4_SSL(host, port)
    client.login(os.environ["IMAP_USER"], os.environ["IMAP_PASSWORD"])
    return client


def _decode(value) -> str:
    """Header values arrive RFC 2047-encoded (=?utf-8?B?...?=) or as bytes."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    try:
        parts = email.header.decode_header(str(value))
    except Exception:
        return str(value)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out).strip()


def _body_text(message) -> str:
    """The plain-text body, preferring text/plain over stripped HTML.

    Attachments are skipped entirely - the classifier reads words, and a PDF
    would only spend tokens.
    """
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() != "text/plain":
                continue
            if "attachment" in str(part.get("Content-Disposition") or ""):
                continue
            try:
                return part.get_content()
            except Exception:
                payload = part.get_payload(decode=True) or b""
                return payload.decode("utf-8", errors="replace")
        # No text part at all: fall back to HTML with tags stripped, which is
        # crude but better than handing the classifier an empty body.
        for part in message.walk():
            if part.get_content_type() == "text/html":
                import re
                payload = part.get_payload(decode=True) or b""
                html = payload.decode("utf-8", errors="replace")
                return re.sub(r"<[^>]+>", " ", html)
        return ""
    try:
        return message.get_content()
    except Exception:
        payload = message.get_payload(decode=True) or b""
        return payload.decode("utf-8", errors="replace")


def normalize(raw: bytes) -> dict:
    """One raw RFC 822 message -> the shape the inbound service consumes.

    Identical output to `inbound_cloudflare.normalize`, which is the point:
    matching, classification and wiring never learn which transport delivered
    the mail.
    """
    message = email.message_from_bytes(raw, policy=policy.default)

    headers = {}
    for key, value in message.items():
        headers[key] = _decode(value)

    from_email = _decode(message.get("From"))
    if "<" in from_email and ">" in from_email:
        from_email = from_email.rsplit("<", 1)[1].split(">", 1)[0]

    message_id = (message.get("Message-ID") or message.get("Message-Id") or "").strip()

    return {
        "provider": PROVIDER,
        # The sender's own Message-ID is the idempotency key. Without one, a
        # message re-fetched after a failed poll would be processed twice.
        "ingest_key": message_id or None,
        "from_email": from_email.strip().lower(),
        "to_email": _decode(message.get("To")).strip().lower(),
        "subject": _decode(message.get("Subject")),
        "text_body": _body_text(message),
        "headers": headers,
        "in_reply_to": (message.get("In-Reply-To") or "").strip() or None,
        "references": (message.get("References") or "").strip() or None,
        "received_at": None,   # the service stamps arrival
    }


async def fetch_new(*, last_uid: int = 0, uidvalidity: int | None = None,
                    mailbox: str = "INBOX", limit: int = MAX_PER_POLL) -> dict:
    """Messages newer than `last_uid`, without touching their read state.

    Returns {messages, last_uid, uidvalidity, truncated}. `truncated` is true
    when the batch cap was hit, so the caller knows more is waiting rather
    than assuming the mailbox is drained.
    """
    import asyncio

    def _poll():
        client = _connect()
        try:
            # readonly=True is the guarantee: SELECT alone can clear \Recent
            # and some servers set \Seen on FETCH otherwise. This is somebody
            # else's inbox.
            status, data = client.select(mailbox, readonly=True)
            if status != "OK":
                raise RuntimeError(f"Cannot open mailbox {mailbox!r}: {data}")

            current_validity = None
            try:
                status, validity = client.status(mailbox, "(UIDVALIDITY)")
                if status == "OK" and validity:
                    text = validity[0].decode("utf-8", errors="replace")
                    current_validity = int(text.split("UIDVALIDITY")[1].strip(" ()"))
            except Exception:
                logger.warning("Could not read UIDVALIDITY; continuing")

            start = last_uid + 1
            if uidvalidity is not None and current_validity is not None \
                    and current_validity != uidvalidity:
                # The server renumbered. Old UIDs are meaningless; resuming
                # from them could replay the whole mailbox. Restart from the
                # end and accept missing a message over re-processing every
                # message - the second is far more damaging.
                logger.warning(
                    "IMAP UIDVALIDITY changed (%s -> %s); skipping to the end",
                    uidvalidity, current_validity,
                )
                status, uid_data = client.uid("search", None, "ALL")
                existing = (uid_data[0].split() if status == "OK" and uid_data[0] else [])
                newest = int(existing[-1]) if existing else 0
                return {"messages": [], "last_uid": newest,
                        "uidvalidity": current_validity, "truncated": False}

            status, uid_data = client.uid("search", None, f"UID {start}:*")
            if status != "OK":
                return {"messages": [], "last_uid": last_uid,
                        "uidvalidity": current_validity, "truncated": False}

            uids = [int(u) for u in (uid_data[0].split() if uid_data[0] else [])]
            # `UID n:*` always returns at least the newest message even when
            # nothing is newer than n, so the filter is not redundant.
            uids = sorted(u for u in uids if u > last_uid)

            truncated = len(uids) > limit
            uids = uids[:limit]

            messages, highest = [], last_uid
            for uid in uids:
                # BODY.PEEK is the half of this that actually preserves the
                # unread state; plain BODY[] would mark it read.
                status, payload = client.uid("fetch", str(uid), "(BODY.PEEK[])")
                if status != "OK" or not payload or not payload[0]:
                    continue
                raw = payload[0][1]
                try:
                    messages.append(normalize(raw))
                except Exception:
                    logger.exception("Could not parse IMAP message uid=%s", uid)
                highest = max(highest, uid)

            return {"messages": messages, "last_uid": highest,
                    "uidvalidity": current_validity, "truncated": truncated}
        finally:
            try:
                client.logout()
            except Exception:
                pass

    return await asyncio.to_thread(_poll)

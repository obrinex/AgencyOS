"""RFC 5322 threading identity for outbound mail.

Why this exists at all: a reply carries `In-Reply-To: <the id of the message
it answers>`. If we never chose that id, we cannot match an inbound reply to
the message that provoked it, and the fallback - from-address plus "probably
the most recent campaign" - breaks the moment two campaigns touch one person.

The id therefore has to be ours, and it has to be minted *before* the send,
not derived afterwards from whatever the provider happened to assign. It is
also the one thing in this module that cannot be retrofitted: mail already
sent under a provider-generated id is permanently unmatchable.

Pure functions, no I/O - the ids are deterministic from the message row, so
the same message always yields the same header whether it is being sent,
re-read, or matched against months later.
"""

import re

#: A conservative local-part. Mongo ids are hex, but a defensive strip keeps a
#: malformed id from producing a header that breaks the whole message.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def domain_of(email: str) -> str:
    """The domain half of an address, lowercased.

    The Message-ID domain is deliberately taken from the sending identity
    rather than a separate setting: a Message-ID whose domain does not match
    the envelope sender is a spam-filter signal, and keeping one source of
    truth means the two cannot drift apart.
    """
    if not email or "@" not in email:
        raise ValueError(f"Cannot derive a sending domain from {email!r}")
    return email.rsplit("@", 1)[1].strip().lower()


def message_id_for(message_id: str, sending_identity: str) -> str:
    """Mint the Message-ID header value for one outbound message.

    Deterministic - `sdr-{message_id}@{domain}` - so an inbound reply can be
    matched either by the stored header or by re-deriving it from the row.
    """
    local = _UNSAFE.sub("", str(message_id or ""))
    if not local:
        raise ValueError("A message id is required to mint a Message-ID")
    return f"<sdr-{local}@{domain_of(sending_identity)}>"


def chain(parent: dict | None) -> tuple[str | None, list]:
    """Given the message this one follows, return (in_reply_to, references).

    `references` is the parent's own chain plus the parent itself, which is
    what mail clients walk to draw a thread. A first touch has no parent and
    returns (None, []).

    A parent that was never assigned a Message-ID - anything sent before this
    module existed - is treated as no parent at all. Half a chain is worse
    than none: it points at an id the recipient's client has never seen.
    """
    if not parent:
        return None, []
    parent_id = parent.get("email_message_id")
    if not parent_id:
        return None, []
    references = list(parent.get("references") or [])
    references.append(parent_id)
    return parent_id, references


def headers(*, own_message_id: str, in_reply_to: str | None = None,
            references: list | None = None) -> dict:
    """The threading headers for one dispatch.

    Message-ID is always present. The other two appear only on follow-ups,
    because an empty `In-Reply-To` is a malformed header rather than an
    absent one.
    """
    result = {"Message-ID": own_message_id}
    if in_reply_to:
        result["In-Reply-To"] = in_reply_to
    if references:
        result["References"] = " ".join(references)
    return result

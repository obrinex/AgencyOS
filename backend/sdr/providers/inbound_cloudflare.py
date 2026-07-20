"""Inbound mail from a Cloudflare Email Routing Worker.

Cloudflare routes mail for the sending domain to a Worker; the Worker parses
the message and POSTs a small JSON envelope here. Chosen over Resend inbound
(limited), IMAP polling (fragile inside a 60s serverless ceiling) and a paid
parser (another vendor, another bill).

The transport is a plain shared secret rather than svix, because we control
both ends. Same posture as the Resend webhook regardless: **unverified is
unprocessed.** A forged inbound reply is not a nuisance — it stops a live
sequence, marks a lead as answered, and can suppress an arbitrary address
permanently. So an absent secret is a 503, not an open door.

The Worker that feeds this is documented in `docs/ai-sdr/inbound-worker.md`;
this module only trusts its signature and normalizes its shape.
"""

import hashlib
import hmac
import os
import time


PROVIDER = "cloudflare"

#: Reject anything older than this. A replayed reply would re-stop an
#: enrollment; `ingest_key` also guards that, but freshness is cheaper.
MAX_SKEW_SECONDS = 300


def is_configured() -> bool:
    return bool(os.environ.get("SDR_INBOUND_WEBHOOK_SECRET"))


def verify(*, body: bytes, timestamp: str, signature: str) -> tuple[bool, str]:
    """Constant-time HMAC-SHA256 over `{timestamp}.{body}`.

    Returns (ok, reason) rather than raising so the router owns the status
    codes, and so a rejection can be logged with a cause instead of
    disappearing into a generic 401.
    """
    secret = os.environ.get("SDR_INBOUND_WEBHOOK_SECRET", "")
    if not secret:
        return False, "not_configured"
    if not timestamp or not signature:
        return False, "missing_signature"

    try:
        age = abs(time.time() - int(timestamp))
    except (TypeError, ValueError):
        return False, "bad_timestamp"
    if age > MAX_SKEW_SECONDS:
        return False, "stale"

    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    # The Worker may send it bare or `sha256=`-prefixed; accept both.
    candidate = signature.split("=", 1)[-1].strip()
    if not hmac.compare_digest(expected, candidate):
        return False, "invalid_signature"
    return True, "ok"


def _first(headers: dict, *names: str) -> str | None:
    """Case-insensitive header lookup - Workers preserve the sender's casing."""
    lowered = {str(k).lower(): v for k, v in (headers or {}).items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return str(value)
    return None


def normalize(payload: dict) -> dict:
    """Cloudflare's envelope -> the shape the inbound service consumes.

    Kept deliberately thin and provider-named: a second transport (IMAP, a
    paid parser) becomes another module with this same output, and nothing
    downstream has to know which one delivered the mail.
    """
    headers = payload.get("headers") or {}
    from_email = (payload.get("from") or _first(headers, "From") or "").strip()
    # `From` may arrive as `Name <addr>`; the address is the part that matters.
    if "<" in from_email and ">" in from_email:
        from_email = from_email.rsplit("<", 1)[1].split(">", 1)[0]

    message_id = _first(headers, "Message-ID", "Message-Id")

    return {
        "provider": PROVIDER,
        # The sender's own Message-ID is the natural idempotency key. Falling
        # back to the Worker's id keeps a header-less message from being
        # processed once per retry.
        "ingest_key": (message_id or payload.get("id") or "").strip() or None,
        "from_email": from_email.lower(),
        "to_email": (payload.get("to") or _first(headers, "To") or "").strip().lower(),
        "subject": payload.get("subject") or _first(headers, "Subject") or "",
        "text_body": payload.get("text") or payload.get("body") or "",
        "headers": headers,
        "in_reply_to": _first(headers, "In-Reply-To"),
        "references": _first(headers, "References"),
        "received_at": payload.get("received_at"),
    }

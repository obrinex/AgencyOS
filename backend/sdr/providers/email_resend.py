"""Resend email dispatch for outreach messages.

Separate from the host's `email_service.py` on purpose, not by oversight:
that module wraps every send in the branded HTML template for transactional
mail (invoices, portal invites). Cold outreach needs the opposite - plain
text that reads as typed by a person, a per-identity from address rather
than the global SENDER_EMAIL, and the List-Unsubscribe headers Gmail and
Yahoo require of bulk senders. The transport pattern is the same one the
host uses: the sync `resend` SDK via `asyncio.to_thread`.

Text-only is the deliverability call, not a shortcut. HTML in cold email
adds tracking-shaped signals for filters and nothing for the reader; the
sole link anywhere is the unsubscribe URL in the footer.
"""

import asyncio
import logging
import os

from sdr.errors import ProviderError, QuotaExceededError, RateLimitError

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY"))


async def send(*, from_identity: str, from_label: str | None, to_email: str,
               subject: str, text_body: str, headers: dict,
               idempotency_ref: str, reply_to: str | None = None) -> dict:
    """Dispatch one message. Returns {"provider_message_id": ...}.

    Raises typed errors so the job runner can tell a retryable refusal (rate
    limit) from a permanent one. The caller has already claimed rate-limit
    slots and decided this send should happen - this function only talks to
    the wire.
    """
    import resend

    if not is_configured():
        raise QuotaExceededError(
            "RESEND_API_KEY is not set - the email provider is not configured."
        )
    resend.api_key = os.environ.get("RESEND_API_KEY")

    params = {
        "from": f"{from_label} <{from_identity}>" if from_label else from_identity,
        "to": [to_email],
        "subject": subject,
        "text": text_body,
        "headers": {
            **headers,
            # Belt-and-braces against provider-side replays. Harmless if the
            # API version ignores it; the real double-send guard is the
            # approved->sending claim in the message repository.
            "X-Entity-Ref-ID": idempotency_ref,
        },
    }
    # Sent as a top-level param rather than a header: Resend owns Reply-To and
    # would otherwise send both, which some clients resolve unpredictably.
    if reply_to:
        params["reply_to"] = reply_to

    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
    except Exception as exc:
        text = str(exc).lower()
        if "429" in text or "rate" in text:
            raise RateLimitError(f"Resend rate limit: {exc}")
        if "quota" in text or "limit" in text or "403" in text:
            raise QuotaExceededError(f"Resend refused the send: {exc}")
        raise ProviderError(f"Resend send failed: {exc}")

    provider_id = (result or {}).get("id") if isinstance(result, dict) else getattr(result, "id", None)
    if not provider_id:
        # A send without an id cannot be reconciled by webhooks later. Treat
        # as failed loudly rather than losing track of a real email.
        raise ProviderError(f"Resend returned no message id: {result!r}")
    return {"provider_message_id": provider_id}

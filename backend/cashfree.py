"""Cashfree Payments integration.

Creates hosted payment links (card / UPI / net banking / wallets) and verifies
the webhooks Cashfree sends back when one is paid.

Credentials come from the environment, never the database:
    CASHFREE_APP_ID, CASHFREE_SECRET_KEY, CASHFREE_ENV (sandbox|production)

Handles INR and USD. USD requires international payments to be enabled on the
Cashfree account; if it is not, Cashfree rejects the link and the caller falls
back to crypto rather than failing the page.
"""
import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

API_VERSION = "2023-08-01"
SANDBOX_BASE = "https://sandbox.cashfree.com/pg"
PRODUCTION_BASE = "https://api.cashfree.com/pg"

# INR is domestic; USD needs international payments active on the account.
SUPPORTED_CURRENCIES = {"INR", "USD"}

# Cashfree rejects link_id values outside this character set.
_ID_SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"


class CashfreeError(Exception):
    """Raised when Cashfree rejects a request or is unreachable."""


def app_id() -> Optional[str]:
    return (os.environ.get("CASHFREE_APP_ID") or "").strip() or None


def secret_key() -> Optional[str]:
    return (os.environ.get("CASHFREE_SECRET_KEY") or "").strip() or None


def environment() -> str:
    env = (os.environ.get("CASHFREE_ENV") or "sandbox").strip().lower()
    return "production" if env in {"production", "prod", "live"} else "sandbox"


def base_url() -> str:
    return PRODUCTION_BASE if environment() == "production" else SANDBOX_BASE


def is_configured() -> bool:
    """True when both credentials are present, so callers can degrade gracefully."""
    return bool(app_id() and secret_key())


def supports_currency(currency: Optional[str]) -> bool:
    return (currency or "INR").upper() in SUPPORTED_CURRENCIES


def _headers() -> dict:
    return {
        "x-client-id": app_id() or "",
        "x-client-secret": secret_key() or "",
        "x-api-version": API_VERSION,
        "Content-Type": "application/json",
    }


def _safe_link_id(raw: str) -> str:
    cleaned = "".join(c if c in _ID_SAFE else "_" for c in raw)
    return cleaned[:45] or "obx_link"


async def create_payment_link(
    *,
    link_id: str,
    amount: float,
    currency: str,
    purpose: str,
    customer_email: Optional[str] = None,
    customer_phone: Optional[str] = None,
    customer_name: Optional[str] = None,
    return_url: Optional[str] = None,
    notify_url: Optional[str] = None,
    expiry_days: int = 30,
) -> dict:
    """Create a Cashfree payment link and return {link_url, link_id, ...}.

    Raises CashfreeError when unconfigured, on a non-2xx response, or if the
    network call fails — callers decide how to degrade.
    """
    if not is_configured():
        raise CashfreeError("Cashfree is not configured")
    if not supports_currency(currency):
        raise CashfreeError(f"Cashfree supports {sorted(SUPPORTED_CURRENCIES)}, not {currency}")
    if amount is None or float(amount) <= 0:
        raise CashfreeError("Amount must be greater than zero")

    expiry = (datetime.now(timezone.utc) + timedelta(days=expiry_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    payload = {
        "link_id": _safe_link_id(link_id),
        "link_amount": round(float(amount), 2),
        "link_currency": (currency or "INR").upper(),
        "link_purpose": (purpose or "Payment")[:250],
        "link_expiry_time": expiry,
        "link_partial_payments": False,
        "link_notify": {"send_email": False, "send_sms": False},
        # Auto-capture: funds settle on authorisation, no manual capture step,
        # so the paid webhook is the single signal we act on.
        "link_auto_reminders": False,
        # Cashfree requires a customer_details block; phone is mandatory, so a
        # placeholder is sent when the payer is anonymous. They can correct it
        # on the hosted page before paying.
        "customer_details": {
            "customer_phone": (customer_phone or "9999999999"),
            **({"customer_email": customer_email} if customer_email else {}),
            **({"customer_name": customer_name} if customer_name else {}),
        },
    }
    meta = {}
    if return_url:
        meta["return_url"] = return_url
    if notify_url:
        meta["notify_url"] = notify_url
    if meta:
        payload["link_meta"] = meta

    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{base_url()}/links", json=payload, headers=_headers()
            ) as resp:
                body = await resp.json(content_type=None)
                if resp.status >= 400:
                    message = (body or {}).get("message") or f"HTTP {resp.status}"
                    # Never log the response wholesale — it echoes customer data.
                    logger.warning("Cashfree link creation failed: %s", message)
                    raise CashfreeError(message)
                return body
    except CashfreeError:
        raise
    except Exception as exc:  # network/timeout/parse
        logger.warning("Cashfree unreachable: %s", exc)
        raise CashfreeError("Could not reach Cashfree") from exc


async def fetch_payment_link(link_id: str) -> Optional[dict]:
    """Read a link's current state. Returns None when it does not exist."""
    if not is_configured():
        raise CashfreeError("Cashfree is not configured")
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"{base_url()}/links/{_safe_link_id(link_id)}", headers=_headers()
            ) as resp:
                if resp.status == 404:
                    return None
                body = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise CashfreeError((body or {}).get("message") or f"HTTP {resp.status}")
                return body
    except CashfreeError:
        raise
    except Exception as exc:
        raise CashfreeError("Could not reach Cashfree") from exc


def verify_webhook(raw_body: bytes, signature: str, timestamp: str) -> bool:
    """Verify a Cashfree webhook.

    Signature is base64(HMAC-SHA256(timestamp + raw_body, secret_key)). Compared
    in constant time. Returns False rather than raising so an unverified webhook
    is simply ignored.
    """
    key = secret_key()
    if not key or not signature or not timestamp:
        return False
    try:
        signed = timestamp.encode("utf-8") + raw_body
        digest = hmac.new(key.encode("utf-8"), signed, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode("utf-8")
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False

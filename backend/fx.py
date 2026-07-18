"""Live foreign-exchange rates (USD → INR and back).

Rates come from a public feed, are cached in memory for a few minutes, and are
mirrored into Mongo so a restart or an outage still has a recent number to work
with. Nothing here raises: a caller always gets a usable rate plus metadata
saying how fresh it is, because a failed lookup must never block invoicing.

Freshness note: the free feeds used here republish roughly every few minutes to
once a day, not tick-by-tick. `as_of` and `stale` tell the UI what it is
showing, so nobody mistakes a day-old rate for a live one.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from database import db

logger = logging.getLogger(__name__)

BASE_CURRENCY = "INR"
SUPPORTED = ("INR", "USD")

# How long a fetched rate is served without re-checking the feed.
CACHE_TTL_SECONDS = 15 * 60
# Beyond this a stored rate is reported as stale (still returned, but flagged).
STALE_AFTER_SECONDS = 24 * 60 * 60

# Last-resort value if a rate has never been fetched and the DB is empty. Only
# used to keep arithmetic sane; it is always reported as stale.
FALLBACK_USD_INR = float(os.environ.get("FX_FALLBACK_USD_INR") or 88.0)

_cache: dict = {}
_lock = asyncio.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _fetch_from_feeds(base: str, quote: str) -> Optional[tuple]:
    """Try each feed in turn. Returns (rate, as_of, source) or None."""
    feeds = [
        (
            "frankfurter",
            f"https://api.frankfurter.app/latest?from={base}&to={quote}",
            lambda d: (d.get("rates") or {}).get(quote),
            lambda d: d.get("date"),
        ),
        (
            "open.er-api",
            f"https://open.er-api.com/v6/latest/{base}",
            lambda d: (d.get("rates") or {}).get(quote),
            lambda d: d.get("time_last_update_utc"),
        ),
    ]
    timeout = aiohttp.ClientTimeout(total=8)
    for name, url, pick_rate, pick_date in feeds:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status >= 400:
                        continue
                    data = await resp.json(content_type=None)
            rate = pick_rate(data)
            if not rate or float(rate) <= 0:
                continue
            return float(rate), (pick_date(data) or _now().isoformat()), name
        except Exception as exc:
            logger.info("FX feed %s unavailable: %s", name, exc)
            continue
    return None


async def _read_stored(pair: str) -> Optional[dict]:
    try:
        return await db.fx_rates.find_one({"pair": pair})
    except Exception:
        return None


async def _store(pair: str, rate: float, as_of: str, source: str) -> None:
    try:
        await db.fx_rates.update_one(
            {"pair": pair},
            {"$set": {"pair": pair, "rate": rate, "as_of": as_of, "source": source,
                      "fetched_at": _now().isoformat()}},
            upsert=True,
        )
    except Exception as exc:
        logger.info("Could not persist FX rate: %s", exc)


async def get_rate(base: str = "USD", quote: str = BASE_CURRENCY, force: bool = False) -> dict:
    """Return {rate, as_of, source, stale} for base→quote. Never raises."""
    base = (base or "USD").upper()
    quote = (quote or BASE_CURRENCY).upper()
    if base == quote:
        return {"rate": 1.0, "as_of": _now().isoformat(), "source": "identity", "stale": False}

    pair = f"{base}{quote}"
    cached = _cache.get(pair)
    if cached and not force:
        age = (_now() - cached["fetched_at"]).total_seconds()
        if age < CACHE_TTL_SECONDS:
            return {k: cached[k] for k in ("rate", "as_of", "source", "stale")}

    async with _lock:
        # Another coroutine may have refreshed while we waited.
        cached = _cache.get(pair)
        if cached and not force:
            age = (_now() - cached["fetched_at"]).total_seconds()
            if age < CACHE_TTL_SECONDS:
                return {k: cached[k] for k in ("rate", "as_of", "source", "stale")}

        fetched = await _fetch_from_feeds(base, quote)
        if fetched:
            rate, as_of, source = fetched
            result = {"rate": rate, "as_of": as_of, "source": source, "stale": False}
            _cache[pair] = {**result, "fetched_at": _now()}
            await _store(pair, rate, as_of, source)
            return result

        # Feeds unreachable — fall back to the last stored value.
        stored = await _read_stored(pair)
        if stored and stored.get("rate"):
            try:
                fetched_at = datetime.fromisoformat(stored["fetched_at"])
                if fetched_at.tzinfo is None:
                    fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                stale = (_now() - fetched_at).total_seconds() > STALE_AFTER_SECONDS
            except Exception:
                stale = True
            result = {"rate": float(stored["rate"]), "as_of": stored.get("as_of"),
                      "source": f"{stored.get('source', 'cache')} (cached)", "stale": stale}
            _cache[pair] = {**result, "fetched_at": _now()}
            return result

        logger.warning("No FX rate available for %s; using fallback", pair)
        return {"rate": FALLBACK_USD_INR if pair == "USDINR" else 1.0,
                "as_of": None, "source": "fallback", "stale": True}


async def to_base_live(amount: float, currency: Optional[str]) -> float:
    """Convert an amount into the company base currency at the current rate."""
    code = (currency or BASE_CURRENCY).upper()
    if code == BASE_CURRENCY:
        return float(amount or 0)
    info = await get_rate(code, BASE_CURRENCY)
    return float(amount or 0) * float(info["rate"])


async def rate_for(currency: Optional[str]) -> float:
    """The multiplier that turns `currency` into the base currency."""
    code = (currency or BASE_CURRENCY).upper()
    if code == BASE_CURRENCY:
        return 1.0
    return float((await get_rate(code, BASE_CURRENCY))["rate"])

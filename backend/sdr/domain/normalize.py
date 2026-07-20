"""Normalisation of the messy strings providers hand us.

Every value that participates in deduplication or contact routing passes
through here first, so that "https://WWW.Acme.co.in/contact?utm_source=x",
"acme.co.in" and "Acme Dental Pvt. Ltd." collapse predictably.

Phone handling is deliberately called "best effort": libphonenumber is not a
dependency of this repo and adding one for Phase 2 is not justified. The
parser below covers the common shapes (already-E.164, national with trunk
prefix, national bare) using the dial code and national-number length supplied
by the caller from the country registry. Anything it cannot confidently parse
returns None rather than a guess, because a wrong number is worse than a
missing one - it routes a real message to a real stranger.

Pure module: no I/O, and no country literals - dial codes arrive as arguments.
"""

import re

#: Legal-form suffixes stripped before name comparison. Ordered longest-first
#: so "pvt ltd" is removed before "ltd" can match half of it.
_LEGAL_SUFFIXES = [
    "private limited", "pvt ltd", "pvt. ltd.", "pvt", "limited", "ltd",
    "llp", "llc", "l.l.c", "inc", "incorporated", "corp", "corporation",
    "gmbh", "b.v", "bv", "n.v", "nv", "s.a", "sa", "pte", "plc", "co",
    "company", "and sons", "& sons", "group", "holdings", "enterprises",
]

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")
_TRACKING_PARAMS = re.compile(r"[?#].*$")


def normalize_domain(value: str | None) -> str | None:
    """Reduce any URL or host to a bare registrable host, lowercased.

    Returns None for input that is not plausibly a domain, so a junk value
    never becomes a dedupe key that collides with other junk.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text)  # scheme
    text = text.split("/")[0]                           # path
    text = _TRACKING_PARAMS.sub("", text)               # query/fragment
    text = text.split("@")[-1]                          # user:pass@
    text = text.split(":")[0]                           # port
    text = text.strip(".")
    if text.startswith("www."):
        text = text[4:]
    # A registrable domain needs at least one dot and no whitespace.
    if "." not in text or _WS.search(text):
        return None
    if not re.fullmatch(r"[a-z0-9.-]+", text):
        return None
    return text


def normalize_name(value: str | None) -> str | None:
    """Lowercase, strip punctuation and legal suffixes, collapse whitespace."""
    if not value or not isinstance(value, str):
        return None
    text = _PUNCT.sub(" ", value.strip().lower())
    text = _WS.sub(" ", text).strip()
    if not text:
        return None
    # Strip trailing legal forms repeatedly: "Acme Pvt Ltd Co" -> "acme".
    changed = True
    while changed:
        changed = False
        for suffix in _LEGAL_SUFFIXES:
            if text.endswith(" " + suffix):
                text = text[: -(len(suffix) + 1)].strip()
                changed = True
                break
            # A name consisting only of a legal form ("Ltd") carries no
            # identity. Returning it would give every such record the same
            # name+city dedupe key and merge unrelated businesses.
            if text == suffix:
                text = ""
                changed = True
                break
    return text or None


def normalize_email(value: str | None) -> str | None:
    """Lowercase and trim. Deliberately does not validate deliverability -
    that is the email-verification provider's job, and guessing here would
    put a false `valid` on a record."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
        return None
    return text


def normalize_phone(value: str | None, dial_code: str | None = None,
                    nsn_length: int | None = None) -> str | None:
    """Best-effort E.164. Returns None when it cannot be sure.

    `dial_code` and `nsn_length` come from the country registry - this module
    knows nothing about any specific country.
    """
    if not value or not isinstance(value, str):
        return None

    raw = value.strip()
    has_plus = raw.startswith("+") or raw.startswith("00")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None

    # Already international.
    if has_plus:
        if raw.startswith("00"):
            digits = digits[2:]
        if 8 <= len(digits) <= 15:
            return "+" + digits
        return None

    if not dial_code:
        return None
    cc = dial_code.lstrip("+")

    # National number, possibly with a trunk prefix or the country code
    # repeated without a plus.
    if digits.startswith(cc) and nsn_length and len(digits) == len(cc) + nsn_length:
        return "+" + digits
    if nsn_length:
        trimmed = digits.lstrip("0")
        if len(trimmed) == nsn_length:
            return "+" + cc + trimmed
        return None

    # No length to check against - only accept an unambiguous length.
    if 8 <= len(digits) <= 12:
        return "+" + cc + digits.lstrip("0")
    return None


def normalize_city(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    text = _PUNCT.sub(" ", value.strip().lower())
    return _WS.sub(" ", text).strip() or None


def normalize_country_code(value: str | None) -> str | None:
    """Accepts an ISO-3166 alpha-2 code. Anything else returns None."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().upper()
    return text if re.fullmatch(r"[A-Z]{2}", text) else None

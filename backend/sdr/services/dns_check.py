"""DNS verification for sending domains.

Real lookups via dnspython, which is already a dependency. Sending from a
domain without SPF, DKIM and DMARC is the single most reliable way to land in
spam, and unlike most deliverability factors it is entirely within our control
and verifiable before the first send.

`ready_to_send()` is the gate: an identity that fails it cannot send at all.
That is deliberately strict. The alternative - sending anyway and warning -
burns the domain's reputation, and reputation is slow to rebuild.

Note on DKIM: a selector is required to look up the key, because DKIM records
live at `<selector>._domainkey.<domain>` and there is no way to enumerate
selectors. Resend publishes its selector when a domain is added; without one
we report `unknown` rather than guessing, since a wrong "missing" would block
a correctly configured domain.
"""

import logging

import dns.exception
import dns.resolver

logger = logging.getLogger(__name__)

#: Short, because this runs inside a request with a 60-second ceiling and a
#: dead nameserver must not consume it.
TIMEOUT_SECONDS = 4.0

PASS = "pass"
FAIL = "fail"
WARN = "warn"
UNKNOWN = "unknown"


def _resolver() -> dns.resolver.Resolver:
    resolver = dns.resolver.Resolver()
    resolver.timeout = TIMEOUT_SECONDS
    resolver.lifetime = TIMEOUT_SECONDS
    return resolver


def _query(name: str, record_type: str, _attempt: int = 1) -> list:
    try:
        answers = _resolver().resolve(name, record_type)
        return [record.to_text().strip('"') for record in answers]
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    except (dns.exception.Timeout, dns.resolver.NoNameservers) as exc:
        # One retry: a TXT query against a domain with many records
        # (google.com is the reproducible case) intermittently exceeds a 4s
        # lifetime, and a timeout here blocks activation entirely. Retried
        # rather than lengthened so the worst case stays inside the request
        # ceiling with four lookups to make.
        if _attempt < 2:
            return _query(name, record_type, _attempt + 1)
        # Distinct from "no record": a timeout means we do not know, and
        # reporting it as missing would block a correct configuration.
        raise LookupError(str(exc))


def check_mx(domain: str) -> dict:
    try:
        records = _query(domain, "MX")
    except LookupError as exc:
        return {"status": UNKNOWN, "detail": f"Lookup failed: {exc}", "records": []}
    if not records:
        return {
            "status": FAIL,
            "detail": "No MX record - this domain cannot receive replies.",
            "records": [],
        }
    return {"status": PASS, "detail": f"{len(records)} MX record(s)", "records": records}


def check_spf(domain: str) -> dict:
    try:
        records = _query(domain, "TXT")
    except LookupError as exc:
        return {"status": UNKNOWN, "detail": f"Lookup failed: {exc}", "records": []}

    spf = [r for r in records if r.lower().startswith("v=spf1")]
    if not spf:
        return {
            "status": FAIL,
            "detail": "No SPF record. Receivers cannot verify we are allowed to send.",
            "records": [],
        }
    if len(spf) > 1:
        # More than one SPF record is a permerror, and receivers treat it as
        # no SPF at all - a common and invisible misconfiguration.
        return {
            "status": FAIL,
            "detail": f"{len(spf)} SPF records found. Exactly one is allowed; "
                      "multiple records fail validation entirely.",
            "records": spf,
        }

    record = spf[0]
    if "+all" in record:
        return {
            "status": FAIL,
            "detail": "SPF ends in '+all', which authorises the entire internet "
                      "to send as this domain.",
            "records": spf,
        }
    if "-all" not in record and "~all" not in record:
        return {
            "status": WARN,
            "detail": "SPF has no '-all' or '~all' terminator, so unauthorised "
                      "senders are not rejected.",
            "records": spf,
        }
    return {"status": PASS, "detail": "SPF present and terminated", "records": spf}


def check_dkim(domain: str, selector: str | None = None) -> dict:
    if not selector:
        return {
            "status": UNKNOWN,
            "detail": "No DKIM selector configured. Add the selector your email "
                      "provider gave you when you verified this domain.",
            "records": [],
        }
    try:
        records = _query(f"{selector}._domainkey.{domain}", "TXT")
    except LookupError as exc:
        return {"status": UNKNOWN, "detail": f"Lookup failed: {exc}", "records": []}

    if not records:
        return {
            "status": FAIL,
            "detail": f"No DKIM record at {selector}._domainkey.{domain}. "
                      "Messages will not be signed.",
            "records": [],
        }
    joined = " ".join(records)
    if "p=" not in joined:
        return {"status": FAIL, "detail": "DKIM record has no public key (p=).",
                "records": records}
    if "p=;" in joined.replace(" ", ""):
        return {"status": FAIL, "detail": "DKIM public key is empty - the key was revoked.",
                "records": records}
    return {"status": PASS, "detail": "DKIM key published", "records": records}


def check_dmarc(domain: str) -> dict:
    try:
        records = _query(f"_dmarc.{domain}", "TXT")
    except LookupError as exc:
        return {"status": UNKNOWN, "detail": f"Lookup failed: {exc}", "records": []}

    dmarc = [r for r in records if r.lower().startswith("v=dmarc1")]
    if not dmarc:
        return {
            "status": FAIL,
            "detail": "No DMARC record. Gmail and Yahoo require one for bulk senders.",
            "records": [],
        }

    record = dmarc[0].lower()
    if "p=none" in record:
        # Valid, and the correct starting point - but it enforces nothing, so
        # it is a warning rather than a pass.
        return {
            "status": WARN,
            "detail": "DMARC policy is 'none' - monitoring only, nothing enforced. "
                      "Move to quarantine once reports look clean.",
            "records": dmarc,
        }
    return {"status": PASS, "detail": "DMARC published and enforcing", "records": dmarc}


def verify_domain(domain: str, dkim_selector: str | None = None) -> dict:
    """Run every check. Returns per-record results plus an overall verdict."""
    if not domain:
        return {"domain": None, "overall": FAIL, "checks": {},
                "detail": "No domain supplied"}

    checks = {
        "mx": check_mx(domain),
        "spf": check_spf(domain),
        "dkim": check_dkim(domain, dkim_selector),
        "dmarc": check_dmarc(domain),
    }

    statuses = [check["status"] for check in checks.values()]
    if FAIL in statuses:
        overall = FAIL
    elif UNKNOWN in statuses:
        overall = UNKNOWN
    elif WARN in statuses:
        overall = WARN
    else:
        overall = PASS

    return {
        "domain": domain,
        "dkim_selector": dkim_selector,
        "overall": overall,
        "checks": checks,
        "blocking": [name for name, check in checks.items() if check["status"] == FAIL],
    }


def ready_to_send(dns_result: dict) -> tuple:
    """Whether an identity's DNS permits sending. Returns (ok, reason).

    Strict on purpose: SPF, DKIM and DMARC must all be present. A domain that
    sends without them lands in spam, and the reputation damage outlasts the
    campaign that caused it.
    """
    if not dns_result:
        return False, "DNS has not been verified for this domain yet."

    checks = dns_result.get("checks") or {}
    for record in ("spf", "dkim", "dmarc"):
        status = (checks.get(record) or {}).get("status")
        if status == FAIL:
            return False, f"{record.upper()} check failed: {checks[record]['detail']}"
        if status == UNKNOWN:
            return False, (
                f"{record.upper()} could not be verified: "
                f"{checks[record]['detail']}"
            )
    return True, "DNS verified"

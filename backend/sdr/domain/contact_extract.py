"""Pull a contact email out of a fetched web page.

OpenStreetMap almost never carries an email address, so a discovered lead
arrives unreachable and scores near zero on reachability - correctly, because
an address we cannot email is worth nothing. The address is usually sitting on
the company's own contact page.

**Deterministic on purpose.** An email address is a fact, not a judgement, and
this is the one place a hallucination would be unrecoverable: a model that
invents `info@kumardental.in` produces something that looks exactly like a
real address and may belong to a stranger. Regex cannot invent an address that
was not in the page.

The rule that does most of the work is the domain match. Small business sites
routinely carry a web designer's address in the footer, a Squarespace support
address in a template, or a stock photo licence contact. Emailing any of those
is worse than having no address at all - so an address is only accepted when
it belongs to the company's own domain.
"""

import re

#: Deliberately conservative. Misses some valid exotic addresses; that is the
#: right trade when the alternative is picking up a malformed one.
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

_MAILTO = re.compile(r"mailto:([^\"'?>\s]+)", re.IGNORECASE)

#: Local parts that are never a person to contact.
_JUNK_LOCAL = (
    "noreply", "no-reply", "donotreply", "do-not-reply", "postmaster",
    "mailer-daemon", "abuse", "unsubscribe", "bounce",
)

#: Domains belonging to platforms and plugins rather than the business.
_JUNK_DOMAINS = (
    "example.com", "example.org", "domain.com", "yourdomain.com",
    "sentry.io", "wordpress.org", "wordpress.com", "wixpress.com",
    "squarespace.com", "godaddy.com", "shopify.com", "cloudflare.com",
    "google.com", "gstatic.com", "schema.org", "w3.org", "jquery.com",
)

#: Preferred first when several addresses on the company's own domain appear.
#: A general enquiries inbox is read; a named partner's address may not be.
_PREFERRED_LOCALS = (
    "info", "hello", "contact", "enquiries", "inquiries", "admin",
    "office", "reception", "mail", "sales", "bookings", "appointments",
)

#: Anything longer is a tracking blob or a base64 fragment, not an address.
_MAX_LENGTH = 100


def _plausible(address: str) -> bool:
    address = address.strip().lower()
    if not address or len(address) > _MAX_LENGTH or address.count("@") != 1:
        return False
    local, _, domain = address.partition("@")
    if not local or not domain or ".." in address:
        return False
    if any(j in local for j in _JUNK_LOCAL):
        return False
    if any(domain == j or domain.endswith("." + j) for j in _JUNK_DOMAINS):
        return False
    # Image and asset filenames routinely look like addresses once the regex
    # has eaten a surrounding path.
    if re.search(r"\.(png|jpe?g|gif|svg|webp|css|js|woff2?)$", domain):
        return False
    return True


def _root(domain: str) -> str:
    """Strip a leading www so a match is not missed on that alone."""
    domain = (domain or "").strip().lower().rstrip(".")
    return domain[4:] if domain.startswith("www.") else domain


def extract_emails(html: str, *, company_domain: str | None = None) -> list:
    """Every plausible address in the page, best first.

    Ordering: addresses on the company's own domain, general enquiry inboxes
    ahead of personal ones; then anything else that survived filtering, which
    the caller may want to show a human but should not email automatically.
    """
    if not html:
        return []

    found, seen = [], set()
    # mailto: links first - a published address, not one scraped out of prose.
    for candidate in _MAILTO.findall(html) + _EMAIL.findall(html):
        address = candidate.strip().lower().rstrip(".,;:)")
        if address in seen or not _plausible(address):
            continue
        seen.add(address)
        found.append(address)

    root = _root(company_domain) if company_domain else None

    def rank(address: str) -> tuple:
        local, _, domain = address.partition("@")
        own = bool(root) and (_root(domain) == root or _root(domain).endswith("." + root))
        preferred = local in _PREFERRED_LOCALS
        # Lower sorts first.
        return (0 if own else 1, 0 if preferred else 1, len(address))

    return sorted(found, key=rank)


def best_email(html: str, *, company_domain: str | None = None) -> str | None:
    """The one address worth writing to, or None.

    Returns None rather than a guess when nothing on the company's own domain
    is present. An address belonging to somebody else - the site's designer,
    a platform's support desk - is not a lead's contact detail, and cold
    outreach to it is a complaint waiting to happen.
    """
    if not company_domain:
        return None

    root = _root(company_domain)
    for address in extract_emails(html, company_domain=company_domain):
        domain = _root(address.partition("@")[2])
        if domain == root or domain.endswith("." + root):
            return address
    return None

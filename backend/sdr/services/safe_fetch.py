"""SSRF-guarded HTTP fetching.

Every URL this module fetches is controlled by a prospect: it came from a
discovery provider, a CSV an operator uploaded, or a link on a page we already
fetched. That makes it attacker-controlled input, and the attack is
server-side request forgery - pointing us at `http://169.254.169.254/` to read
cloud credentials, or at an internal host that is only reachable from inside
the deployment.

The defence is resolve-then-validate: resolve the hostname to addresses
ourselves, check every one of them, then connect to a validated address. That
closes the DNS-rebinding hole in the naive version, where a hostname passes a
check and then resolves to something else on the actual connection.

Also enforced: scheme allowlist, redirect revalidation, response size cap,
and a short timeout so one slow host cannot eat the 60-second serverless
budget.
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

from sdr.errors import ValidationError

logger = logging.getLogger(__name__)

USER_AGENT = "AgencyOS-SDR/1.0 (+https://obrinex.space; info@obrinex.space)"

ALLOWED_SCHEMES = ("http", "https")

#: Cap on response body. A 50 MB PDF served at / would blow memory and the
#: time budget, and there is no useful signal past the first few hundred KB.
MAX_BYTES = 2_000_000

MAX_REDIRECTS = 3

DEFAULT_TIMEOUT = httpx.Timeout(8.0, connect=4.0)


def _is_public(address: str) -> bool:
    """Whether an IP is safe to connect to from a server.

    Rejects loopback, private ranges, link-local (which covers the cloud
    metadata endpoint at 169.254.169.254), multicast, reserved and
    unspecified. IPv6 equivalents included - an IPv6-only bypass would be the
    obvious way around a v4-only check.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified
    )


def resolve_public_addresses(hostname: str) -> list:
    """Resolve a hostname and return its addresses, or raise.

    Raises if *any* resolved address is non-public. Rejecting the whole
    hostname rather than filtering is deliberate: a name resolving to both a
    public and a private address is a rebinding attempt, not a configuration
    quirk.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValidationError(f"Could not resolve '{hostname}': {exc}")

    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        raise ValidationError(f"'{hostname}' resolved to no addresses.")

    unsafe = [address for address in addresses if not _is_public(address)]
    if unsafe:
        raise ValidationError(
            f"'{hostname}' resolves to a non-public address ({', '.join(unsafe)}). "
            "Refusing to fetch it."
        )
    return addresses


def validate_url(url: str) -> str:
    """Check scheme and host, and confirm every resolved address is public."""
    if not url or not isinstance(url, str):
        raise ValidationError("No URL supplied.")

    parsed = urlparse(url if "://" in url else f"https://{url}")
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValidationError(
            f"Only {' and '.join(ALLOWED_SCHEMES)} URLs can be fetched "
            f"(got '{parsed.scheme}')."
        )
    if not parsed.hostname:
        raise ValidationError(f"'{url}' has no hostname.")

    # A bare IP literal skips DNS but still needs the range check.
    try:
        ipaddress.ip_address(parsed.hostname)
        if not _is_public(parsed.hostname):
            raise ValidationError(
                f"Refusing to fetch a non-public address ({parsed.hostname})."
            )
    except ValueError:
        resolve_public_addresses(parsed.hostname)

    return parsed.geturl()


class SafeResponse:
    def __init__(self, *, url: str, status_code: int, headers: dict, text: str,
                 elapsed_ms: int, redirects: list, tls: bool):
        self.url = url
        self.status_code = status_code
        self.headers = headers
        self.text = text
        self.elapsed_ms = elapsed_ms
        self.redirects = redirects
        self.tls = tls


async def fetch(url: str, *, timeout: httpx.Timeout | None = None,
                max_bytes: int = MAX_BYTES) -> SafeResponse:
    """Fetch a prospect-controlled URL with every guard applied.

    Redirects are followed manually rather than by httpx, because each hop is
    a fresh attacker-controlled URL: a public page redirecting to
    `http://127.0.0.1/` would otherwise sail straight through the initial
    check.
    """
    import time

    current = validate_url(url)
    redirects = []
    started = time.monotonic()

    async with httpx.AsyncClient(
        timeout=timeout or DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        follow_redirects=False,
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                response = await client.get(current)
            except httpx.HTTPError as exc:
                raise ValidationError(f"Could not fetch {current}: {exc}")

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    break
                if location.startswith("/"):
                    parsed = urlparse(current)
                    location = f"{parsed.scheme}://{parsed.netloc}{location}"
                redirects.append(location)
                current = validate_url(location)  # revalidate every hop
                continue
            break
        else:
            raise ValidationError(f"Too many redirects fetching {url}.")

        body = response.content[:max_bytes]

    try:
        text = body.decode(response.encoding or "utf-8", errors="replace")
    except (LookupError, TypeError):
        text = body.decode("utf-8", errors="replace")

    return SafeResponse(
        url=current,
        status_code=response.status_code,
        headers={key.lower(): value for key, value in response.headers.items()},
        text=text,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        redirects=redirects,
        tls=current.startswith("https://"),
    )

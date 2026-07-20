"""Provider registry - capability matching and selection.

Selection order: can it honour the filters at all, then is it configured,
then cheapest first. Priority can be overridden per deployment via
`SDR_PROVIDER_PRIORITY`, which is how you put a paid provider ahead of the
free one once the billing relationship exists.

Registration is explicit rather than auto-discovered by import scanning: an
accidental import should never start costing money.
"""

import os

from sdr.dto.filters import DiscoveryFilters
from sdr.providers.base import COMPANY_SEARCH, DataProvider
from sdr.providers.csv_import import CSVImportProvider
from sdr.providers.google_places import GooglePlacesProvider
from sdr.providers.osm_overpass import OSMOverpassProvider

_PROVIDERS: dict = {}


def register(provider: DataProvider) -> None:
    _PROVIDERS[provider.key] = provider


register(OSMOverpassProvider())
register(GooglePlacesProvider())
register(CSVImportProvider())


def get(key: str) -> DataProvider | None:
    return _PROVIDERS.get(key)


def all_providers() -> list:
    return list(_PROVIDERS.values())


def _priority_order() -> list:
    """Explicit ordering from env, highest priority first.

    Anything unlisted keeps its natural (cost-based) position after the
    listed ones.
    """
    raw = os.environ.get("SDR_PROVIDER_PRIORITY", "")
    return [key.strip() for key in raw.split(",") if key.strip()]


def select_for_search(filters: DiscoveryFilters) -> tuple:
    """Choose providers able to run this search, best first.

    Returns (selected, rejected). `rejected` carries a reason per provider so
    the UI can explain *why* Google Places was not used, rather than leaving
    the operator to guess whether it silently failed.
    """
    selected, rejected = [], []

    for provider in _PROVIDERS.values():
        if COMPANY_SEARCH not in provider.capabilities:
            continue
        if provider.key == CSVImportProvider.key:
            # File-driven; never auto-selected for a query-driven run.
            continue

        if not provider.is_configured():
            rejected.append({
                "provider": provider.key,
                "label": provider.label,
                "reason": "Not configured - no API key set.",
            })
            continue

        report = provider.supports(filters)
        if not report.supported:
            rejected.append({
                "provider": provider.key,
                "label": provider.label,
                "reason": report.reason,
            })
            continue

        selected.append((provider, report))

    priority = _priority_order()

    def sort_key(entry):
        provider, report = entry
        explicit = priority.index(provider.key) if provider.key in priority else len(priority)
        # More natively-honoured filters is better than fewer, because a
        # post-filter throws away results we may have paid for.
        return (explicit, provider.cost_per_result_usd, -len(report.native))

    selected.sort(key=sort_key)
    return selected, rejected


async def health_report() -> list:
    """Health and configuration status for every provider, for the UI."""
    report = []
    for provider in _PROVIDERS.values():
        status = await provider.health_check()
        report.append({
            "key": provider.key,
            "label": provider.label,
            "capabilities": list(provider.capabilities),
            "requires_credentials": provider.requires_credentials,
            "configured": provider.is_configured(),
            "healthy": status.healthy,
            "detail": status.detail,
            "cost_per_result_usd": provider.cost_per_result_usd,
        })
    return report


def describe() -> list:
    """Static provider metadata - no network calls, safe on a hot path."""
    return [
        {
            "key": provider.key,
            "label": provider.label,
            "capabilities": list(provider.capabilities),
            "requires_credentials": provider.requires_credentials,
            "configured": provider.is_configured(),
            "cost_per_result_usd": provider.cost_per_result_usd,
        }
        for provider in _PROVIDERS.values()
    ]

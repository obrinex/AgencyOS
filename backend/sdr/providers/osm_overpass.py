"""OpenStreetMap discovery via Overpass, with a Nominatim fallback.

This is the module's workhorse provider and the reason the SDR is useful on
day one: it needs no API key and no billing relationship. The approach is
lifted from the existing `routers/leadfinder.py`, which already works in
production - this adapter wraps that behaviour behind the `DataProvider` port
so the rest of the module never knows OSM exists.

Two operational details carried over deliberately:

- **Short timeouts.** The whole chain (geocode + up to three mirrors +
  fallback) has to fit inside the 60-second serverless ceiling. One slow
  mirror must not consume the entire budget.
- **A declared User-Agent.** OSM's usage policy requires identifying the
  client. Removing it gets the IP blocked, which would take out discovery for
  everyone on this deployment.

Data quality is genuinely mixed - OSM is crowd-sourced and often stale. That
is reflected in `SOURCE_PRECEDENCE` in the dedupe module, where osm_overpass
ranks low, so any better-sourced value overwrites it on merge.
"""

import logging
import os

import httpx

from sdr.dto.filters import DiscoveryFilters
from sdr.errors import ProviderError, ValidationError
from sdr.providers.base import (
    COMPANY_SEARCH, CapabilityReport, DataProvider, HealthStatus, Page,
)

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

OVERPASS_URLS = [
    url.strip()
    for url in os.environ.get(
        "OVERPASS_URLS",
        "https://overpass-api.de/api/interpreter,"
        "https://overpass.kumi.systems/api/interpreter,"
        "https://overpass.openstreetmap.ru/api/interpreter",
    ).split(",")
    if url.strip()
]

USER_AGENT = "AgencyOS-SDR/1.0 (info@obrinex.space)"

#: Niche -> (OSM tag filter, plain-text search term, benchmark industry key).
#: The third element is what links discovery to the ROI benchmark table - a
#: niche with no industry mapping would silently fall back to the generic
#: benchmark, so every entry sets one.
NICHES = {
    "cafe": ('["amenity"="cafe"]', "cafe", "cafe"),
    "restaurant": ('["amenity"="restaurant"]', "restaurant", "restaurant"),
    "dental_clinic": ('["amenity"="dentist"]', "dentist", "dental"),
    "medical_clinic": ('["amenity"="clinic"]', "clinic", "medical"),
    "doctor": ('["amenity"="doctors"]', "doctor", "medical"),
    "pharmacy": ('["amenity"="pharmacy"]', "pharmacy", "pharmacy"),
    "salon": ('["shop"="hairdresser"]', "hair salon", "salon"),
    "beauty": ('["shop"="beauty"]', "beauty salon", "salon"),
    "gym": ('["leisure"="fitness_centre"]', "gym", "gym"),
    "hotel": ('["tourism"="hotel"]', "hotel", "hotel"),
    "real_estate": ('["office"="estate_agent"]', "real estate agent", "real_estate"),
    "lawyer": ('["office"="lawyer"]', "lawyer", "legal"),
    "accountant": ('["office"="accountant"]', "accountant", "accounting"),
    "veterinary": ('["amenity"="veterinary"]', "veterinary clinic", "veterinary"),
    "car_repair": ('["shop"="car_repair"]', "car repair", "car_repair"),
}


class OSMOverpassProvider(DataProvider):
    key = "osm_overpass"
    label = "OpenStreetMap (Overpass)"
    requires_credentials = False
    cost_per_result_usd = 0.0
    capabilities = (COMPANY_SEARCH,)

    def supports(self, filters: DiscoveryFilters) -> CapabilityReport:
        """OSM searches a bounding box for a tag. Everything else is a
        post-filter applied to whatever comes back."""
        if not filters.geo.cities:
            return CapabilityReport(
                supported=False,
                reason="OpenStreetMap search needs at least one city to geocode.",
            )
        if not filters.industry.categories:
            return CapabilityReport(
                supported=False,
                reason="OpenStreetMap search needs a niche to map onto an OSM tag.",
            )
        unknown = [c for c in filters.industry.categories if c not in NICHES]
        if unknown:
            return CapabilityReport(
                supported=False,
                reason=f"No OpenStreetMap tag mapping for: {', '.join(unknown)}.",
            )

        active = filters.active_keys()
        native = {"geo", "industry"} & active
        return CapabilityReport(
            supported=True,
            native=native,
            post_filter=active - native,
            reason="Geo and industry are queried natively; other filters are applied afterwards.",
        )

    async def health_check(self) -> HealthStatus:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(8.0, connect=4.0),
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = await client.get(
                    NOMINATIM_URL, params={"q": "London", "format": "json", "limit": 1}
                )
            healthy = response.status_code == 200
            return HealthStatus(
                healthy=healthy,
                detail="" if healthy else f"Nominatim returned {response.status_code}",
            )
        except Exception as exc:
            return HealthStatus(healthy=False, detail=str(exc))

    async def search(self, filters: DiscoveryFilters, cursor: str | None = None) -> Page:
        report = self.supports(filters)
        if not report.supported:
            raise ValidationError(report.reason)

        niche = filters.industry.categories[0]
        city = filters.geo.cities[0]
        country_code = filters.geo.country_codes[0] if filters.geo.country_codes else None
        tag, search_term, industry = NICHES[niche]
        limit = filters.limits.max_results
        place_query = f"{city}, {country_code}" if country_code else city

        warnings = []

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"User-Agent": USER_AGENT},
        ) as client:
            place = await self._geocode(client, place_query)
            south, north, west, east = [float(x) for x in place["boundingbox"]]

            raw = await self._query_overpass(
                client, tag, (south, west, north, east), limit, warnings
            )
            source = "overpass"

            if not raw:
                warnings.append("All Overpass mirrors failed or returned nothing; used Nominatim.")
                raw = await self._query_nominatim(client, search_term, place_query, limit)
                source = "nominatim_fallback"

        if not raw:
            raise ProviderError(
                f"No results for '{niche}' in {place_query} from OpenStreetMap.",
                detail={"warnings": warnings},
            )

        items = [
            self._normalize(element, city, country_code, industry, source)
            for element in raw
        ]
        items = [item for item in items if item.get("name")]

        return Page(items=items, cost_usd=0.0, warnings=warnings)

    # -- internals -------------------------------------------------------------

    async def _geocode(self, client: httpx.AsyncClient, place_query: str) -> dict:
        try:
            response = await client.get(
                NOMINATIM_URL, params={"q": place_query, "format": "json", "limit": 1}
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach the geocoder: {exc}")
        if response.status_code != 200 or not response.json():
            raise ValidationError(
                f'Could not find "{place_query}" - check the city name.'
            )
        return response.json()[0]

    async def _query_overpass(self, client, tag, bbox, limit, warnings) -> list:
        south, west, north, east = bbox
        # `out center` gives a point for ways as well as nodes. Over-fetching
        # 3x compensates for entries with no name, which get filtered out.
        query = (
            f"[out:json][timeout:8];("
            f"node{tag}({south},{west},{north},{east});"
            f"way{tag}({south},{west},{north},{east});"
            f");out center tags {min(limit * 3, 150)};"
        )
        for url in OVERPASS_URLS:
            try:
                response = await client.post(url, content=query.encode("utf-8"))
                if response.status_code == 200:
                    return response.json().get("elements", [])
                warnings.append(f"{url} returned {response.status_code}")
            except httpx.HTTPError as exc:
                warnings.append(f"{url} unreachable: {exc}")
                logger.warning("Overpass mirror failed: %s (%s)", url, exc)
        return []

    async def _query_nominatim(self, client, search_term, place_query, limit) -> list:
        try:
            response = await client.get(
                NOMINATIM_URL,
                params={
                    "q": f"{search_term} in {place_query}", "format": "json",
                    "limit": min(limit, 25), "addressdetails": 1,
                    "extratags": 1, "namedetails": 1,
                },
            )
        except httpx.HTTPError:
            return []
        if response.status_code != 200:
            return []
        return [{"_nominatim": True, **item} for item in response.json()]

    def _normalize(self, element: dict, city: str, country_code: str | None,
                   industry: str, source: str) -> dict:
        """Vendor shape -> canonical company. Nothing OSM-specific escapes here."""
        if element.get("_nominatim"):
            tags = element.get("extratags") or {}
            name = (
                (element.get("namedetails") or {}).get("name")
                or element.get("display_name", "").split(",")[0]
            )
            provider_ref = (
                f"nominatim/{element.get('osm_type', 'place')}/"
                f"{element.get('osm_id') or element.get('place_id')}"
            )
            description = element.get("display_name")
        else:
            tags = element.get("tags") or {}
            name = tags.get("name")
            provider_ref = f"osm/{element.get('type')}/{element.get('id')}"
            description = tags.get("description")

        website = tags.get("website") or tags.get("contact:website")
        record = {
            "name": name,
            "website_url": website,
            "domain": website,  # normalised into a bare host by the repository
            "primary_email": tags.get("email") or tags.get("contact:email"),
            "phone_e164": tags.get("phone") or tags.get("contact:phone"),
            "city": tags.get("addr:city") or city,
            "postal_code": tags.get("addr:postcode"),
            "country_code": country_code,
            "industry": industry,
            "description": description,
            "facebook_url": tags.get("contact:facebook") or tags.get("facebook"),
            "instagram_url": tags.get("contact:instagram") or tags.get("instagram"),
            "discovery_source": self.key if source == "overpass" else "osm_overpass",
            "provider_ref": provider_ref,
        }
        return self.clean(record)

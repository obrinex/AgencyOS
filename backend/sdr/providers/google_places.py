"""Google Places (New) - Text Search.

Better coverage and far fresher data than OpenStreetMap, particularly for
ratings and review counts, which feed both the ROI lead estimate and the
`high_review_volume_no_response` signal.

It is **billed per request**, so unlike the OSM provider this one is gated on
a key and reports its cost honestly. With no `GOOGLE_PLACES_API_KEY` set it
reports itself unconfigured and the registry skips it - the module keeps
working on OSM alone rather than failing.

Cost note: Text Search (Pro SKU) is roughly $32 per 1,000 requests at the time
of writing, and one request returns up to 20 results. `cost_per_result_usd`
below reflects that. Verify against current Google pricing before enabling
this at volume.
"""

import logging
import os

import httpx

from sdr.dto.filters import DiscoveryFilters
from sdr.errors import ProviderError, QuotaExceededError, RateLimitError, ValidationError
from sdr.providers.base import (
    COMPANY_ENRICH, COMPANY_SEARCH, CapabilityReport, DataProvider, HealthStatus, Page,
)

logger = logging.getLogger(__name__)

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

#: Only the fields we actually store. Google bills by field mask, so asking
#: for less genuinely costs less - do not widen this casually.
FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.formattedAddress",
    "places.websiteUri", "places.nationalPhoneNumber",
    "places.internationalPhoneNumber", "places.rating",
    "places.userRatingCount", "places.primaryType", "places.addressComponents",
    "nextPageToken",
])

#: Google's own place types -> our benchmark industry keys.
TYPE_TO_INDUSTRY = {
    "cafe": "cafe", "coffee_shop": "cafe",
    "restaurant": "restaurant", "meal_takeaway": "restaurant",
    "dentist": "dental", "dental_clinic": "dental",
    "doctor": "medical", "hospital": "medical", "medical_lab": "medical",
    "pharmacy": "pharmacy", "drugstore": "pharmacy",
    "hair_salon": "salon", "beauty_salon": "salon", "spa": "salon",
    "gym": "gym", "fitness_center": "gym",
    "hotel": "hotel", "lodging": "hotel",
    "real_estate_agency": "real_estate",
    "lawyer": "legal",
    "accounting": "accounting",
    "veterinary_care": "veterinary",
    "car_repair": "car_repair",
}


class GooglePlacesProvider(DataProvider):
    key = "google_places"
    label = "Google Places"
    requires_credentials = True
    #: ~$32 per 1,000 requests, up to 20 results each.
    cost_per_result_usd = 0.0016
    capabilities = (COMPANY_SEARCH, COMPANY_ENRICH)

    def _api_key(self) -> str | None:
        return os.environ.get("GOOGLE_PLACES_API_KEY")

    def is_configured(self) -> bool:
        return bool(self._api_key())

    def supports(self, filters: DiscoveryFilters) -> CapabilityReport:
        if not self.is_configured():
            return CapabilityReport(
                supported=False,
                reason="GOOGLE_PLACES_API_KEY is not set.",
            )
        if not filters.geo.cities:
            return CapabilityReport(
                supported=False,
                reason="Google Places text search needs a city.",
            )
        if not filters.industry.categories:
            return CapabilityReport(
                supported=False,
                reason="Google Places text search needs a business category.",
            )

        active = filters.active_keys()
        # Text search takes a free-text query and a region; rating is
        # filterable natively. Everything else we apply ourselves.
        native = {"geo", "industry", "keywords"} & active
        if filters.reputation.min_google_rating is not None:
            native.add("reputation")
        return CapabilityReport(
            supported=True,
            native=native,
            post_filter=active - native,
            reason="Query and region are native; remaining filters applied afterwards.",
        )

    async def health_check(self) -> HealthStatus:
        if not self.is_configured():
            return HealthStatus(healthy=False, detail="GOOGLE_PLACES_API_KEY is not set")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0)) as client:
                response = await client.post(
                    TEXT_SEARCH_URL,
                    headers=self._headers(),
                    json={"textQuery": "coffee in London", "maxResultCount": 1},
                )
            if response.status_code == 200:
                return HealthStatus(healthy=True)
            return HealthStatus(
                healthy=False,
                detail=f"Google Places returned {response.status_code}: {response.text[:200]}",
            )
        except Exception as exc:
            return HealthStatus(healthy=False, detail=str(exc))

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key(),
            "X-Goog-FieldMask": FIELD_MASK,
        }

    async def search(self, filters: DiscoveryFilters, cursor: str | None = None) -> Page:
        report = self.supports(filters)
        if not report.supported:
            raise ValidationError(report.reason)

        category = filters.industry.categories[0]
        city = filters.geo.cities[0]
        country_code = filters.geo.country_codes[0] if filters.geo.country_codes else None
        keywords = " ".join(filters.keywords.include)
        text_query = f"{keywords} {category} in {city}".strip().replace("_", " ")

        body = {
            "textQuery": text_query,
            # Google caps a page at 20 regardless of what we ask for.
            "maxResultCount": min(filters.limits.max_results, 20),
        }
        if country_code:
            body["regionCode"] = country_code
        if filters.reputation.min_google_rating is not None:
            body["minRating"] = filters.reputation.min_google_rating
        if cursor:
            body["pageToken"] = cursor

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
                response = await client.post(TEXT_SEARCH_URL, headers=self._headers(), json=body)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach Google Places: {exc}")

        if response.status_code == 429:
            raise RateLimitError("Google Places rate limit hit.")
        if response.status_code in (402, 403):
            raise QuotaExceededError(
                f"Google Places refused the request ({response.status_code}) - "
                "check billing and API enablement."
            )
        if response.status_code != 200:
            raise ProviderError(
                f"Google Places returned {response.status_code}: {response.text[:200]}"
            )

        payload = response.json()
        places = payload.get("places", [])
        items = [self._normalize(place, city, country_code, category) for place in places]
        items = [item for item in items if item.get("name")]

        return Page(
            items=items,
            next_cursor=payload.get("nextPageToken"),
            cost_usd=round(len(places) * self.cost_per_result_usd, 4),
        )

    def _normalize(self, place: dict, city: str, country_code: str | None,
                   requested_category: str) -> dict:
        components = place.get("addressComponents") or []

        def component(kind: str) -> str | None:
            for item in components:
                if kind in (item.get("types") or []):
                    return item.get("shortText") or item.get("longText")
            return None

        website = place.get("websiteUri")
        record = {
            "name": (place.get("displayName") or {}).get("text"),
            "website_url": website,
            "domain": website,
            "phone_e164": place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber"),
            "city": component("locality") or city,
            "region_state": component("administrative_area_level_1"),
            "postal_code": component("postal_code"),
            "country_code": component("country") or country_code,
            "industry": TYPE_TO_INDUSTRY.get(place.get("primaryType"), requested_category),
            "google_place_id": place.get("id"),
            "google_rating": place.get("rating"),
            "google_review_count": place.get("userRatingCount"),
            "description": place.get("formattedAddress"),
            "discovery_source": self.key,
            "provider_ref": f"google_places/{place.get('id')}",
        }
        return self.clean(record)

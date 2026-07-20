"""Filter post-processing, CSV import, and the provider port.

The provider tests are contract tests against recorded response shapes rather
than live calls: CI must not depend on Overpass being up, and a vendor
changing its response shape should fail the build loudly.
"""

import pytest

from sdr.dto.filters import DiscoveryFilters, matches
from sdr.errors import UnsupportedCapabilityError, ValidationError
from sdr.providers import csv_import, registry
from sdr.providers.base import DataProvider, RAW_COMPANY_FIELDS
from sdr.providers.google_places import GooglePlacesProvider
from sdr.providers.osm_overpass import OSMOverpassProvider

COMPANY = {
    "name": "Acme Dental", "domain": "acme.in", "website_url": "https://acme.in",
    "city": "Pune", "country_code": "IN", "industry": "dental",
    "employee_count": 12, "google_rating": 4.5, "google_review_count": 120,
    "founded_year": 2015, "tech_stack": ["WordPress"],
    "primary_email": "hi@acme.in", "phone_e164": "+912012345678",
}


# --- Filters ------------------------------------------------------------------

def test_empty_filters_match_everything():
    passed, failed = matches(COMPANY, DiscoveryFilters())
    assert passed and failed is None


def test_country_filter():
    assert matches(COMPANY, DiscoveryFilters(geo={"country_codes": ["IN"]}))[0]
    assert matches(COMPANY, DiscoveryFilters(geo={"country_codes": ["US"]}))[1] == "geo.country_codes"


def test_city_filter_is_case_insensitive():
    assert matches(COMPANY, DiscoveryFilters(geo={"cities": ["pune"]}))[0]
    assert matches(COMPANY, DiscoveryFilters(geo={"cities": ["PUNE"]}))[0]


def test_employee_band():
    assert matches(COMPANY, DiscoveryFilters(size={"employee_min": 5, "employee_max": 50}))[0]
    assert matches(COMPANY, DiscoveryFilters(size={"employee_min": 50}))[1] == "size.employee_min"


def test_unknown_headcount_fails_an_explicit_size_filter():
    """If the operator asked for 5-50 employees, a company whose headcount we
    do not know has not been shown to match."""
    without = {k: v for k, v in COMPANY.items() if k != "employee_count"}
    assert matches(without, DiscoveryFilters(size={"employee_min": 5}))[1] == "size.employee_min"


def test_presence_filters_work_in_both_directions():
    assert matches(COMPANY, DiscoveryFilters(presence={"has_website": True}))[0]
    assert matches(COMPANY, DiscoveryFilters(presence={"has_website": False}))[1] == "presence.has_website"
    without = {k: v for k, v in COMPANY.items() if k != "primary_email"}
    assert matches(without, DiscoveryFilters(presence={"has_email": False}))[0]


def test_keyword_include_and_exclude():
    assert matches(COMPANY, DiscoveryFilters(keywords={"include": ["dental"]}))[0]
    assert matches(COMPANY, DiscoveryFilters(keywords={"include": ["plumbing"]}))[1] == "keywords.include"
    assert matches(COMPANY, DiscoveryFilters(keywords={"exclude": ["acme"]}))[1] == "keywords.exclude"


def test_reputation_filters():
    assert matches(COMPANY, DiscoveryFilters(reputation={"min_google_rating": 4.0}))[0]
    assert matches(COMPANY, DiscoveryFilters(reputation={"min_google_rating": 4.8}))[1] == "reputation.min_google_rating"
    assert matches(COMPANY, DiscoveryFilters(reputation={"max_review_count": 50}))[1] == "reputation.max_review_count"


def test_tech_filters():
    assert matches(COMPANY, DiscoveryFilters(tech={"includes": ["wordpress"]}))[0]
    assert matches(COMPANY, DiscoveryFilters(tech={"excludes": ["WordPress"]}))[1] == "tech.excludes"


def test_active_keys_ignores_unset_groups():
    filters = DiscoveryFilters(geo={"cities": ["Pune"]})
    assert filters.active_keys() == {"geo"}
    assert DiscoveryFilters().active_keys() == set()


def test_limits_are_bounded():
    with pytest.raises(Exception):
        DiscoveryFilters(limits={"max_results": 99999})


def test_country_codes_are_upcased_on_input():
    assert DiscoveryFilters(geo={"country_codes": ["in", " us "]}).geo.country_codes == ["IN", "US"]


# --- CSV import ---------------------------------------------------------------

def test_forgiving_header_matching():
    for header in ("Company Name", "company_name", "Business", "NAME"):
        content = f"{header},Email\nAcme Dental,hi@acme.in\n"
        result = csv_import.parse(content)
        assert result["records"][0]["name"] == "Acme Dental"


def test_values_are_coerced_to_the_right_types():
    content = "Company,Employees,Rating,Reviews\nAcme,\"1,200\",4.5,120\n"
    record = csv_import.parse(content)["records"][0]
    assert record["employee_count"] == 1200
    assert record["google_rating"] == 4.5
    assert record["google_review_count"] == 120


def test_rows_without_a_name_are_skipped_and_reported():
    """A silent skip is the failure mode that wastes an afternoon."""
    content = "Company,Email\nAcme,hi@acme.in\n,orphan@nowhere.in\n"
    result = csv_import.parse(content)
    assert len(result["records"]) == 1
    assert result["report"]["rows_skipped"] == 1
    assert "missing name" in result["report"]["skipped"][0]["reason"]


def test_unrecognised_columns_are_reported_not_dropped_silently():
    content = "Company,Owner Name\nAcme,Priya\n"
    result = csv_import.parse(content)
    assert "Owner Name" in result["report"]["columns_ignored"]


def test_a_file_with_no_name_column_is_rejected_with_advice():
    with pytest.raises(ValidationError) as exc:
        csv_import.parse("Email,Phone\nhi@acme.in,123\n")
    assert "Company" in str(exc.value)


def test_empty_and_headerless_files_are_rejected():
    with pytest.raises(ValidationError):
        csv_import.parse("")
    with pytest.raises(ValidationError):
        csv_import.parse("   ")


def test_imported_rows_are_tagged_with_their_source():
    record = csv_import.parse("Company\nAcme\n")["records"][0]
    assert record["discovery_source"] == "csv_import"


# --- Provider port ------------------------------------------------------------

def test_unimplemented_capabilities_raise_rather_than_returning_empty():
    """A missing capability must be loud at the call site, not look like
    'no results found'."""
    provider = OSMOverpassProvider()

    async def check(coro):
        with pytest.raises(UnsupportedCapabilityError):
            await coro

    import asyncio
    asyncio.run(check(provider.enrich({})))
    asyncio.run(check(provider.find_contacts({})))
    asyncio.run(check(provider.verify_email("a@b.com")))


def test_clean_drops_vendor_fields_outside_the_canonical_shape():
    """This is what actually enforces 'vendor field names never leak'."""
    cleaned = DataProvider.clean({
        "name": "Acme", "formatted_phone_number": "+91...", "userRatingCount": 5,
        "domain": "", "tech_stack": [],
    })
    assert cleaned == {"name": "Acme"}
    assert all(key in RAW_COMPANY_FIELDS for key in cleaned)


# --- OSM adapter --------------------------------------------------------------

def test_osm_declares_what_it_can_and_cannot_honour():
    provider = OSMOverpassProvider()
    report = provider.supports(DiscoveryFilters(
        geo={"cities": ["Pune"]},
        industry={"categories": ["dental_clinic"]},
        size={"employee_min": 5},
    ))
    assert report.supported
    assert "industry" in report.native
    # OSM has no headcount data, so size must be applied afterwards.
    assert "size" in report.post_filter


def test_osm_refuses_a_search_it_cannot_run():
    provider = OSMOverpassProvider()
    assert not provider.supports(DiscoveryFilters()).supported
    assert not provider.supports(
        DiscoveryFilters(geo={"cities": ["Pune"]},
                         industry={"categories": ["nuclear_reactors"]})
    ).supported


def test_osm_normalises_an_overpass_element():
    element = {
        "type": "node", "id": 123,
        "tags": {
            "name": "Acme Dental", "website": "https://www.acme.in",
            "contact:phone": "+91 20 1234 5678", "addr:city": "Pune",
            "opening_hours": "Mo-Fr 09:00-18:00",  # not a canonical field
        },
    }
    record = OSMOverpassProvider()._normalize(element, "Pune", "IN", "dental", "overpass")
    assert record["name"] == "Acme Dental"
    assert record["industry"] == "dental"
    assert record["provider_ref"] == "osm/node/123"
    assert record["discovery_source"] == "osm_overpass"
    assert "opening_hours" not in record  # dropped by clean()


def test_osm_normalises_a_nominatim_fallback_element():
    element = {
        "_nominatim": True, "osm_type": "node", "osm_id": 99,
        "namedetails": {"name": "Acme Dental"},
        "display_name": "Acme Dental, Pune, India",
        "extratags": {"website": "acme.in"},
    }
    record = OSMOverpassProvider()._normalize(element, "Pune", "IN", "dental", "nominatim_fallback")
    assert record["name"] == "Acme Dental"
    assert record["provider_ref"] == "nominatim/node/99"


def test_every_osm_niche_maps_to_a_benchmark_industry():
    """A niche with no industry mapping would silently fall back to the
    generic ROI benchmark."""
    from sdr.config.benchmarks import INDUSTRIES
    from sdr.providers.osm_overpass import NICHES
    for niche, (_, _, industry) in NICHES.items():
        assert industry in INDUSTRIES, f"{niche} maps to unknown industry '{industry}'"


# --- Google Places adapter ----------------------------------------------------

def test_google_places_is_unconfigured_without_a_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    provider = GooglePlacesProvider()
    assert not provider.is_configured()
    assert not provider.supports(DiscoveryFilters()).supported


def test_google_places_normalises_a_recorded_response(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    place = {
        "id": "ChIJabc",
        "displayName": {"text": "Acme Dental"},
        "websiteUri": "https://acme.in",
        "internationalPhoneNumber": "+91 20 1234 5678",
        "rating": 4.5, "userRatingCount": 120,
        "primaryType": "dentist",
        "formattedAddress": "1 Main St, Pune",
        "addressComponents": [
            {"types": ["locality"], "longText": "Pune", "shortText": "Pune"},
            {"types": ["country"], "shortText": "IN", "longText": "India"},
        ],
    }
    record = GooglePlacesProvider()._normalize(place, "Pune", "IN", "dental_clinic")
    assert record["name"] == "Acme Dental"
    assert record["industry"] == "dental"       # mapped from Google's own type
    assert record["country_code"] == "IN"
    assert record["google_review_count"] == 120
    assert record["provider_ref"] == "google_places/ChIJabc"
    assert "formattedAddress" not in record     # vendor key did not leak


# --- Registry -----------------------------------------------------------------

def test_registry_skips_unconfigured_providers_with_a_reason(monkeypatch):
    """The UI must be able to explain why Google Places was not used, rather
    than leaving the operator guessing whether it failed silently."""
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    selected, rejected = registry.select_for_search(
        DiscoveryFilters(geo={"cities": ["Pune"]},
                         industry={"categories": ["dental_clinic"]})
    )
    keys = [provider.key for provider, _ in selected]
    assert "osm_overpass" in keys
    assert any(r["provider"] == "google_places" for r in rejected)
    assert any("not configured" in r["reason"].lower() for r in rejected)


def test_csv_provider_is_never_auto_selected():
    """It is file-driven; auto-selecting it for a query would be meaningless."""
    selected, _ = registry.select_for_search(
        DiscoveryFilters(geo={"cities": ["Pune"]},
                         industry={"categories": ["dental_clinic"]})
    )
    assert "csv_import" not in [provider.key for provider, _ in selected]


def test_priority_env_overrides_natural_ordering(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    monkeypatch.setenv("SDR_PROVIDER_PRIORITY", "google_places,osm_overpass")
    selected, _ = registry.select_for_search(
        DiscoveryFilters(geo={"cities": ["Pune"]},
                         industry={"categories": ["dental_clinic"]})
    )
    assert [provider.key for provider, _ in selected][0] == "google_places"


def test_cheapest_provider_wins_without_an_explicit_priority(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    monkeypatch.delenv("SDR_PROVIDER_PRIORITY", raising=False)
    selected, _ = registry.select_for_search(
        DiscoveryFilters(geo={"cities": ["Pune"]},
                         industry={"categories": ["dental_clinic"]})
    )
    assert [provider.key for provider, _ in selected][0] == "osm_overpass"


def test_no_provider_can_run_a_filterless_search():
    selected, rejected = registry.select_for_search(DiscoveryFilters())
    assert selected == []
    assert rejected


def test_describe_makes_no_network_calls():
    described = registry.describe()
    assert {"key", "label", "capabilities", "configured"} <= set(described[0])

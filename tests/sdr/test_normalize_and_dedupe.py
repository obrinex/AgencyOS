"""Normalisation and deduplication.

Dedupe failures are expensive in a specific way: a duplicate company means
the same human receives the same pitch twice, which is the fastest route to a
spam complaint. These tests exist to keep that from regressing.
"""

import pytest

from sdr.domain import dedupe
from sdr.domain.normalize import (
    normalize_city, normalize_country_code, normalize_domain, normalize_email,
    normalize_name, normalize_phone,
)


# --- Domains ------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("https://www.acme.co.in/contact?utm_source=x", "acme.co.in"),
    ("HTTP://ACME.CO.IN", "acme.co.in"),
    ("www.acme.co.in", "acme.co.in"),
    ("acme.co.in/", "acme.co.in"),
    ("acme.co.in:8080", "acme.co.in"),
    ("user@acme.co.in", "acme.co.in"),
    ("acme.co.in#section", "acme.co.in"),
    ("  acme.co.in.  ", "acme.co.in"),
])
def test_domain_variants_collapse_to_one_value(raw, expected):
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "not a domain", "localhost", "acme", 42, "a b.com"])
def test_junk_never_becomes_a_domain(raw):
    """A junk value that became a domain would collide with other junk in the
    unique dedupe index."""
    assert normalize_domain(raw) is None


# --- Names --------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Acme Dental Pvt. Ltd.", "acme dental"),
    ("ACME DENTAL PRIVATE LIMITED", "acme dental"),
    ("Acme Dental, LLC", "acme dental"),
    ("  Acme   Dental  ", "acme dental"),
    ("Acme Dental Pvt Ltd Co", "acme dental"),
])
def test_legal_suffixes_are_stripped(raw, expected):
    assert normalize_name(raw) == expected


def test_name_normalisation_handles_empty_input():
    assert normalize_name(None) is None
    assert normalize_name("   ") is None
    assert normalize_name("Ltd") is None  # nothing left after stripping


# --- Phones -------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("+91 20 1234 5678", "+912012345678"),
    ("00912012345678", "+912012345678"),
    ("9812345678", "+919812345678"),
    ("098-1234-5678", "+919812345678"),
    ("+91-98-1234-5678", "+919812345678"),
])
def test_phone_shapes_normalise_to_e164(raw, expected):
    assert normalize_phone(raw, dial_code="+91", nsn_length=10) == expected


@pytest.mark.parametrize("raw", ["", None, "call us", "12345", "1234567890123456789"])
def test_unparseable_phones_return_none_rather_than_a_guess(raw):
    """A wrong number is worse than a missing one - it routes a real message
    to a real stranger."""
    assert normalize_phone(raw, dial_code="+91", nsn_length=10) is None


def test_national_number_needs_a_dial_code():
    assert normalize_phone("9812345678", dial_code=None) is None


def test_already_international_needs_no_country_context():
    assert normalize_phone("+442071234567") == "+442071234567"


# --- Email, city, country -----------------------------------------------------

def test_email_normalisation():
    assert normalize_email("  Info@Acme.CO.in ") == "info@acme.co.in"
    assert normalize_email("not-an-email") is None
    assert normalize_email(None) is None


def test_city_and_country_normalisation():
    assert normalize_city("  New   Delhi ") == "new delhi"
    assert normalize_country_code("in") == "IN"
    assert normalize_country_code("IND") is None
    assert normalize_country_code(None) is None


# --- Similarity ---------------------------------------------------------------

def test_similarity_is_symmetric_and_bounded():
    a, b = "acme dental", "acme dental clinic"
    assert similarity_bounded(a, b)
    assert dedupe.similarity(a, b) == dedupe.similarity(b, a)


def similarity_bounded(a, b):
    score = dedupe.similarity(a, b)
    return 0.0 <= score <= 1.0


def test_identical_names_score_one():
    assert dedupe.similarity("acme dental", "acme dental") == 1.0


def test_word_order_is_tolerated():
    """Providers disagree on ordering constantly."""
    assert dedupe.similarity("dental acme", "acme dental") > 0.5


def test_unrelated_names_score_low():
    assert dedupe.similarity("acme dental", "zenith motors") < 0.3


# --- Dedupe keys --------------------------------------------------------------

def test_domain_wins_as_the_dedupe_key():
    key = dedupe.dedupe_key({"name": "Acme", "city": "Pune", "domain": "https://www.acme.in"})
    assert key == "d:acme.in"


def test_registration_id_is_the_second_choice():
    key = dedupe.dedupe_key({"name": "Acme", "city": "Pune", "registration_id": "U123XYZ"})
    assert key == "r:u123xyz"


def test_name_and_city_are_the_last_resort():
    key = dedupe.dedupe_key({"name": "Acme Dental Pvt Ltd", "city": "Pune", "country_code": "IN"})
    assert key == "n:acme dental|pune|IN"


def test_unidentifiable_records_get_no_key():
    """They are inserted keyless rather than colliding with each other - the
    index is sparse for exactly this reason."""
    assert dedupe.dedupe_key({"name": "Acme"}) is None
    assert dedupe.dedupe_key({}) is None


# --- Duplicate detection ------------------------------------------------------

def test_same_domain_is_a_duplicate():
    is_dup, signal, confidence = dedupe.is_duplicate(
        {"domain": "acme.in"}, {"website_url": "https://www.acme.in/about"}
    )
    assert is_dup and signal == "domain" and confidence == 1.0


def test_different_domains_are_never_merged_on_name_similarity():
    """Two distinct domains is strong evidence of two distinct businesses -
    a fuzzy name match must not override it."""
    is_dup, signal, _ = dedupe.is_duplicate(
        {"domain": "acme-pune.in", "name": "Acme Dental", "city": "Pune"},
        {"domain": "acme-mumbai.in", "name": "Acme Dental", "city": "Pune"},
    )
    assert not is_dup
    assert signal == "domain_mismatch"


def test_fuzzy_name_match_in_the_same_city_is_a_duplicate():
    is_dup, signal, _ = dedupe.is_duplicate(
        {"name": "Acme Dental Pvt Ltd", "city": "Pune"},
        {"name": "Acme Dental", "city": "pune"},
    )
    assert is_dup and signal == "fuzzy_name"


def test_same_name_in_different_cities_is_not_a_duplicate():
    """Franchises. Merging these is far harder to undo than splitting them."""
    is_dup, signal, _ = dedupe.is_duplicate(
        {"name": "Apollo Pharmacy", "city": "Pune"},
        {"name": "Apollo Pharmacy", "city": "Mumbai"},
    )
    assert not is_dup and signal == "different_city"


def test_registration_id_mismatch_blocks_a_merge():
    is_dup, signal, _ = dedupe.is_duplicate(
        {"registration_id": "AAA", "name": "Acme", "city": "Pune"},
        {"registration_id": "BBB", "name": "Acme", "city": "Pune"},
    )
    assert not is_dup and signal == "registration_mismatch"


# --- Merging ------------------------------------------------------------------

def test_empty_fields_are_filled():
    merged, changes = dedupe.merge(
        {"name": "Acme", "primary_email": None, "discovery_source": "osm_overpass"},
        {"primary_email": "hi@acme.in", "discovery_source": "google_places"},
    )
    assert merged["primary_email"] == "hi@acme.in"
    assert changes[0]["reason"] == "filled_empty"


def test_verified_values_survive_an_unverified_overwrite():
    """The single most important merge rule."""
    existing = {
        "primary_email": "real@acme.in", "email_verification_status": "valid",
        "discovery_source": "osm_overpass",
    }
    incoming = {"primary_email": "guess@acme.in", "discovery_source": "manual"}
    merged, changes = dedupe.merge(existing, incoming)
    assert merged["primary_email"] == "real@acme.in"
    assert any(c["reason"] == "kept_verified_over_unverified" for c in changes)


def test_higher_precedence_source_wins():
    merged, _ = dedupe.merge(
        {"name": "Acme Ltd", "discovery_source": "osm_overpass"},
        {"name": "Acme Dental", "discovery_source": "manual"},
    )
    assert merged["name"] == "Acme Dental"


def test_lower_precedence_source_loses():
    merged, _ = dedupe.merge(
        {"name": "Acme Dental", "discovery_source": "manual"},
        {"name": "Acme Ltd", "discovery_source": "osm_overpass"},
    )
    assert merged["name"] == "Acme Dental"


def test_equal_precedence_keeps_the_existing_value():
    """Discovery reruns must be stable, not flap between equal sources."""
    merged, _ = dedupe.merge(
        {"name": "First", "discovery_source": "google_places"},
        {"name": "Second", "discovery_source": "google_places"},
    )
    assert merged["name"] == "First"


def test_merge_never_mutates_its_inputs():
    existing = {"name": "Acme", "discovery_source": "osm_overpass"}
    incoming = {"name": "Acme Dental", "discovery_source": "manual"}
    dedupe.merge(existing, incoming)
    assert existing["name"] == "Acme"


def test_immutable_fields_are_not_merged():
    merged, _ = dedupe.merge(
        {"id": "1", "created_at": "old", "dedupe_key": "d:a.in", "discovery_source": "manual"},
        {"id": "2", "created_at": "new", "dedupe_key": "d:b.in", "discovery_source": "manual"},
    )
    assert merged["id"] == "1"
    assert merged["created_at"] == "old"
    assert merged["dedupe_key"] == "d:a.in"


# --- Batch dedupe -------------------------------------------------------------

def test_batch_collapses_duplicates_and_reports_the_count():
    records = [
        {"name": "Acme Dental", "city": "Pune", "domain": "acme.in", "discovery_source": "osm_overpass"},
        {"name": "Acme Dental Pvt Ltd", "city": "Pune", "website_url": "https://www.acme.in", "discovery_source": "google_places"},
        {"name": "Zenith Motors", "city": "Pune", "domain": "zenith.in", "discovery_source": "osm_overpass"},
    ]
    unique, dropped = dedupe.dedupe_batch(records)
    assert len(unique) == 2
    assert dropped == 1


def test_batch_merges_rather_than_discarding_the_duplicate():
    records = [
        {"name": "Acme", "domain": "acme.in", "discovery_source": "osm_overpass"},
        {"name": "Acme", "domain": "acme.in", "primary_email": "hi@acme.in", "discovery_source": "google_places"},
    ]
    unique, _ = dedupe.dedupe_batch(records)
    assert unique[0]["primary_email"] == "hi@acme.in"


def test_empty_batch():
    assert dedupe.dedupe_batch([]) == ([], 0)

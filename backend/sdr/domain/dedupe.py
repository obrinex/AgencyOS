"""Multi-signal deduplication and field-level merging.

Discovery runs the same city and niche repeatedly, and providers overlap
heavily, so the same business arrives many times wearing different names.
Getting this wrong is expensive in a specific way: a duplicate company means
the same human receives the same pitch twice, which is the fastest route to a
spam complaint.

Matching order, per spec section 5.3:
  1. normalised domain, exact
  2. registration id, exact
  3. fuzzy name similarity >= 0.85 AND same city

Merging is field-level with source precedence. The rule that matters:
**never overwrite a verified value with an unverified one.**

Pure module: no I/O.
"""

from sdr.domain.normalize import (
    normalize_city, normalize_country_code, normalize_domain, normalize_name,
)

#: Name similarity above which two businesses in the same city are considered
#: the same. 0.85 is the spec's figure. Raising it splits genuine duplicates;
#: lowering it merges distinct franchises ("Apollo Pharmacy Kothrud" vs
#: "Apollo Pharmacy Baner"), which is the worse failure - a merge is far
#: harder to undo than a split.
NAME_SIMILARITY_THRESHOLD = 0.85

#: How much a value from each source is trusted, high wins. Used only to
#: break ties between two values that are both present.
SOURCE_PRECEDENCE = {
    "manual": 100,        # a human typed it
    "csv_import": 90,     # the operator supplied it deliberately
    "registry": 80,       # government/company registry
    "google_places": 70,
    "clearbit": 65,
    "apollo": 60,
    "osm_overpass": 40,   # crowd-sourced, frequently stale
    "web_scraper": 30,
    "inferred": 10,       # derived, not observed
}

#: Fields that carry a verification status. A verified value is never
#: overwritten by an unverified one regardless of source precedence.
VERIFIED_FLAGS = {
    "primary_email": "email_verification_status",
    "phone_e164": "phone_verification_status",
}


def _trigrams(text: str) -> set:
    padded = f"  {text} "
    return {padded[i:i + 3] for i in range(len(padded) - 2)}


def similarity(left: str | None, right: str | None) -> float:
    """Trigram Jaccard similarity of two already-normalised names, 0.0-1.0.

    Trigrams rather than edit distance because they tolerate word reordering
    ("dental acme" vs "acme dental"), which is common across providers.
    """
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    a, b = _trigrams(left), _trigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedupe_key(company: dict) -> str | None:
    """The unique key stored on `sdr_companies.dedupe_key`.

    Returns None when there is not enough to identify the business at all -
    such a record is inserted without a key rather than colliding with every
    other unidentifiable record (the index is sparse for this reason).
    """
    domain = normalize_domain(company.get("domain") or company.get("website_url"))
    if domain:
        return f"d:{domain}"

    registration = (company.get("registration_id") or "").strip().lower()
    if registration:
        return f"r:{registration}"

    name = normalize_name(company.get("name"))
    city = normalize_city(company.get("city"))
    country = normalize_country_code(company.get("country_code"))
    if name and city:
        return f"n:{name}|{city}|{country or ''}"
    return None


def is_duplicate(left: dict, right: dict) -> tuple:
    """Whether two company records describe the same business.

    Returns (is_duplicate, signal, confidence) so the merge audit can record
    *why* two records were joined - a fuzzy merge deserves more scrutiny later
    than an exact domain match.
    """
    left_domain = normalize_domain(left.get("domain") or left.get("website_url"))
    right_domain = normalize_domain(right.get("domain") or right.get("website_url"))
    if left_domain and right_domain:
        if left_domain == right_domain:
            return True, "domain", 1.0
        # Two different domains is strong evidence of two different
        # businesses, so stop here rather than letting a fuzzy name match
        # override it.
        return False, "domain_mismatch", 1.0

    left_reg = (left.get("registration_id") or "").strip().lower()
    right_reg = (right.get("registration_id") or "").strip().lower()
    if left_reg and right_reg:
        if left_reg == right_reg:
            return True, "registration_id", 1.0
        return False, "registration_mismatch", 1.0

    left_city = normalize_city(left.get("city"))
    right_city = normalize_city(right.get("city"))
    if not left_city or not right_city or left_city != right_city:
        return False, "different_city", 0.0

    score = similarity(normalize_name(left.get("name")), normalize_name(right.get("name")))
    if score >= NAME_SIMILARITY_THRESHOLD:
        return True, "fuzzy_name", round(score, 3)
    return False, "no_match", round(score, 3)


def _is_verified(record: dict, field: str) -> bool:
    flag = VERIFIED_FLAGS.get(field)
    if not flag:
        return False
    return record.get(flag) in ("valid", "verified")


def _precedence(record: dict) -> int:
    return SOURCE_PRECEDENCE.get(record.get("discovery_source"), 0)


def merge(existing: dict, incoming: dict) -> tuple:
    """Field-level merge of a newly discovered record into a stored one.

    Returns (merged, changes). `changes` is the merge audit - which fields
    moved, from what to what, and why - so a bad merge can be diagnosed
    rather than guessed at.

    Rules, in order:
      1. A field absent from the existing record is always filled.
      2. A verified value is never replaced by an unverified one.
      3. Otherwise the higher-precedence source wins.
      4. Equal precedence keeps the existing value - discovery should be
         stable across reruns, not flap between two equally-trusted sources.
    """
    merged = dict(existing)
    changes = []

    existing_rank = _precedence(existing)
    incoming_rank = _precedence(incoming)

    for field, new_value in incoming.items():
        if field in ("_id", "id", "created_at", "dedupe_key", "discovery_source"):
            continue
        if new_value is None or new_value == "" or new_value == []:
            continue

        old_value = merged.get(field)

        if old_value is None or old_value == "" or old_value == []:
            merged[field] = new_value
            changes.append({"field": field, "from": old_value, "to": new_value, "reason": "filled_empty"})
            continue

        if old_value == new_value:
            continue

        if _is_verified(existing, field) and not _is_verified(incoming, field):
            changes.append({
                "field": field, "from": old_value, "to": old_value,
                "reason": "kept_verified_over_unverified",
            })
            continue

        if incoming_rank > existing_rank:
            merged[field] = new_value
            changes.append({
                "field": field, "from": old_value, "to": new_value,
                "reason": f"higher_precedence_source({incoming.get('discovery_source')})",
            })
        else:
            changes.append({
                "field": field, "from": old_value, "to": old_value,
                "reason": "kept_existing_equal_or_higher_precedence",
            })

    return merged, changes


def dedupe_batch(records: list) -> tuple:
    """Collapse duplicates within a single discovery batch.

    Providers return overlapping results, and inserting them one at a time
    would mean N round trips discovering the same collisions. Returns
    (unique_records, dropped_count).
    """
    unique = []
    dropped = 0
    for record in records:
        match_index = None
        for index, kept in enumerate(unique):
            duplicate, _, _ = is_duplicate(kept, record)
            if duplicate:
                match_index = index
                break
        if match_index is None:
            unique.append(record)
        else:
            unique[match_index], _ = merge(unique[match_index], record)
            dropped += 1
    return unique, dropped

"""Company persistence, including the upsert-with-merge path.

The interesting method is `upsert_many`: discovery re-runs the same searches
constantly, so most of what arrives already exists. Every incoming record is
matched against storage by dedupe key and merged field-by-field rather than
overwritten, so a verified email gathered last week is not clobbered by a
blank from OpenStreetMap today.
"""

from database import db, now_iso, serialize_doc, serialize_list
from sdr.collections import COMPANIES
from sdr.domain import dedupe
from sdr.domain.normalize import (
    normalize_city, normalize_country_code, normalize_domain, normalize_email,
    normalize_name, normalize_phone,
)
from sdr.config.countries import get_country
from sdr.repositories.base import get_or_404, object_id, paginate, scope, stamp_create, stamp_update


def normalize_record(record: dict) -> dict:
    """Canonicalise a provider record before it touches storage.

    Phone normalisation needs the country's dial code, which is why this sits
    in the repository rather than the domain layer - it is the seam where
    configuration and data meet.
    """
    normalized = dict(record)

    domain = normalize_domain(record.get("domain") or record.get("website_url"))
    if domain:
        normalized["domain"] = domain
        normalized.setdefault("website_url", f"https://{domain}")
    else:
        normalized.pop("domain", None)

    country_code = normalize_country_code(record.get("country_code"))
    if country_code:
        normalized["country_code"] = country_code
    else:
        normalized.pop("country_code", None)

    country = get_country(country_code)
    phone = normalize_phone(
        record.get("phone_e164"), country.get("phone_code"), country.get("phone_nsn_length")
    )
    if phone:
        normalized["phone_e164"] = phone
    else:
        normalized.pop("phone_e164", None)

    email = normalize_email(record.get("primary_email"))
    if email:
        normalized["primary_email"] = email
        normalized.setdefault("email_verification_status", "unknown")
    else:
        normalized.pop("primary_email", None)

    if record.get("city"):
        normalized["city"] = str(record["city"]).strip()
    if record.get("name"):
        normalized["name"] = str(record["name"]).strip()

    # Stored for search and dedupe; the display value keeps its original case.
    normalized["name_normalized"] = normalize_name(normalized.get("name"))
    normalized["city_normalized"] = normalize_city(normalized.get("city"))
    normalized["timezone"] = normalized.get("timezone") or (country.get("timezones") or [None])[0]
    normalized["dedupe_key"] = dedupe.dedupe_key(normalized)
    return normalized


async def find_by_dedupe_key(key: str) -> dict | None:
    if not key:
        return None
    return await db[COMPANIES].find_one(scope({"dedupe_key": key}))


async def upsert_many(records: list, *, discovery_run_id: str | None = None) -> dict:
    """Insert new companies, merge into existing ones.

    Returns counts plus the merge audit, so a discovery run can report what it
    actually changed rather than just how many rows it touched.
    """
    normalized = [normalize_record(record) for record in records]
    unique, dropped_in_batch = dedupe.dedupe_batch(normalized)

    inserted, merged, unchanged = 0, 0, 0
    merge_log = []
    company_ids = []

    for record in unique:
        key = record.get("dedupe_key")
        existing = await find_by_dedupe_key(key) if key else None

        if not existing:
            doc = dict(record)
            doc.update({
                "enrichment_status": "pending",
                "discovery_run_id": discovery_run_id,
                "first_seen_at": now_iso(),
                "last_enriched_at": None,
                "data_quality_score": _data_quality(record),
            })
            stamp_create(doc)
            result = await db[COMPANIES].insert_one(doc)
            company_ids.append(str(result.inserted_id))
            inserted += 1
            continue

        combined, changes = dedupe.merge(serialize_doc(existing), record)
        company_ids.append(str(existing["_id"]))

        if not changes:
            unchanged += 1
            continue

        patch = {
            key_: value for key_, value in combined.items()
            if key_ not in ("id", "_id", "created_at")
        }
        patch["data_quality_score"] = _data_quality(combined)
        await db[COMPANIES].update_one(
            {"_id": existing["_id"]}, {"$set": stamp_update(patch)}
        )
        merged += 1
        merge_log.append({
            "company_id": str(existing["_id"]),
            "name": combined.get("name"),
            "changes": changes,
        })

    return {
        "inserted": inserted,
        "merged": merged,
        "unchanged": unchanged,
        "deduped_in_batch": dropped_in_batch,
        "company_ids": company_ids,
        # Enough to diagnose a bad merge without flooding the response.
        "merge_log": merge_log[:25],
    }


def _data_quality(record: dict) -> float:
    """How complete a company record is, 0.0-1.0.

    Feeds the scoring layer's data_quality component - a lead we know nothing
    about cannot be personalised to, so completeness is genuinely predictive.
    """
    fields = (
        "name", "domain", "industry", "city", "country_code",
        "phone_e164", "primary_email", "description",
        "google_rating", "employee_count",
    )
    present = sum(1 for field in fields if record.get(field))
    return round(present / len(fields), 3)


async def list_companies(*, search: str | None = None, industry: str | None = None,
                         country_code: str | None = None,
                         enrichment_status: str | None = None,
                         has_website: bool | None = None,
                         limit: int = 50, cursor: str | None = None) -> dict:
    query = {}
    if industry:
        query["industry"] = industry
    if country_code:
        query["country_code"] = country_code.upper()
    if enrichment_status:
        query["enrichment_status"] = enrichment_status
    if has_website is not None:
        query["domain"] = {"$ne": None} if has_website else None
    if search:
        # Regex rather than the text index because this is a prefix/substring
        # search as the user types, which $text does not do.
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"domain": {"$regex": search, "$options": "i"}},
        ]
    return await paginate(
        COMPANIES, scope(query), sort=("created_at", -1), limit=limit, cursor=cursor
    )


async def get_company(company_id: str) -> dict:
    return await get_or_404(COMPANIES, company_id, "company")


async def update_company(company_id: str, patch: dict) -> dict:
    await db[COMPANIES].update_one(
        scope({"_id": object_id(company_id, "company id")}),
        {"$set": stamp_update(patch)},
    )
    return await get_company(company_id)


async def count_companies(query: dict | None = None) -> int:
    return await db[COMPANIES].count_documents(scope(query or {}))


async def companies_by_ids(ids: list) -> list:
    if not ids:
        return []
    object_ids = [object_id(value, "company id") for value in ids]
    docs = await db[COMPANIES].find(scope({"_id": {"$in": object_ids}})).to_list(len(ids))
    return serialize_list(docs)

"""CSV / spreadsheet import, treated as a first-class provider.

The spec calls for this explicitly so the system is useful on day one with
zero paid API keys. It is also the escape hatch for every market where no
provider has decent coverage - an operator exports a list from anywhere and
it enters the same pipeline as an API result, with the same dedupe, scoring
and compliance checks.

Column matching is forgiving because real spreadsheets are: "Company Name",
"company_name", "Business", and "Name" all mean the same thing. Anything
unrecognised is reported back rather than silently dropped, so a mis-mapped
export is visible before 1,000 rows land in the database.
"""

import csv
import io

from sdr.dto.filters import DiscoveryFilters
from sdr.errors import ValidationError
from sdr.providers.base import COMPANY_SEARCH, CapabilityReport, DataProvider

#: Canonical field -> accepted header aliases, all compared lowercased with
#: non-alphanumerics stripped.
COLUMN_ALIASES = {
    "name": ["name", "company", "companyname", "business", "businessname", "organisation", "organization"],
    "domain": ["domain", "website", "websiteurl", "url", "site", "webaddress"],
    "website_url": ["websiteurl", "website", "url"],
    "primary_email": ["email", "emailaddress", "primaryemail", "contactemail", "mail"],
    "phone_e164": ["phone", "phonenumber", "mobile", "contactnumber", "telephone", "tel", "contact"],
    "city": ["city", "town", "location", "locality"],
    "region_state": ["state", "region", "province"],
    "country_code": ["country", "countrycode", "countryiso"],
    "postal_code": ["postalcode", "postcode", "zip", "zipcode", "pincode", "pin"],
    "industry": ["industry", "category", "niche", "sector", "vertical", "type"],
    "employee_count": ["employees", "employeecount", "headcount", "staff", "teamsize"],
    "revenue_estimate": ["revenue", "turnover", "annualrevenue"],
    "founded_year": ["founded", "foundedyear", "yearfounded", "established"],
    "registration_id": ["registrationid", "cin", "gstin", "ein", "companynumber", "taxid"],
    "linkedin_url": ["linkedin", "linkedinurl", "linkedinprofile"],
    "instagram_url": ["instagram", "instagramurl", "ig"],
    "facebook_url": ["facebook", "facebookurl", "fb"],
    "google_rating": ["rating", "googlerating", "stars"],
    "google_review_count": ["reviews", "reviewcount", "googlereviews", "numreviews"],
    "description": ["description", "about", "notes", "summary"],
}

#: The one field without which a row is meaningless.
REQUIRED_FIELDS = ("name",)

MAX_ROWS = 10_000

_INT_FIELDS = ("employee_count", "founded_year", "google_review_count")
_FLOAT_FIELDS = ("revenue_estimate", "google_rating")


def _canonical(header: str) -> str:
    return "".join(ch for ch in (header or "").lower() if ch.isalnum())


def build_column_map(headers: list) -> tuple:
    """Map spreadsheet headers onto canonical fields.

    Returns (mapping, unmapped_headers). Unmapped headers are reported so the
    operator can see that their "Owner Name" column was ignored, rather than
    wondering later why the data is not there.
    """
    lookup = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            lookup.setdefault(alias, field)

    mapping, unmapped = {}, []
    for header in headers:
        canonical = _canonical(header)
        field = lookup.get(canonical)
        if field and field not in mapping.values():
            mapping[header] = field
        elif field:
            # A second column claiming the same field - keep the first and
            # report the loser rather than overwriting.
            unmapped.append(header)
        else:
            unmapped.append(header)
    return mapping, unmapped


def _coerce(field: str, value: str):
    text = (value or "").strip()
    if not text:
        return None
    if field in _INT_FIELDS:
        try:
            return int(float(text.replace(",", "")))
        except ValueError:
            return None
    if field in _FLOAT_FIELDS:
        try:
            return float(text.replace(",", ""))
        except ValueError:
            return None
    return text


def parse(content: str, column_map: dict | None = None) -> dict:
    """Parse CSV text into canonical company records.

    Returns the records plus a report: how many rows were read, skipped and
    why. A silent skip is the failure mode that wastes an afternoon, so every
    dropped row is accounted for.
    """
    if not content or not content.strip():
        raise ValidationError("The file is empty.")

    try:
        reader = csv.DictReader(io.StringIO(content))
        headers = reader.fieldnames or []
    except csv.Error as exc:
        raise ValidationError(f"Could not read the CSV: {exc}")

    if not headers:
        raise ValidationError("The file has no header row.")

    mapping, unmapped = (column_map, []) if column_map else build_column_map(headers)

    if "name" not in mapping.values():
        raise ValidationError(
            "No company-name column found. Name one of your columns "
            "'Company', 'Business' or 'Name'."
        )

    records, skipped = [], []
    for index, row in enumerate(reader, start=2):  # row 1 is the header
        if len(records) >= MAX_ROWS:
            skipped.append({"row": index, "reason": f"file exceeds the {MAX_ROWS:,}-row limit"})
            break

        record = {}
        for header, field in mapping.items():
            coerced = _coerce(field, row.get(header))
            if coerced is not None:
                record[field] = coerced

        missing = [f for f in REQUIRED_FIELDS if not record.get(f)]
        if missing:
            skipped.append({"row": index, "reason": f"missing {', '.join(missing)}"})
            continue

        record["discovery_source"] = CSVImportProvider.key
        records.append(record)

    return {
        "records": records,
        "report": {
            "rows_read": len(records) + len(skipped),
            "rows_accepted": len(records),
            "rows_skipped": len(skipped),
            "skipped": skipped[:50],  # enough to diagnose, not enough to flood
            "columns_mapped": mapping,
            "columns_ignored": unmapped,
        },
    }


class CSVImportProvider(DataProvider):
    """Registered as a provider so imported rows follow the same path as API
    results - same normalisation, same dedupe, same audit trail."""

    key = "csv_import"
    label = "CSV / Spreadsheet import"
    requires_credentials = False
    cost_per_result_usd = 0.0
    capabilities = (COMPANY_SEARCH,)

    def supports(self, filters: DiscoveryFilters) -> CapabilityReport:
        # Import is driven by a file, not a filter set. Filters still apply as
        # a post-filter, which is how an operator imports a broad export and
        # keeps only the rows matching their ICP.
        return CapabilityReport(
            supported=True,
            native=set(),
            post_filter=filters.active_keys(),
            reason="Rows come from the uploaded file; every filter is applied afterwards.",
        )

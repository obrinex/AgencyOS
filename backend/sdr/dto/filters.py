"""DiscoveryFilters - the single source of truth for what a search can ask for.

The UI filter panel is generated from `describe()` below, so adding a filter
means editing this file and mapping it in the providers that can honour it.
No frontend rewrite, per spec section 5.1.

Providers rarely support everything. Each declares what it can do natively
via `supports()`; the discovery service applies the remainder as a post-filter
and the run report states which was which - so a result set is never silently
narrower than the user believes.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class GeoFilter(BaseModel):
    country_codes: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    radius_km: Optional[float] = Field(default=None, ge=0, le=500)
    center_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    center_lng: Optional[float] = Field(default=None, ge=-180, le=180)

    @field_validator("country_codes")
    @classmethod
    def _upper(cls, value):
        return [v.strip().upper() for v in value if v and v.strip()]


class IndustryFilter(BaseModel):
    categories: list[str] = Field(default_factory=list)
    sub_categories: list[str] = Field(default_factory=list)
    classification_system: Optional[Literal["nic", "naics", "sic", "provider"]] = None


class KeywordFilter(BaseModel):
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    match_in: list[Literal["name", "description", "website"]] = Field(
        default_factory=lambda: ["name", "description"]
    )


class SizeFilter(BaseModel):
    employee_min: Optional[int] = Field(default=None, ge=0)
    employee_max: Optional[int] = Field(default=None, ge=0)
    revenue_min: Optional[float] = Field(default=None, ge=0)
    revenue_max: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None


class PresenceFilter(BaseModel):
    """Presence filters are the ones that matter most for this product - a
    business with no website cannot have a website gap detected."""
    has_website: Optional[bool] = None
    has_email: Optional[bool] = None
    has_phone: Optional[bool] = None
    has_instagram: Optional[bool] = None
    has_facebook: Optional[bool] = None
    has_linkedin: Optional[bool] = None


class ReputationFilter(BaseModel):
    min_google_rating: Optional[float] = Field(default=None, ge=0, le=5)
    min_review_count: Optional[int] = Field(default=None, ge=0)
    max_review_count: Optional[int] = Field(default=None, ge=0)


class TechFilter(BaseModel):
    includes: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)


class AgeFilter(BaseModel):
    founded_after: Optional[int] = Field(default=None, ge=1800, le=2200)
    founded_before: Optional[int] = Field(default=None, ge=1800, le=2200)


class LimitsFilter(BaseModel):
    #: Hard ceiling. Discovery is paid per result on most providers, so an
    #: unbounded run is a way to spend real money by accident.
    max_results: int = Field(default=50, ge=1, le=1000)
    max_cost_usd: float = Field(default=1.0, ge=0, le=100)
    #: Skip re-fetching a company seen more recently than this.
    freshness_days: Optional[int] = Field(default=None, ge=0, le=365)


class DiscoveryFilters(BaseModel):
    geo: GeoFilter = Field(default_factory=GeoFilter)
    industry: IndustryFilter = Field(default_factory=IndustryFilter)
    keywords: KeywordFilter = Field(default_factory=KeywordFilter)
    size: SizeFilter = Field(default_factory=SizeFilter)
    presence: PresenceFilter = Field(default_factory=PresenceFilter)
    reputation: ReputationFilter = Field(default_factory=ReputationFilter)
    tech: TechFilter = Field(default_factory=TechFilter)
    age: AgeFilter = Field(default_factory=AgeFilter)
    limits: LimitsFilter = Field(default_factory=LimitsFilter)
    custom: dict = Field(default_factory=dict)

    def active_keys(self) -> set:
        """Which filter groups the caller actually set.

        Used to work out what a provider must honour - an unset group is not
        a constraint and should not count against a provider's capability
        match.
        """
        active = set()
        for name in ("geo", "industry", "keywords", "size", "presence",
                     "reputation", "tech", "age"):
            group = getattr(self, name)
            dumped = group.model_dump(exclude_defaults=True, exclude_none=True)
            if any(v for v in dumped.values()):
                active.add(name)
        return active


def matches(company: dict, filters: DiscoveryFilters) -> tuple:
    """Post-filter a single company against the full filter set.

    Applied to results from providers that could not honour a filter natively.
    Returns (passed, failed_filter_name) so a discovery run can report *why*
    results were dropped rather than just how many.
    """
    geo = filters.geo
    if geo.country_codes and company.get("country_code") not in geo.country_codes:
        return False, "geo.country_codes"
    if geo.cities:
        wanted = {c.strip().lower() for c in geo.cities}
        if (company.get("city") or "").strip().lower() not in wanted:
            return False, "geo.cities"

    industry = filters.industry
    if industry.categories and company.get("industry") not in industry.categories:
        return False, "industry.categories"

    keywords = filters.keywords
    if keywords.include or keywords.exclude:
        haystack = " ".join(
            str(company.get(field) or "")
            for field in ("name", "description", "website_url")
        ).lower()
        if keywords.include and not any(k.lower() in haystack for k in keywords.include):
            return False, "keywords.include"
        if any(k.lower() in haystack for k in keywords.exclude):
            return False, "keywords.exclude"

    size = filters.size
    employees = company.get("employee_count")
    if size.employee_min is not None:
        if employees is None or employees < size.employee_min:
            return False, "size.employee_min"
    if size.employee_max is not None:
        if employees is None or employees > size.employee_max:
            return False, "size.employee_max"

    presence = filters.presence
    presence_fields = {
        "has_website": "website_url", "has_email": "primary_email",
        "has_phone": "phone_e164", "has_instagram": "instagram_url",
        "has_facebook": "facebook_url", "has_linkedin": "linkedin_url",
    }
    for flag, field in presence_fields.items():
        wanted = getattr(presence, flag)
        if wanted is None:
            continue
        if bool(company.get(field)) != wanted:
            return False, f"presence.{flag}"

    reputation = filters.reputation
    rating = company.get("google_rating")
    reviews = company.get("google_review_count")
    if reputation.min_google_rating is not None:
        if rating is None or rating < reputation.min_google_rating:
            return False, "reputation.min_google_rating"
    if reputation.min_review_count is not None:
        if reviews is None or reviews < reputation.min_review_count:
            return False, "reputation.min_review_count"
    if reputation.max_review_count is not None:
        if reviews is not None and reviews > reputation.max_review_count:
            return False, "reputation.max_review_count"

    age = filters.age
    founded = company.get("founded_year")
    if age.founded_after is not None and (founded is None or founded < age.founded_after):
        return False, "age.founded_after"
    if age.founded_before is not None and (founded is None or founded > age.founded_before):
        return False, "age.founded_before"

    tech = filters.tech
    if tech.includes or tech.excludes:
        stack = {str(t).lower() for t in (company.get("tech_stack") or [])}
        if tech.includes and not stack & {t.lower() for t in tech.includes}:
            return False, "tech.includes"
        if stack & {t.lower() for t in tech.excludes}:
            return False, "tech.excludes"

    return True, None


def describe() -> dict:
    """Machine-readable filter schema, served to the UI.

    The filter panel renders from this, so a new filter needs no frontend
    change - which is the point of keeping one source of truth.
    """
    return DiscoveryFilters.model_json_schema()

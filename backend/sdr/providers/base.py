"""The DataProvider port and the canonical record shapes.

Adapters translate a vendor's response into `RAW_COMPANY_FIELDS`. Nothing
downstream ever sees a vendor field name - that is what makes providers
swappable and what stops a Clearbit outage from requiring changes in the
scoring layer.
"""

from dataclasses import dataclass, field

from sdr.dto.filters import DiscoveryFilters
from sdr.errors import UnsupportedCapabilityError

# Capability keys a provider may declare.
COMPANY_SEARCH = "company_search"
COMPANY_ENRICH = "company_enrich"
CONTACT_FIND = "contact_find"
EMAIL_VERIFY = "email_verify"
TECH_DETECT = "tech_detect"

#: The canonical company shape. An adapter may return a subset; it may not
#: invent keys outside this list, because the repository writes them straight
#: onto `sdr_companies`.
RAW_COMPANY_FIELDS = (
    "name", "legal_name", "domain", "website_url",
    "country_code", "region_state", "city", "postal_code", "timezone",
    "industry", "sub_industry",
    "employee_count", "revenue_estimate", "revenue_currency",
    "founded_year", "registration_id",
    "phone_e164", "primary_email",
    "google_place_id", "google_rating", "google_review_count",
    "linkedin_url", "instagram_url", "facebook_url", "twitter_url",
    "tech_stack", "logo_url", "description",
    "discovery_source", "provider_ref",
)

RAW_CONTACT_FIELDS = (
    "full_name", "first_name", "last_name", "title", "seniority", "department",
    "is_decision_maker", "email", "email_status", "email_confidence",
    "phone_e164", "linkedin_url", "preferred_language", "discovery_source",
)


@dataclass
class CapabilityReport:
    """What a provider can honour natively for a given filter set.

    `native` and `post_filter` must together cover every active filter group,
    so the discovery run can tell the user exactly which constraints the
    provider enforced and which were applied afterwards.
    """
    supported: bool
    native: set = field(default_factory=set)
    post_filter: set = field(default_factory=set)
    reason: str = ""


@dataclass
class QuotaStatus:
    used: int = 0
    limit: int | None = None
    resets_at: str | None = None

    @property
    def exhausted(self) -> bool:
        return self.limit is not None and self.used >= self.limit


@dataclass
class HealthStatus:
    healthy: bool
    detail: str = ""
    latency_ms: int | None = None


@dataclass
class Page:
    items: list
    next_cursor: str | None = None
    cost_usd: float = 0.0
    #: Non-fatal problems - a dead mirror, a partial page. Surfaced on the run
    #: report so a quietly degraded result set is visible.
    warnings: list = field(default_factory=list)


class DataProvider:
    """Base class. Adapters override only what they can actually do.

    Every unimplemented method raises UnsupportedCapabilityError rather than
    returning empty, so a missing capability is loud at the call site instead
    of looking like "no results found".
    """

    key: str = ""
    label: str = ""
    #: Whether the provider needs credentials to function at all.
    requires_credentials: bool = False
    #: Rough per-result cost, used for budget estimation before a run.
    cost_per_result_usd: float = 0.0
    capabilities: tuple = ()

    def is_configured(self) -> bool:
        """Whether this provider can run right now. Adapters needing an API
        key check for it here so the registry can skip them cleanly."""
        return True

    def supports(self, filters: DiscoveryFilters) -> CapabilityReport:
        raise NotImplementedError

    async def quota(self) -> QuotaStatus:
        return QuotaStatus()

    async def estimate_cost(self, filters: DiscoveryFilters) -> float:
        return filters.limits.max_results * self.cost_per_result_usd

    async def search(self, filters: DiscoveryFilters, cursor: str | None = None) -> Page:
        raise UnsupportedCapabilityError(
            f"{self.label or self.key} does not support company search."
        )

    async def enrich(self, company: dict) -> dict:
        raise UnsupportedCapabilityError(
            f"{self.label or self.key} does not support company enrichment."
        )

    async def find_contacts(self, company: dict, role_hints: list | None = None) -> list:
        raise UnsupportedCapabilityError(
            f"{self.label or self.key} does not support contact discovery."
        )

    async def verify_email(self, email: str) -> dict:
        raise UnsupportedCapabilityError(
            f"{self.label or self.key} does not support email verification."
        )

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=self.is_configured(),
                            detail="" if self.is_configured() else "Not configured")

    # -- helpers for adapters --------------------------------------------------

    @staticmethod
    def clean(record: dict) -> dict:
        """Drop keys outside the canonical shape and strip empty values.

        Called by every adapter at the end of `_normalize`. It is the thing
        that actually enforces "vendor field names never leak" - a stray
        `formatted_phone_number` is dropped here rather than landing in Mongo.
        """
        return {
            key: value for key, value in record.items()
            if key in RAW_COMPANY_FIELDS and value not in (None, "", [], {})
        }

    @staticmethod
    def clean_contact(record: dict) -> dict:
        return {
            key: value for key, value in record.items()
            if key in RAW_CONTACT_FIELDS and value not in (None, "", [], {})
        }

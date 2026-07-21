"""Opportunity signal registry.

A declarative catalogue, not a wall of if-statements: each signal owns its
detector, severity, evidence path and the services it maps to. Adding a
nineteenth signal means appending one SignalDef - no other file changes.

Detectors receive a single normalised `AuditFacts` dict, assembled by the
website-audit agent in Phase 4. They must be total functions: an absent key
means "we could not determine this", which yields no signal rather than a
false positive. Claiming a prospect has no chatbot because the crawl failed
is worse than claiming nothing at all - it would end up in an outreach email.

Pure module: no I/O.
"""

from dataclasses import dataclass, field
from typing import Callable

# Severity drives both the pitch ordering and the scoring weight.
LOW = "low"
MEDIUM = "medium"
HIGH = "high"
CRITICAL = "critical"

SEVERITY_RANK = {LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4}


@dataclass(frozen=True)
class SignalDef:
    key: str
    label: str
    #: Plain-English description of the gap, safe to show a prospect.
    description: str
    severity: str
    #: Returns True when the gap is present, False when it is provably absent,
    #: None when the input does not let us tell.
    detector: Callable[[dict], bool | None]
    #: Audit keys the detector consulted, so every claim can be traced back
    #: to stored evidence. The grounding guardrail checks this.
    evidence_keys: tuple
    #: Fraction of currently-missed enquiries this gap is responsible for.
    #: Used by roi.estimate_opportunity. Sourced from the benchmark table in
    #: sdr/config/benchmarks.py, not invented per-signal.
    capture_uplift: float
    #: Service catalogue slugs this signal justifies pitching.
    services: tuple = field(default_factory=tuple)


def _missing(facts: dict, key: str) -> bool | None:
    """True when a boolean capability is absent, None when unknown."""
    value = facts.get(key)
    if value is None:
        return None
    return not bool(value)


def _below(facts: dict, key: str, threshold: float) -> bool | None:
    value = facts.get(key)
    if value is None:
        return None
    try:
        return float(value) < threshold
    except (TypeError, ValueError):
        return None


def _above(facts: dict, key: str, threshold: float) -> bool | None:
    value = facts.get(key)
    if value is None:
        return None
    try:
        return float(value) > threshold
    except (TypeError, ValueError):
        return None


def _slow_site(facts: dict) -> bool | None:
    """Prefer a real Lighthouse score; fall back to measured response time.

    This deployment cannot run Lighthouse (ADR 0004), so in practice the
    fallback is what fires. It measures server response and transfer, not
    render time - a genuinely different thing, and narrower. The evidence
    keys say which one was used so a claim is never overstated.
    """
    score = facts.get("lighthouse_performance")
    if score is not None:
        try:
            return float(score) < 50
        except (TypeError, ValueError):
            pass

    elapsed = facts.get("load_time_ms")
    if elapsed is None:
        return None
    try:
        # 2.5s to first byte and full transfer is slow by any standard, and
        # is deliberately well above a borderline figure so the claim holds up.
        return float(elapsed) > 2500
    except (TypeError, ValueError):
        return None


def _weak_seo(facts: dict) -> bool | None:
    """Lighthouse SEO if available, else the structural check from detect.py."""
    score = facts.get("lighthouse_seo")
    if score is None:
        score = facts.get("seo_score_basic")
    if score is None:
        return None
    try:
        return float(score) < 70
    except (TypeError, ValueError):
        return None


def _stale_content(facts: dict) -> bool | None:
    days = facts.get("blog_days_since_update")
    if days is None:
        return None
    try:
        return float(days) > 180
    except (TypeError, ValueError):
        return None


def _reviews_unanswered(facts: dict) -> bool | None:
    count = facts.get("google_review_count")
    response_rate = facts.get("review_response_rate")
    if count is None or response_rate is None:
        return None
    try:
        return float(count) >= 25 and float(response_rate) < 0.2
    except (TypeError, ValueError):
        return None


def _broken_form(facts: dict) -> bool | None:
    present = facts.get("contact_form_present")
    working = facts.get("contact_form_working")
    if present is None:
        return None
    if not present:
        return False  # covered by weak_lead_capture instead
    if working is None:
        return None
    return not working


SIGNALS: tuple = (
    # First because it outranks everything below it: the other signals all
    # describe a gap *on* a website. This one is the absence of the website.
    #
    # It exists because scoring previously treated "no site to audit" as "no
    # opportunity found", which zeroed the largest scoring component for the
    # single best prospect an automation agency can have. The audit already
    # called this "a finding, and a strong one" - it just never emitted one.
    SignalDef(
        key="no_website",
        label="No website at all",
        description="The business has no website, so every enquiry depends on someone "
                    "finding a phone number and choosing to ring it during office hours.",
        severity=CRITICAL,
        # True when we positively know there is no site. Never guessed: a
        # company we simply have not looked up yet returns None and claims
        # nothing, exactly like every other detector here.
        detector=lambda f: True if f.get("has_website") is False else None,
        evidence_keys=("has_website",),
        # The highest in the table. Every other gap loses a share of visitors
        # who already reached the site; this one loses the visitors too.
        capture_uplift=0.35,
        services=("website", "ai-chatbot", "booking-automation"),
    ),
    SignalDef(
        key="no_chatbot",
        label="No website chat",
        description="Visitors have no way to ask a question without picking up the phone or waiting on email.",
        severity=HIGH,
        detector=lambda f: _missing(f, "has_chat_widget"),
        evidence_keys=("has_chat_widget", "chat_vendor"),
        capture_uplift=0.12,
        services=("ai-chatbot", "ai-receptionist"),
    ),
    SignalDef(
        key="no_crm",
        label="No CRM in use",
        description="No CRM tracking pixel detected, so enquiries are likely being managed in an inbox.",
        severity=MEDIUM,
        detector=lambda f: _missing(f, "has_crm_pixel"),
        evidence_keys=("has_crm_pixel", "crm_vendor"),
        capture_uplift=0.06,
        services=("crm-setup",),
    ),
    SignalDef(
        key="manual_appointment_booking",
        label="Manual appointment booking",
        description="No self-serve booking - every appointment costs staff time and is limited to office hours.",
        severity=HIGH,
        detector=lambda f: _missing(f, "has_booking_system"),
        evidence_keys=("has_booking_system", "booking_vendor"),
        capture_uplift=0.15,
        services=("booking-automation", "ai-receptionist"),
    ),
    SignalDef(
        key="poor_website_performance",
        label="Slow website",
        description="The site is slow enough to respond that a measurable share of visitors leave before it loads.",
        severity=HIGH,
        detector=_slow_site,
        evidence_keys=("lighthouse_performance", "load_time_ms", "page_bytes"),
        capture_uplift=0.10,
        services=("website-rebuild", "performance-optimisation"),
    ),
    SignalDef(
        key="not_mobile_friendly",
        label="Not mobile friendly",
        description="The site does not adapt to phones, where most local search traffic originates.",
        severity=CRITICAL,
        detector=lambda f: _missing(f, "mobile_friendly"),
        evidence_keys=("mobile_friendly",),
        capture_uplift=0.20,
        services=("website-rebuild",),
    ),
    SignalDef(
        key="no_ssl",
        label="No valid HTTPS",
        description="Browsers warn visitors that the site is not secure before they ever see it.",
        severity=CRITICAL,
        detector=lambda f: _missing(f, "ssl_valid"),
        evidence_keys=("ssl_valid",),
        capture_uplift=0.25,
        services=("website-rebuild", "hosting-migration"),
    ),
    SignalDef(
        key="no_marketing_automation",
        label="No marketing automation",
        description="No email or nurture automation detected - leads that do not buy immediately go cold.",
        severity=MEDIUM,
        detector=lambda f: _missing(f, "has_marketing_automation"),
        evidence_keys=("has_marketing_automation", "analytics_vendors"),
        capture_uplift=0.08,
        services=("marketing-automation",),
    ),
    SignalDef(
        key="no_ai_receptionist",
        label="No after-hours cover",
        description="Enquiries arriving outside business hours wait until the next working day.",
        severity=HIGH,
        detector=lambda f: _missing(f, "has_after_hours_cover"),
        evidence_keys=("has_after_hours_cover", "opening_hours"),
        capture_uplift=0.14,
        services=("ai-receptionist", "voice-agent"),
    ),
    SignalDef(
        key="slow_response_time",
        label="Slow enquiry response",
        description="Measured reply time is slow enough that most prospects will have contacted a competitor first.",
        severity=HIGH,
        detector=lambda f: _above(f, "measured_response_hours", 24),
        evidence_keys=("measured_response_hours",),
        capture_uplift=0.13,
        services=("ai-chatbot", "crm-setup"),
    ),
    SignalDef(
        key="no_whatsapp_automation",
        label="No WhatsApp channel",
        description="No WhatsApp contact route, despite it being the default channel in this market.",
        severity=MEDIUM,
        detector=lambda f: _missing(f, "whatsapp_link_present"),
        evidence_keys=("whatsapp_link_present", "phone_click_to_call"),
        capture_uplift=0.09,
        services=("whatsapp-automation",),
    ),
    SignalDef(
        key="weak_lead_capture",
        label="No enquiry form",
        description="There is no form at all - every enquiry depends on the visitor deciding to call.",
        severity=HIGH,
        detector=lambda f: _missing(f, "contact_form_present"),
        evidence_keys=("contact_form_present", "forms_detected", "cta_count"),
        capture_uplift=0.16,
        services=("website-rebuild", "lead-capture"),
    ),
    SignalDef(
        key="broken_contact_form",
        label="Broken contact form",
        description="The enquiry form is present but does not submit - enquiries are being silently lost.",
        severity=CRITICAL,
        detector=_broken_form,
        evidence_keys=("contact_form_present", "contact_form_working"),
        capture_uplift=0.30,
        services=("website-repair", "lead-capture"),
    ),
    SignalDef(
        key="poor_seo",
        label="Weak SEO",
        description="Structural SEO problems limit how often the business appears in search at all.",
        severity=MEDIUM,
        detector=_weak_seo,
        evidence_keys=("lighthouse_seo", "seo_score_basic", "seo_issues", "schema_org_present"),
        capture_uplift=0.07,
        services=("seo",),
    ),
    SignalDef(
        key="no_faq_automation",
        label="No self-serve answers",
        description="No FAQ or help content, so routine questions consume staff time.",
        severity=LOW,
        detector=lambda f: _missing(f, "has_faq_content"),
        evidence_keys=("has_faq_content",),
        capture_uplift=0.03,
        services=("ai-chatbot", "knowledge-base"),
    ),
    SignalDef(
        key="no_review_automation",
        label="No review generation",
        description="Nothing prompts happy customers to leave a review, so social proof accrues slowly.",
        severity=LOW,
        detector=lambda f: _missing(f, "has_review_automation"),
        evidence_keys=("has_review_automation", "google_review_count"),
        capture_uplift=0.04,
        services=("review-automation",),
    ),
    SignalDef(
        key="high_review_volume_no_response",
        label="Reviews going unanswered",
        description="A meaningful review volume with almost no owner responses - a visible trust gap.",
        severity=MEDIUM,
        detector=_reviews_unanswered,
        evidence_keys=("google_review_count", "review_response_rate", "google_rating"),
        capture_uplift=0.05,
        services=("review-automation", "reputation-management"),
    ),
    SignalDef(
        key="no_analytics",
        label="No analytics",
        description="No analytics detected, so there is no way to know which marketing spend works.",
        severity=MEDIUM,
        detector=lambda f: _missing(f, "has_analytics"),
        evidence_keys=("has_analytics", "analytics_vendors"),
        capture_uplift=0.05,
        services=("analytics-setup",),
    ),
    SignalDef(
        key="stale_content",
        label="Stale content",
        description="Nothing has been published in over six months, which reads as inactive to both visitors and search engines.",
        severity=LOW,
        detector=_stale_content,
        evidence_keys=("blog_days_since_update",),
        capture_uplift=0.03,
        services=("content-marketing", "seo"),
    ),
    SignalDef(
        key="no_booking_reminders",
        label="No booking reminders",
        description="Appointments are booked without automated reminders, which drives avoidable no-shows.",
        severity=MEDIUM,
        detector=lambda f: _missing(f, "has_booking_reminders"),
        evidence_keys=("has_booking_reminders", "has_booking_system"),
        capture_uplift=0.06,
        services=("booking-automation", "whatsapp-automation"),
    ),
)

BY_KEY = {s.key: s for s in SIGNALS}


def detect(facts: dict) -> list:
    """Run every detector over one audit's facts.

    Returns a list of dicts ready to persist as `sdr_opportunity_signals`
    rows, ordered most severe first. Signals whose detector returns None
    (undeterminable) are omitted entirely - see the module docstring.
    """
    found = []
    for signal in SIGNALS:
        try:
            present = signal.detector(facts)
        except Exception:
            # A malformed fact for one signal must not abort the whole audit.
            present = None
        if not present:
            continue
        found.append({
            "signal_key": signal.key,
            "label": signal.label,
            "description": signal.description,
            "severity": signal.severity,
            "capture_uplift": signal.capture_uplift,
            "services": list(signal.services),
            # Only the keys the detector actually consulted, so every claim
            # in an outreach message can be traced to stored evidence.
            "evidence": {k: facts.get(k) for k in signal.evidence_keys if k in facts},
        })
    found.sort(key=lambda s: SEVERITY_RANK.get(s["severity"], 0), reverse=True)
    return found


def confidence(signal_row: dict) -> float:
    """How much of the signal's evidence we actually captured, 0.0-1.0.

    A signal detected from two of two expected fields is more trustworthy
    than one inferred from one of four. Surfaced in the UI so an estimate is
    never presented as a measurement.
    """
    definition = BY_KEY.get(signal_row.get("signal_key"))
    if not definition or not definition.evidence_keys:
        return 0.0
    evidence = signal_row.get("evidence") or {}
    present = sum(1 for k in definition.evidence_keys if evidence.get(k) is not None)
    return round(present / len(definition.evidence_keys), 2)

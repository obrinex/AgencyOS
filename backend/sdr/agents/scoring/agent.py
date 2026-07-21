"""Scoring and qualification agents.

Both are deterministic wrappers over `sdr/domain/scoring.py`. No model is
involved, which is deliberate: a score has to be reproducible and defensible.
"This lead scored 78 because reachability contributed 20 and opportunity 24"
is arguable. "The model felt it was a 78" is not, and cannot be regression
tested.

Qualification applies hard rules first. A hard rule beats any score - a lead
in a country with no compliance profile is disqualified at 95 as readily as at
15, because sending to them would be unlawful regardless of how good a fit
they are.
"""

import logging

from database import db
from sdr.agents.base.agent import Agent, AgentContext
from sdr.collections import SUPPRESSION
from sdr.config.countries import is_cold_outreach_permitted
from sdr.repositories import settings as settings_repo
from sdr.domain import scoring as scoring_domain
from sdr.domain.normalize import normalize_domain, normalize_email
from sdr.errors import NotFoundError, ValidationError
from sdr.repositories import audits as audits_repo
from sdr.repositories import companies as companies_repo
from sdr.repositories import leads as leads_repo

logger = logging.getLogger(__name__)


async def _gather(lead_id: str) -> tuple:
    """Everything the scorer needs, assembled once."""
    lead = await leads_repo.get_lead(lead_id)
    if not lead:
        raise NotFoundError("Lead not found")

    company = {}
    signals = []
    if lead.get("sdr_company_id"):
        try:
            company = await companies_repo.get_company(lead["sdr_company_id"])
            signals = await audits_repo.signals_for(lead["sdr_company_id"])
        except NotFoundError:
            company = {}

    contacts = []
    if lead.get("email") or lead.get("phone"):
        # The host CRM stores a lead's own contact details on the lead itself;
        # treat them as one implicit contact so reachability is not zero for
        # every lead that has an email but no separate contact record.
        contacts.append({
            "email": lead.get("email"),
            "email_status": lead.get("email_status", "unknown"),
            "phone_e164": lead.get("phone"),
            "is_decision_maker": False,
        })
    stored = await db.contacts.find({"lead_id": lead_id}).to_list(50)
    for contact in stored:
        contacts.append({
            "email": contact.get("email"),
            "email_status": contact.get("email_status", "unknown"),
            "phone_e164": contact.get("phone_e164") or contact.get("phone"),
            "is_decision_maker": contact.get("is_decision_maker", False),
        })

    icp = None
    if lead.get("icp_profile_id"):
        from sdr.collections import ICP_PROFILES
        from sdr.repositories.base import object_id
        from database import serialize_doc
        doc = await db[ICP_PROFILES].find_one(
            {"_id": object_id(lead["icp_profile_id"], "icp id")}
        )
        icp = serialize_doc(doc)

    return lead, company, contacts, signals, icp


class LeadScoringAgent(Agent):
    key = "lead_scoring"
    version = f"1.0.0+model{scoring_domain.SCORING_VERSION}"
    description = "Deterministic 0-100 score with an explainable per-component breakdown."
    category = "sales"
    surface = "AI SDR → Lead drawer"
    queue = "scoring"
    cost_ceiling_usd = 0.001
    timeout_ms = 15_000

    async def execute(self, payload: dict, ctx: AgentContext) -> dict:
        lead_id = payload.get("lead_id")
        if not lead_id:
            raise ValidationError("lead_id is required")

        lead, company, contacts, signals, icp = await _gather(lead_id)

        scored = scoring_domain.score_lead(
            lead=lead, company=company, contacts=contacts,
            detected_signals=signals, icp=icp,
        )
        await leads_repo.apply_score(lead_id, scored)

        return {
            "lead_id": lead_id,
            "score": scored["score"],
            "score_version": scored["score_version"],
            # The breakdown is the deliverable, not a debugging aid - the lead
            # drawer renders it so a rep can disagree with a specific line
            # rather than with the number.
            "breakdown": scored["score_breakdown"],
            "signals_counted": len(signals),
            "contacts_counted": len(contacts),
            "icp_applied": bool(icp),
        }


async def _hard_fails(lead: dict, company: dict, contacts: list,
                      allow_unlisted: bool = False) -> list:
    """Rules that disqualify regardless of score."""
    fails = []

    # Suppression: an opt-out is permanent and applies across every channel.
    domain = normalize_domain(company.get("domain") or lead.get("website"))
    email = normalize_email(lead.get("email"))
    checks = []
    if domain:
        checks.append({"value_type": "domain", "value_normalized": domain})
    if email:
        checks.append({"value_type": "email", "value_normalized": email})
    if checks:
        hit = await db[SUPPRESSION].find_one({"$or": checks})
        if hit:
            fails.append(f"suppressed ({hit.get('reason', 'unknown reason')})")

    if lead.get("do_not_contact"):
        fails.append("marked do-not-contact")

    # No route to reach them. Everything downstream is pointless.
    has_route = bool(
        lead.get("email") or lead.get("phone")
        or company.get("primary_email") or company.get("phone_e164")
        or any(c.get("email") or c.get("phone_e164") for c in contacts)
    )
    if not has_route:
        fails.append("no contact route")

    # Compliance is checked against the *recipient's* country. An unlisted
    # country has no profile, so cold outreach is refused by design.
    country = company.get("country_code") or lead.get("country_code")
    permitted, reason = is_cold_outreach_permitted(
        country, "email", allow_unlisted=allow_unlisted
    )
    if not permitted:
        fails.append(f"compliance: {reason}")

    # Already a customer. Pitching an existing client is embarrassing.
    if lead.get("converted_client_id"):
        fails.append("already converted to a client")

    return fails


class QualificationAgent(Agent):
    key = "lead_qualification"
    version = "1.0.0"
    description = "Applies hard compliance and reachability rules, then the score threshold."
    category = "sales"
    surface = "AI SDR → Lead drawer"
    queue = "scoring"
    cost_ceiling_usd = 0.001
    timeout_ms = 15_000

    async def execute(self, payload: dict, ctx: AgentContext) -> dict:
        lead_id = payload.get("lead_id")
        if not lead_id:
            raise ValidationError("lead_id is required")

        lead, company, contacts, signals, _ = await _gather(lead_id)

        settings = await settings_repo.get_settings()
        fails = await _hard_fails(
            lead, company, contacts,
            allow_unlisted=settings.get("allow_unlisted_countries", False),
        )
        if fails:
            ctx.flag("hard_disqualification", fails)

        status, reason = scoring_domain.qualification_status(
            lead.get("score", 0), hard_fails=fails
        )
        await leads_repo.set_qualification(lead_id, status, reason)

        # Qualifying advances the pipeline; nothing else auto-transitions.
        # Contacting is a human or campaign decision, not this agent's.
        transitioned = False
        if status == "qualified" and lead.get("stage") == "prospect":
            try:
                await leads_repo.transition_stage(
                    lead_id, "qualified", actor="ai",
                    reason=f"Auto-qualified: {reason}",
                )
                transitioned = True
            except ValidationError as exc:
                logger.warning("Could not auto-advance lead %s: %s", lead_id, exc)

        return {
            "lead_id": lead_id,
            "qualification_status": status,
            "reason": reason,
            "hard_fails": fails,
            "score": lead.get("score", 0),
            "threshold": scoring_domain.QUALIFICATION_THRESHOLD,
            "stage_advanced": transitioned,
        }

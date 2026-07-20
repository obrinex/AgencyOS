"""Company research agent.

Produces the narrative a human needs before a first conversation: what the
business actually does, who it serves, and which detected gap is worth leading
with. Everything it writes is grounded in the audit and the company record -
it does no browsing of its own, so there is no route for it to acquire a fact
nobody stored.

The pitch angle is the valuable output. Signals tell you a prospect has no
booking system; the angle says why that matters *for a dental clinic in Pune
with 212 reviews*, which is the difference between a mail-merge and a reason
to reply.
"""

import logging

from typing import Optional

from pydantic import BaseModel, Field

from sdr.agents.base.agent import Agent, AgentContext
from sdr.agents.base.guardrails import check_grounding, collect_grounding_facts
from sdr.errors import NotFoundError, ValidationError
from sdr.repositories import audits as audits_repo
from sdr.repositories import companies as companies_repo

logger = logging.getLogger(__name__)

PROMPT_VERSION = "1.0.0"


class ResearchOutput(BaseModel):
    summary: str = Field(max_length=800, description="What the business does, plainly")
    target_customer: Optional[str] = Field(default=None, max_length=300)
    #: The single gap worth leading with, and why it matters to this business.
    pitch_angle: Optional[str] = Field(default=None, max_length=500)
    lead_signal_key: Optional[str] = None
    talking_points: list[str] = Field(default_factory=list, max_length=5)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)


SYSTEM = """You are a B2B researcher preparing a sales team for a first conversation.

You are given a company record and the results of an automated website audit.
Work only from those. You have no other sources, and you must not act as
though you do.

Rules:
1. Every claim must come from the supplied data. If you cannot tell what the
   business does, say so in `summary` and lower `confidence`. Do not fill the
   gap with what a business of that type usually does.
2. `pitch_angle` must reference a gap that is actually in the detected signals
   list, and explain why it costs this specific business something. Set
   `lead_signal_key` to that signal's key.
3. No superlatives, no invented achievements, no guesses about revenue,
   headcount, or their current vendors beyond what is listed.
4. `talking_points` are facts a rep can safely say out loud. Anything you
   would not want read back to the business owner does not belong here.
5. Put the exact supporting values in `evidence`.

Respond with ONLY a JSON object. No prose, no markdown fences."""


def build_user_prompt(company: dict, audit: dict | None, signals: list) -> str:
    known = {
        "name": company.get("name"),
        "industry": company.get("industry"),
        "city": company.get("city"),
        "country_code": company.get("country_code"),
        "website": company.get("domain"),
        "description": company.get("description"),
        "google_rating": company.get("google_rating"),
        "google_review_count": company.get("google_review_count"),
        "employee_count": company.get("employee_count"),
        "founded_year": company.get("founded_year"),
        "tech_stack": company.get("tech_stack"),
    }
    known_lines = "\n".join(
        f"- {key}: {value}" for key, value in known.items() if value not in (None, "", [])
    )

    if signals:
        signal_lines = "\n".join(
            f"- {row['signal_key']} ({row['severity']}): {row.get('description', '')}"
            for row in signals
        )
    else:
        signal_lines = "- (no gaps detected, or no audit has run)"

    audit_lines = "- (no audit available)"
    if audit and audit.get("facts"):
        facts = audit["facts"]
        interesting = {
            key: facts.get(key) for key in (
                "load_time_ms", "seo_score_basic", "mobile_friendly", "ssl_valid",
                "has_chat_widget", "has_booking_system", "has_analytics",
                "contact_form_present", "whatsapp_link_present", "tech_stack",
            ) if facts.get(key) is not None
        }
        audit_lines = "\n".join(f"- {key}: {value}" for key, value in interesting.items())

    return "\n".join([
        "Research this company.",
        "",
        "COMPANY RECORD:",
        known_lines or "- (only a name)",
        "",
        "DETECTED GAPS (choose your pitch angle from these, by key):",
        signal_lines,
        "",
        "WEBSITE AUDIT FACTS:",
        audit_lines,
        "",
        "Return JSON:",
        """{
  "summary": string,
  "target_customer": string|null,
  "pitch_angle": string|null,
  "lead_signal_key": string|null,
  "talking_points": [string],
  "evidence": [string],
  "confidence": number between 0 and 1
}""",
    ])


class CompanyResearchAgent(Agent):
    key = "company_research"
    version = f"1.0.0+prompt{PROMPT_VERSION}"
    description = "Summarises the business and picks the pitch angle from detected gaps."
    output_schema = ResearchOutput
    category = "sales"
    surface = "AI SDR → Lead drawer"
    queue = "research"
    cost_ceiling_usd = 0.02
    timeout_ms = 40_000
    max_tokens = 1000

    async def execute(self, payload: dict, ctx: AgentContext) -> dict:
        company_id = payload.get("company_id")
        if not company_id:
            raise ValidationError("company_id is required")

        company = await companies_repo.get_company(company_id)
        if not company:
            raise NotFoundError("Company not found")

        audit = await audits_repo.latest_audit(company_id)
        signals = await audits_repo.signals_for(company_id)

        result = await self.complete_validated(
            system=SYSTEM,
            user=build_user_prompt(company, audit, signals),
            ctx=ctx,
        )

        facts = collect_grounding_facts(company, audit or {}, {"signals": signals})
        grounded, unsupported = check_grounding(result.evidence, facts)
        if not grounded:
            ctx.flag("ungrounded_evidence", unsupported[:5])

        # A pitch angle citing a gap we never detected is the failure mode
        # that matters here - it would put a false claim in an email.
        valid_keys = {row["signal_key"] for row in signals}
        angle_valid = (not result.lead_signal_key) or (result.lead_signal_key in valid_keys)
        if not angle_valid:
            ctx.flag("invalid_pitch_signal", result.lead_signal_key)

        patch = {
            "research_summary": result.summary,
            "research_confidence": result.confidence,
            "research_version": self.version,
        }
        if grounded and angle_valid:
            patch.update({
                "target_customer": result.target_customer,
                "pitch_angle": result.pitch_angle,
                "lead_signal_key": result.lead_signal_key,
                "talking_points": result.talking_points,
            })
        await companies_repo.update_company(company_id, patch)

        return {
            "company_id": company_id,
            "summary": result.summary,
            "pitch_angle": result.pitch_angle if (grounded and angle_valid) else None,
            "lead_signal_key": result.lead_signal_key if angle_valid else None,
            "talking_points": result.talking_points if grounded else [],
            "confidence": result.confidence,
            "grounded": grounded,
            "pitch_signal_valid": angle_valid,
            "ungrounded_evidence": unsupported,
        }

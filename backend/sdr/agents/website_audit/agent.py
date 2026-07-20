"""Website audit agent.

Fully deterministic - no LLM, no cost, no hallucination surface. It fetches
one page through the SSRF guard, runs the pure detectors over it, stores the
audit, derives signals from the registry, and stops.

That it uses no model is the point. Everything here is a factual claim about
a real business that will end up in an email to them ("your contact form is
broken"). A language model adds nothing to `does this HTML contain a form`,
and adds a way to be confidently wrong.
"""

import logging

from sdr.agents.base.agent import Agent, AgentContext
from sdr.domain import detect
from sdr.domain import signals as signals_domain
from sdr.errors import NotFoundError, ValidationError
from sdr.repositories import audits as audits_repo
from sdr.repositories import companies as companies_repo
from sdr.services import safe_fetch

logger = logging.getLogger(__name__)


class WebsiteAuditAgent(Agent):
    key = "website_audit"
    version = f"1.0.0+detect{audits_repo.AUDIT_VERSION}"
    description = "Fetches the prospect's site and detects capability gaps. No LLM."
    category = "sales"
    surface = "AI SDR → Website Audits"
    queue = "audit"
    #: Deterministic, so no model budget is needed. Left non-zero rather than
    #: zero so the ceiling machinery is still exercised on this path.
    cost_ceiling_usd = 0.001
    timeout_ms = 25_000

    async def execute(self, payload: dict, ctx: AgentContext) -> dict:
        company_id = payload.get("company_id")
        if not company_id:
            raise ValidationError("company_id is required")

        company = await companies_repo.get_company(company_id)
        if not company:
            raise NotFoundError("Company not found")

        domain = company.get("domain")
        if not domain:
            # Not an error: plenty of small businesses have no site at all.
            # That is itself a finding, and a strong one - but it is recorded
            # as a skipped audit, not a failed job.
            audit = await audits_repo.save_audit(
                company_id, {}, status="skipped",
                error="Company has no website", unmeasured=detect.UNMEASURED_FACTS,
            )
            await companies_repo.update_company(company_id, {"last_audited_at": audit["audited_at"]})
            return {
                "company_id": company_id, "audit_id": audit["id"],
                "status": "skipped", "reason": "no website", "signals": [],
            }

        url = f"https://{domain}"
        try:
            response = await safe_fetch.fetch(url)
        except ValidationError as exc:
            # Covers unreachable hosts, TLS failures, and SSRF refusals. All
            # are audit outcomes, not job failures - retrying a dead domain
            # five times helps nobody.
            audit = await audits_repo.save_audit(
                company_id, {}, status="failed", error=str(exc), url=url,
                unmeasured=detect.UNMEASURED_FACTS,
            )
            ctx.flag("audit_fetch_failed", str(exc)[:200])
            return {
                "company_id": company_id, "audit_id": audit["id"],
                "status": "failed", "error": str(exc), "signals": [],
            }

        facts = detect.build_facts(
            html=response.text,
            status_code=response.status_code,
            headers=response.headers,
            elapsed_ms=response.elapsed_ms,
            tls=response.tls,
            company=company,
        )

        audit = await audits_repo.save_audit(
            company_id, facts, status="completed", url=response.url,
            unmeasured=detect.UNMEASURED_FACTS,
        )

        detected = signals_domain.detect(facts)
        stored = await audits_repo.replace_signals(company_id, audit["id"], detected)

        # The detected stack is worth promoting onto the company - later
        # agents and the tech filter both read it from there.
        patch = {"last_audited_at": audit["audited_at"]}
        if facts.get("tech_stack"):
            patch["tech_stack"] = facts["tech_stack"]
        await companies_repo.update_company(company_id, patch)

        return {
            "company_id": company_id,
            "audit_id": audit["id"],
            "status": "completed",
            "url": response.url,
            "load_time_ms": response.elapsed_ms,
            "seo_score_basic": facts.get("seo_score_basic"),
            "tech_stack": facts.get("tech_stack", []),
            "signals": [row["signal_key"] for row in stored],
            "signal_count": len(stored),
            "unmeasured": list(detect.UNMEASURED_FACTS),
        }

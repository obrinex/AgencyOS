"""Enrichment agent.

Order of operations matters and is deliberate:

  1. Try providers first. A fact from an API beats a fact from a language
     model every time, and provider results cost nothing extra once fetched.
  2. Only then ask the model, and only about things it can legitimately infer
     from evidence we hold.
  3. Check grounding before writing anything.

Failure is partial, never total: a company with provider data but a failed
LLM call is marked `partial` and keeps what it got, because throwing away
good data because a later step failed is how records end up empty.
"""

import logging

import httpx

from database import now_iso
from sdr.agents.base.agent import Agent, AgentContext
from sdr.agents.base.guardrails import (
    check_grounding, collect_grounding_facts, detect_injection_attempt, wrap_untrusted,
)
from sdr.agents.enrichment.prompts import PROMPT_VERSION, SYSTEM, build_user_prompt
from sdr.agents.enrichment.schema import EnrichmentInput, EnrichmentOutput
from sdr.errors import NotFoundError, ProviderError, SDRError
from sdr.providers import registry
from sdr.repositories import companies as companies_repo

logger = logging.getLogger(__name__)

USER_AGENT = "AgencyOS-SDR/1.0 (info@obrinex.space)"

#: Fields the model is allowed to write. Contact details are absent by design
#: - see the system prompt. This list is the enforcement.
_WRITABLE = (
    "industry", "sub_industry", "description",
    "founded_year", "tech_stack",
)

#: Below this, an inference is recorded but not promoted onto the company.
CONFIDENCE_FLOOR = 0.4


class EnrichmentAgent(Agent):
    key = "lead_enrichment"
    version = f"1.0.0+prompt{PROMPT_VERSION}"
    description = "Fills missing firmographics from providers and the company's own website."
    input_schema = EnrichmentInput
    output_schema = EnrichmentOutput
    category = "sales"
    surface = "AI SDR → Lead Database"
    queue = "enrichment"
    cost_ceiling_usd = 0.02
    timeout_ms = 40_000
    max_tokens = 900

    async def execute(self, payload: dict, ctx: AgentContext) -> dict:
        company = await companies_repo.get_company(payload["company_id"])
        if not company:
            raise NotFoundError("Company not found")

        if not payload.get("force") and company.get("enrichment_status") == "complete":
            return {"skipped": True, "reason": "already enriched", "company_id": company["id"]}

        provider_fields, provider_notes = await self._from_providers(company)
        page_text, fetch_note = await self._fetch_homepage(company)

        if page_text:
            attempts = detect_injection_attempt(page_text)
            if attempts:
                # Worth recording against the company, not just filtering:
                # a site doing this tells you something about the prospect.
                ctx.flag("prompt_injection_attempt", attempts[:3])
                logger.warning(
                    "Injection-shaped content on %s: %s", company.get("domain"), attempts[:3]
                )

        inferred, confidence, evidence = {}, 0.0, []
        llm_note = None
        if page_text or company.get("description"):
            try:
                result = await self._infer(company, page_text, ctx)
                inferred = result.fields.model_dump(exclude_none=True)
                confidence = result.confidence
                evidence = result.evidence
            except SDRError as exc:
                # Degrade rather than fail: provider data is still worth keeping.
                llm_note = f"inference failed: {exc}"
                ctx.flag("llm_inference_failed", str(exc)[:200])
        else:
            llm_note = "no website content to infer from"

        grounded = True
        ungrounded = []
        if inferred:
            facts = collect_grounding_facts(company, {"page": page_text or ""})
            grounded, ungrounded = check_grounding(evidence, facts)
            if not grounded:
                ctx.flag("ungrounded_evidence", ungrounded[:5])

        patch = dict(provider_fields)
        applied_from_llm = []
        # An inference is only promoted onto the record when it is both
        # confident and traceable. Everything else stays on the run for
        # inspection and goes no further.
        if inferred and confidence >= CONFIDENCE_FLOOR and grounded:
            for field in _WRITABLE:
                value = inferred.get(field)
                if value in (None, "", []):
                    continue
                if company.get(field):
                    continue  # never overwrite an existing value from an inference
                patch[field] = value
                applied_from_llm.append(field)

            signals = inferred.get("buying_signals") or []
            if signals:
                patch["buying_signals"] = signals

        status = self._status(company, patch, provider_fields, llm_note)
        patch["enrichment_status"] = status
        patch["last_enriched_at"] = now_iso()
        patch["enrichment_confidence"] = confidence

        await companies_repo.update_company(company["id"], patch)

        return {
            "company_id": company["id"],
            "enrichment_status": status,
            "fields_from_providers": sorted(provider_fields.keys()),
            "fields_from_inference": applied_from_llm,
            "confidence": confidence,
            "grounded": grounded,
            "ungrounded_evidence": ungrounded,
            "notes": [n for n in (*provider_notes, fetch_note, llm_note) if n],
        }

    # -- steps -----------------------------------------------------------------

    async def _from_providers(self, company: dict) -> tuple:
        """Ask every configured provider that supports enrichment."""
        fields, notes = {}, []
        for provider in registry.all_providers():
            from sdr.providers.base import COMPANY_ENRICH
            if COMPANY_ENRICH not in provider.capabilities or not provider.is_configured():
                continue
            try:
                result = await provider.enrich(company)
                for key, value in (result or {}).items():
                    if value not in (None, "", []) and not company.get(key):
                        fields[key] = value
                notes.append(f"{provider.key}: ok")
            except SDRError as exc:
                notes.append(f"{provider.key}: {exc}")
            except Exception as exc:
                notes.append(f"{provider.key}: {exc}")
        return fields, notes

    async def _fetch_homepage(self, company: dict) -> tuple:
        """Fetch the company's homepage as plain-ish text.

        SSRF guard: only http/https, and the fetch is size- and time-capped.
        A prospect controls this URL, so it is treated as hostile input from
        the moment it arrives.
        """
        domain = company.get("domain")
        if not domain:
            return None, "no website to fetch"

        url = f"https://{domain}"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(8.0, connect=4.0),
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                max_redirects=3,
            ) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            return None, f"could not fetch {domain}: {exc}"

        if response.status_code != 200:
            return None, f"{domain} returned {response.status_code}"

        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            return None, f"{domain} served {content_type or 'unknown content'}"

        text = self._strip_html(response.text[:200_000])
        return text, None

    @staticmethod
    def _strip_html(html: str) -> str:
        import re
        # Scripts and styles first, or their contents survive tag removal.
        cleaned = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
        cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"&nbsp;?", " ", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.strip()

    async def _infer(self, company: dict, page_text: str | None,
                     ctx: AgentContext) -> EnrichmentOutput:
        untrusted = wrap_untrusted(page_text, label="the prospect's own website text")
        user = build_user_prompt(company, untrusted)
        return await self.complete_validated(system=SYSTEM, user=user, ctx=ctx)

    @staticmethod
    def _status(company: dict, patch: dict, provider_fields: dict,
                llm_note: str | None) -> str:
        """`complete` means the fields that matter downstream are present."""
        required = ("industry", "description", "city", "country_code")
        merged = {**company, **patch}
        if all(merged.get(field) for field in required):
            return "complete"
        if patch or provider_fields:
            return "partial"
        return "failed" if llm_note else "partial"

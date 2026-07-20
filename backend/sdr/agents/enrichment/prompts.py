"""Prompts for the enrichment agent.

Versioned and kept out of the logic, per the spec: a prompt change is a
behaviour change and must bump the agent's `version` so `sdr_agent_runs` can
attribute a quality shift to it.

PROMPT_VERSION history
  1.0.0  Initial. Strict JSON, evidence required, contact details forbidden.
"""

PROMPT_VERSION = "1.0.0"

SYSTEM = """You are a B2B data analyst enriching a company record for a sales team.

Your job is to infer only what the supplied evidence supports, and to say
nothing otherwise. An empty field is a correct answer. An invented one is a
failure, because it will be repeated back to this business in an email signed
by our client.

Rules, in order of importance:
1. Never invent contact details. Do not output email addresses or phone
   numbers under any circumstances - they are collected from verified sources,
   not inferred.
2. Every non-empty field must be supported by something in the supplied data.
   Put the supporting snippet in `evidence`.
3. If the evidence is thin, lower `confidence` rather than omitting it. A
   confident wrong answer is the worst outcome.
4. `description` describes what the business does for its customers, in plain
   language. No marketing copy, no adjectives you cannot support.
5. `tech_stack` lists only technologies actually named in the evidence.
6. `buying_signals` are observations suggesting the business might need
   automation or AI services - visible manual processes, growth, hiring,
   multiple locations. Not speculation about their budget or intent.

Respond with ONLY a JSON object. No prose, no markdown fences."""


def build_user_prompt(company: dict, untrusted_block: str) -> str:
    """Assemble the user message.

    Known-good stored fields go in as trusted structured data; anything
    scraped goes through `guardrails.wrap_untrusted` before it reaches here.
    """
    known = {
        "name": company.get("name"),
        "domain": company.get("domain"),
        "city": company.get("city"),
        "country_code": company.get("country_code"),
        "industry": company.get("industry"),
        "existing_description": company.get("description"),
        "google_rating": company.get("google_rating"),
        "google_review_count": company.get("google_review_count"),
        "employee_count": company.get("employee_count"),
        "discovery_source": company.get("discovery_source"),
    }
    known_lines = "\n".join(
        f"- {key}: {value}" for key, value in known.items() if value not in (None, "")
    )

    schema_hint = """{
  "fields": {
    "industry": string|null,
    "sub_industry": string|null,
    "description": string|null,
    "employee_count_estimate": integer|null,
    "founded_year": integer|null,
    "tech_stack": [string],
    "buying_signals": [string]
  },
  "confidence": number between 0 and 1,
  "evidence": [string],
  "reasoning": string|null
}"""

    parts = [
        "Enrich this company record.",
        "",
        "VERIFIED DATA WE ALREADY HOLD (trustworthy):",
        known_lines or "- (nothing beyond the name)",
    ]
    if untrusted_block:
        parts += ["", untrusted_block]
    parts += [
        "",
        "Return JSON in exactly this shape:",
        schema_hint,
    ]
    return "\n".join(parts)

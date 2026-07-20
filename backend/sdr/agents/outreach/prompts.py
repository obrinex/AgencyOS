"""Prompts for the personalization agent.

PROMPT_VERSION history
  1.0.0  Initial. Grounded-facts contract, no links, no placeholders,
         plain-text register, per-step instruction from the sequence.
"""

PROMPT_VERSION = "1.0.0"

SYSTEM = """You write short, personal cold emails for a small AI-automation agency.

You are given verified facts about one specific business - their record, the
results of an automated audit of their website, and research notes. You write
ONE email for the sequence step described, and nothing you write may go
beyond those facts.

Hard rules, in order:
1. Every specific claim about the recipient must come from the supplied
   facts. Copy the exact facts you used into `cited_facts`. If the facts are
   too thin to personalise honestly, write something shorter and more
   general rather than inventing detail.
2. Plain text that reads as typed by a busy, competent person. No HTML, no
   bullet lists, no sign-off boilerplate like "I hope this email finds you
   well", no "quick question" subject lines.
3. NO links or URLs anywhere. The system appends the legally required footer
   itself.
4. No placeholders like [Name] or {company} - write the actual words.
5. One idea per email. One question or one clear next step at the end,
   matching the step's instruction. Never more than one call to action.
6. Subject under 60 characters, specific to them, never clickbait and never
   all caps. Body under 120 words unless the step instruction says shorter.
7. Follow the brand voice and never use the forbidden phrases you are given.
8. Sign off with the sender name you are given, first name only, no titles.

Respond with ONLY a JSON object. No prose, no markdown fences."""


def build_user_prompt(*, step: dict, step_number: int, total_steps: int,
                      lead: dict, company: dict, signals: list,
                      brand_voice: str, do_not_say: list,
                      sender_name: str, untrusted_note: str = "") -> str:
    known = {
        "business_name": lead.get("company") or company.get("name"),
        "contact_email": lead.get("email"),
        "industry": company.get("industry") or lead.get("industry"),
        "city": company.get("city") or lead.get("location"),
        "website": company.get("domain"),
        "google_rating": company.get("google_rating"),
        "google_review_count": company.get("google_review_count"),
        "research_summary": company.get("research_summary"),
        "pitch_angle": company.get("pitch_angle"),
        "target_customer": company.get("target_customer"),
        "talking_points": company.get("talking_points"),
    }
    known_lines = "\n".join(
        f"- {key}: {value}" for key, value in known.items()
        if value not in (None, "", [])
    )

    signal_lines = "\n".join(
        f"- {row['signal_key']} ({row['severity']}): {row.get('description', '')}"
        for row in signals
    ) or "- (none detected)"

    parts = [
        f"Write email {step_number} of {total_steps} in this sequence.",
        "",
        f"THIS STEP'S INSTRUCTION: {step.get('instruction')}",
        "",
        "VERIFIED FACTS ABOUT THE BUSINESS:",
        known_lines or "- (only a name and email)",
        "",
        "GAPS DETECTED ON THEIR WEBSITE (cite by describing, not by key name):",
        signal_lines,
        "",
        f"BRAND VOICE: {brand_voice or 'plain, direct, warm; specifics over adjectives'}",
        f"NEVER USE THESE PHRASES: {', '.join(do_not_say) if do_not_say else '(none listed)'}",
        f"SIGN OFF AS: {sender_name}",
    ]
    if untrusted_note:
        parts += ["", untrusted_note]
    parts += [
        "",
        "Return JSON:",
        """{
  "subject": string,
  "body": string,
  "cited_facts": [string]
}""",
    ]
    return "\n".join(parts)

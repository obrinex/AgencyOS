"""Inbound reply classification: the pure parts.

This module exists to answer one question correctly: **did a human actually
answer?** Everything downstream keys off that, and the expensive mistake is
not a missed reply — it is a false one.

Treating an out-of-office as engagement stops the sequence permanently and
marks the lead as responsive when nobody read anything. The lead then sits in
`replied` forever, looking like the best outcome the system produces, and no
one ever follows up. That failure is silent, which is why it is caught here
deterministically from headers *before* any model is asked for an opinion.

Header detection runs first because it is authoritative and free: RFC 3834
requires automatic responders to mark themselves, and the well-behaved ones
do. The subject heuristics catch the rest. The model is only asked about
messages that survive both.
"""

import re

# --- Categories ---------------------------------------------------------------

#: What a reply can be. Closed set - the wiring below switches on it exactly.
CATEGORIES = (
    "interested",           # wants to talk. The goal.
    "not_now",              # a real human deferral ("ask me in Q3")
    "objection",            # engaged but pushing back
    "wrong_person",         # "I don't handle this" - re-research, don't retry
    "out_of_office",        # a machine. NOT a reply.
    "auto_reply",           # a machine. NOT a reply.
    "unsubscribe_request",  # "take me off your list"
    "bounce",               # delivery failure that arrived as mail
)

#: The two categories that must never be mistaken for engagement.
MACHINE_CATEGORIES = ("out_of_office", "auto_reply")

#: Categories where a human demonstrably read the message. Only these stamp
#: the lead as replied and stop the sequence as a success.
HUMAN_CATEGORIES = ("interested", "not_now", "objection", "wrong_person")

#: How long an out-of-office pushes the next touch. Long enough to outlast a
#: typical holiday, short enough that the lead does not go cold.
OOO_DEFER_DAYS = 7


# --- Threading ----------------------------------------------------------------

_MESSAGE_ID = re.compile(r"<[^<>@\s]+@[^<>@\s]+>")


def extract_message_ids(*header_values: str | None) -> list:
    """Every `<id@domain>` in the given headers, in order, de-duplicated.

    `References` holds the whole chain and `In-Reply-To` the immediate parent.
    Both are searched because clients are inconsistent about which they set,
    and a reply that threads at all is worth matching however it did it.
    """
    found = []
    for value in header_values:
        if not value:
            continue
        for match in _MESSAGE_ID.findall(value):
            if match not in found:
                found.append(match)
    return found


def match_order(in_reply_to: str | None, references: str | None) -> list:
    """Candidate Message-IDs, most-likely-parent first.

    `In-Reply-To` is the direct answer and wins. The `References` chain is
    walked backwards after it: the nearest ancestor is the most recent thing
    we sent, and therefore the best guess at what provoked this.
    """
    direct = extract_message_ids(in_reply_to)
    chain = list(reversed(extract_message_ids(references)))
    ordered = []
    for candidate in direct + chain:
        if candidate not in ordered:
            ordered.append(candidate)
    return ordered


# --- Machine detection --------------------------------------------------------

#: Headers that mean "a machine sent this", per RFC 3834 and common practice.
#: Checked case-insensitively on both name and value.
_AUTO_HEADERS = {
    "auto-submitted": lambda v: v.strip().lower() != "no",
    "x-autoreply": lambda v: True,
    "x-autorespond": lambda v: True,
    "x-auto-response-suppress": lambda v: True,
    "precedence": lambda v: v.strip().lower() in ("auto_reply", "bulk", "junk", "list"),
    "x-mailer-daemon": lambda v: True,
}

#: Subject patterns for responders that do not set the headers. Deliberately
#: multilingual - "abwesend" and "ausência" cost nothing and a missed OOO is
#: the expensive direction.
_OOO_SUBJECT = re.compile(
    r"\b(out\s+of\s+(the\s+)?office|auto(matic)?[\s-]*(reply|response|antwort)|"
    r"on\s+(vacation|holiday|leave|annual\s+leave|parental\s+leave)|"
    r"away\s+from\s+(my\s+)?(desk|office|email)|maternity|paternity|"
    # German compounds run words together ("Abwesenheitsnotiz"), so no
    # trailing word boundary is available to anchor on.
    r"abwesen\w*|ausencia|aus[eê]ncia|vacaciones|"
    r"n[aã]o\s+estarei|fuera\s+de\s+la\s+oficina|"
    r"currently\s+unavailable|limited\s+access\s+to\s+email)\b",
    re.IGNORECASE,
)

_BOUNCE_SUBJECT = re.compile(
    r"\b(undeliverable|delivery\s+(status\s+notification|failure|has\s+failed)|"
    r"returned\s+mail|mail\s+delivery\s+(failed|subsystem)|"
    r"failure\s+notice|message\s+not\s+delivered)\b",
    re.IGNORECASE,
)

_BOUNCE_SENDERS = ("mailer-daemon", "postmaster", "no-reply", "noreply")


def detect_machine_reply(*, headers: dict | None, subject: str | None,
                         from_email: str | None = None) -> str | None:
    """Return a machine category, or None if this looks like a person.

    Runs before the classifier and overrides it. A false positive here costs
    a 7-day delay; a false negative permanently strands a live lead. The
    asymmetry is the whole design — when in doubt, this leans machine.
    """
    normalized = {str(k).lower(): str(v) for k, v in (headers or {}).items()}

    sender = (from_email or "").lower()
    if any(marker in sender for marker in _BOUNCE_SENDERS):
        return "bounce"
    if _BOUNCE_SUBJECT.search(subject or ""):
        return "bounce"

    for name, is_auto in _AUTO_HEADERS.items():
        if name in normalized and is_auto(normalized[name]):
            # `Auto-Submitted: auto-replied` covers OOO and vacation
            # responders; the distinction from a generic auto_reply is made
            # on the subject, which is the only signal that carries it.
            if _OOO_SUBJECT.search(subject or ""):
                return "out_of_office"
            return "auto_reply"

    if _OOO_SUBJECT.search(subject or ""):
        return "out_of_office"

    return None


# --- What a category means ----------------------------------------------------

def action_for(category: str) -> dict:
    """Map a category onto what should happen to the enrollment and lead.

    Returned as data rather than executed here so the decision is testable
    without a database, and so the service layer has exactly one place to
    read the policy from.

    Keys:
      stop_reason   stop the enrollment with this reason, or None
      counts_as_reply  stamp the lead `replied_at` and treat as engagement
      suppress      add the address to the never-contact list
      defer_days    push the next touch out instead of stopping
    """
    if category == "interested":
        return {"stop_reason": "replied", "counts_as_reply": True,
                "suppress": False, "defer_days": 0, "lead_stage": "interested"}

    if category in ("not_now", "objection"):
        # Still a human who read it: stop writing. A rep decides what next.
        return {"stop_reason": "replied", "counts_as_reply": True,
                "suppress": False, "defer_days": 0, "lead_stage": None}

    if category == "wrong_person":
        # A distinct reason so the contact can be re-researched rather than
        # the company being written off.
        return {"stop_reason": "wrong_person", "counts_as_reply": True,
                "suppress": False, "defer_days": 0, "lead_stage": None}

    if category == "unsubscribe_request":
        return {"stop_reason": "unsubscribed", "counts_as_reply": False,
                "suppress": True, "defer_days": 0, "lead_stage": None}

    if category == "bounce":
        return {"stop_reason": "bounced", "counts_as_reply": False,
                "suppress": True, "defer_days": 0, "lead_stage": None}

    if category == "out_of_office":
        # The trap this module exists for: defer, never stop, never mark
        # replied. Nobody read the email.
        return {"stop_reason": None, "counts_as_reply": False,
                "suppress": False, "defer_days": OOO_DEFER_DAYS, "lead_stage": None}

    if category == "auto_reply":
        # A ticket acknowledgement or similar. Not engagement, but not a
        # reason to delay either - the sequence continues untouched.
        return {"stop_reason": None, "counts_as_reply": False,
                "suppress": False, "defer_days": 0, "lead_stage": None}

    raise ValueError(f"Unknown inbound category '{category}'")

"""Pre-send copy checks: the do-not-say list and light deliverability hygiene.

Run against every generated draft *before* it can be approved or sent. These
are deterministic string checks, deliberately separate from the LLM: the
model is asked to follow the rules, but asking is not enforcement, and the
whole point of a do-not-say list is that it holds even when the model has a
bad day.

The spam checks are the light version of spec section 7.2 - the handful of
signals that are (a) meaningful for plain-text cold email and (b) checkable
without a rendering engine. Link counting matters most: this system sends
text-only messages whose only link is the unsubscribe footer, so a draft that
contains URLs is either hallucinating resources or pasting tracking links,
and both get blocked.

Pure module: no I/O.
"""

import re

MAX_SUBJECT_CHARS = 78          # RFC-ish header comfort; long subjects clip anyway
MAX_BODY_WORDS = 220            # cold email past ~200 words stops being read
MAX_EXCLAMATIONS = 1
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
#: Placeholder shapes a template-minded model leaves behind. Any hit means
#: the draft was written for a mail-merge, not this person.
_PLACEHOLDER = re.compile(r"[\[{]\s*(first[_ ]?name|name|company|city|date)\s*[\]}]", re.IGNORECASE)

#: Classic spam-trigger phrases. Small and curated rather than exhaustive -
#: a giant list mostly produces false positives on normal prose.
_SPAM_PHRASES = (
    "act now", "buy now", "limited time", "100% free", "risk-free",
    "no obligation", "click here", "once in a lifetime", "winner",
    "guarantee", "guaranteed", "cash bonus", "double your",
)


def check_copy(*, subject: str, body: str, do_not_say: list | None = None) -> list:
    """Every problem with a draft, empty list if it is clean.

    All problems at once rather than first-failure, so a regeneration prompt
    can include the full list and fix everything in one pass.
    """
    problems = []
    subject = (subject or "").strip()
    body = (body or "").strip()

    if not subject:
        problems.append("Subject is empty.")
    elif len(subject) > MAX_SUBJECT_CHARS:
        problems.append(f"Subject is {len(subject)} characters; keep it under {MAX_SUBJECT_CHARS}.")
    if subject.isupper() and len(subject) > 3:
        problems.append("Subject is all caps.")

    if not body:
        problems.append("Body is empty.")
        return problems

    words = len(body.split())
    if words > MAX_BODY_WORDS:
        problems.append(f"Body is {words} words; cold email over {MAX_BODY_WORDS} stops being read.")

    if _URL.search(body) or _URL.search(subject):
        problems.append(
            "Draft contains a URL. These messages are text-only with the "
            "unsubscribe footer as the sole link - a URL here is either an "
            "invented resource or a tracking link."
        )

    placeholder = _PLACEHOLDER.search(body) or _PLACEHOLDER.search(subject)
    if placeholder:
        problems.append(
            f"Unfilled template placeholder '{placeholder.group(0)}' - the "
            "draft was written for a mail-merge, not this person."
        )

    exclamations = body.count("!") + subject.count("!")
    if exclamations > MAX_EXCLAMATIONS:
        problems.append(f"{exclamations} exclamation marks; at most {MAX_EXCLAMATIONS}.")

    haystack = f"{subject}\n{body}".lower()
    hits = sorted({phrase for phrase in _SPAM_PHRASES if phrase in haystack})
    if hits:
        problems.append(f"Spam-trigger phrasing: {', '.join(hits)}.")

    for banned in (do_not_say or []):
        term = (banned or "").strip().lower()
        if term and term in haystack:
            problems.append(f'Contains a do-not-say term: "{banned}".')

    return problems

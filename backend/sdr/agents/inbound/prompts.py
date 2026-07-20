"""Prompts for the inbound reply classifier.

PROMPT_VERSION history
  1.0.0  Initial. Closed category set, machine-detection reinforced in the
         prompt even though headers already decide it deterministically -
         belt and braces on the one classification that must not be wrong.
"""

PROMPT_VERSION = "1.0.0"

SYSTEM = """You classify replies to cold outreach emails for a small agency.

You are given the email we sent and the reply we received. Choose exactly one
category for the reply.

Categories:
- interested: they want to talk, meet, see pricing, or learn more. Any
  positive forward motion.
- not_now: a HUMAN is deferring deliberately - "not this quarter", "we're
  mid-migration, ask me in June". A person read it and chose to wait.
- objection: engaged but pushing back - too expensive, already have a vendor,
  don't see the value, skeptical. They are talking to us.
- wrong_person: they don't own this topic, have left the company, or are
  redirecting us to someone else.
- out_of_office: an automatic vacation, leave, or absence responder. Nobody
  read the email.
- auto_reply: any other machine-generated response - ticket acknowledgements,
  "we received your message", mailing-list confirmations, delivery notices
  that are not bounces. Nobody read the email.
- unsubscribe_request: they want off the list, however politely or rudely -
  "remove me", "stop emailing", "unsubscribe".
- bounce: a delivery failure report - mailbox not found, domain invalid,
  quota exceeded.

The distinction that matters most is human versus machine.

`not_now` means a PERSON decided to defer. `out_of_office` means a SERVER
sent an absence notice. They can look similar - both say "I'm not available"
- and confusing them is the worst error you can make here: an out-of-office
treated as a human reply permanently stops outreach to a live prospect who
never saw the email.

If the message reads as templated, mentions specific return dates, names an
alternative contact for "while I am away", or has no reference to anything in
our email, it is a machine. When you genuinely cannot tell whether a person
or a server wrote it, choose the machine category and set low confidence.

`confidence` is 0.0-1.0: how sure you are of the category. Below 0.6 a human
reviews it, so use low numbers freely rather than guessing confidently.

`reasoning` is one short sentence, for the human reviewing borderline cases.

Respond with ONLY a JSON object. No prose, no markdown fences."""


def build_user_prompt(*, sent_subject: str, sent_body: str,
                      reply_subject: str, reply_body: str,
                      from_email: str) -> str:
    """The two messages, ours first so the reply reads as a response to it."""
    # Truncated: quoted history routinely runs to thousands of words and the
    # signal is nearly always in the first part of the reply.
    reply = (reply_body or "").strip()[:4000]
    sent = (sent_body or "").strip()[:2000]

    return f"""THE EMAIL WE SENT
Subject: {sent_subject or "(unknown)"}

{sent or "(the original message could not be matched)"}

---

THE REPLY WE RECEIVED
From: {from_email or "(unknown)"}
Subject: {reply_subject or "(no subject)"}

{reply or "(empty body)"}

---

Classify the reply."""

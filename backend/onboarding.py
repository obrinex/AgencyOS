"""What we ask someone the first time they sign in, and why.

Two audiences, two question sets, one mechanism. A founding member and a client
are asked different things because they want different things from us — but both
sets exist for the same reason: the assistant is only as useful as what it knows
about the person it is talking to, and asking the same context question every
session is how an assistant becomes a form.

## This is a gate

The owner's decision: the portal is not usable until these are answered. It is
worth being clear about the cost, because it is real — someone who opens the
portal at 11pm to check one invoice meets ten questions first, and some of them
will close the tab. The design pays that down where it can:

- Ten is the ceiling, not the target. Client asks nine, member asks ten.
- One question per screen, so it never reads as a form.
- **Every answer is saved the moment it is given.** A gate that loses six
  answers to a dropped connection is a gate people never get through.
- Nothing here is scored, and none of it is shown to anyone else. It exists to
  be remembered, which is what the screen says.

## Keys are permanent

Each `key` is written into the person's context document and read back into
every assistant prompt they ever send. Renaming one silently orphans whatever
was already stored under the old name — the answer is not lost, but the
assistant stops seeing it. Add new keys; do not rename old ones.
"""

from typing import Optional

#: Ceiling, enforced below. More than this and the gate stops being a
#: conversation and starts being paperwork.
MAX_QUESTIONS = 10

#: Roles this module knows how to interview.
CLIENT_ROLE = "client"
FOUNDING_ROLE = "founding"


def _q(key: str, prompt: str, kind: str = "text", **extra) -> dict:
    return {"key": key, "prompt": prompt, "kind": kind, **extra}


#: A client. Everything here is something an account manager would otherwise ask
#: on a call and write in a doc nobody reads again.
CLIENT_QUESTIONS = [
    _q("business", "What does your business actually do?",
       hint="One or two sentences. Plain words beat positioning.",
       placeholder="We…", max_length=400),
    _q("industry", "Which of these is closest?", kind="choice",
       options=["E-commerce", "SaaS / software", "Professional services",
                "Healthcare", "Education", "Real estate", "Manufacturing",
                "Media / creator", "Something else"]),
    _q("customer", "Who is your customer?",
       hint="The person who actually pays, and what they're like.",
       placeholder="Mostly…", max_length=400),
    _q("success", "What would make the next 90 days a win?",
       kind="long",
       hint="Be specific. 'More leads' and '40 qualified calls a month' are very different briefs.",
       max_length=1000),
    _q("bottleneck", "What's the single biggest thing slowing you down?",
       kind="long",
       hint="The thing that actually stops you, not the thing that sounds best.",
       max_length=1000),
    _q("decision_maker", "Who signs off on this work?",
       hint="Name and role. If it's you, say so — it tells us how fast we can move.",
       max_length=200),
    _q("channel", "Where do you want us to reach you?", kind="choice",
       options=["Portal messages", "Email", "WhatsApp", "Phone call"]),
    _q("cadence", "How often do you want an update?", kind="choice",
       options=["Every day", "Twice a week", "Weekly",
                "Only when something changes", "Only at milestones"]),
    _q("constraints", "Any hard deadlines, budgets or constraints we should plan around?",
       kind="long",
       hint="Write 'None' if there aren't any — we'd rather know that than guess.",
       max_length=1000),
]

#: A founding member. Deliberately not the application again — they already
#: answered eleven questions to get in, and asking those a second time would say
#: we did not read them. These are about how to *help* them, which the
#: application never asked.
FOUNDING_QUESTIONS = [
    _q("building", "What are you building right now?",
       hint="Today's version, not the pitch.",
       placeholder="I'm working on…", max_length=400),
    _q("stage", "Where is it?", kind="choice",
       options=["Still an idea", "Building it", "First customers",
                "Growing steadily", "Scaling hard", "Between things"]),
    _q("superpower", "What are you unusually good at?",
       hint="The circle is ten people. This is how the others find you.",
       max_length=300),
    _q("bottleneck", "What's in your way this month?",
       kind="long", max_length=1000),
    _q("ninety_days", "What would make the next 90 days in the circle worth it?",
       kind="long", max_length=1000),
    _q("can_offer", "What can you genuinely help another member with?",
       kind="long",
       hint="Introductions, a skill, a hard-won mistake — anything real.",
       max_length=1000),
    _q("help_style", "When you bring a problem, what do you want back?",
       kind="choice",
       options=["Blunt feedback", "Questions that make me think",
                "An introduction to someone", "Accountability and a deadline",
                "Someone to just listen first"]),
    _q("hours", "Where are you, and when do you work?",
       hint="Timezone and the hours you're actually reachable.",
       placeholder="IST, usually 10am–7pm", max_length=200),
    _q("assistant_focus", "What should your assistant be good at for you?",
       hint="Writing, pricing, hiring, strategy, code review — whatever you'll actually use it for.",
       max_length=400),
    _q("remember", "Anything it should always remember about you?",
       kind="long",
       hint="How you like to be spoken to, what you never want suggested, context that saves you re-explaining.",
       max_length=1000),
]


def questions_for(role: str) -> list:
    """The interview for one role, capped. Unknown roles get nothing to answer —
    staff are not interviewed, and returning an empty list is what lets the
    gate resolve to 'complete' for them rather than to an error."""
    if role == CLIENT_ROLE:
        return CLIENT_QUESTIONS[:MAX_QUESTIONS]
    if role == FOUNDING_ROLE:
        return FOUNDING_QUESTIONS[:MAX_QUESTIONS]
    return []


def is_complete(role: str, answers: Optional[dict]) -> bool:
    """Every question answered with something that isn't whitespace.

    Whitespace is checked rather than presence because a required field that
    accepts a single space is not a required field.
    """
    given = answers or {}
    return all(str(given.get(q["key"], "")).strip() for q in questions_for(role))


def summarise(role: str, answers: Optional[dict]) -> str:
    """The interview, rendered for a system prompt.

    Prompt text rather than JSON: a model reads 'What does your business do? —
    We sell…' more reliably than it reads a nested object, and this string is
    prepended to every single request the person makes, so it has to be cheap
    and unambiguous.
    """
    given = answers or {}
    lines = []
    for q in questions_for(role):
        value = str(given.get(q["key"], "")).strip()
        if value:
            lines.append(f"- {q['prompt']} — {value}")
    return "\n".join(lines)

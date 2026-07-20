# ADR 0005 — AI as a platform layer, not an SDR feature

**Status:** Accepted · **Date:** 2026-07-20

## Context

The agent runtime — run recording, cost ceilings, guardrails, retries, the
job queue — was built inside the SDR module because that is where the first
agents were needed. None of it is sales-specific.

Meanwhile the host app already had six AI features predating this work: the
CRM chat assistant, email writer, proposal writer, meeting summariser, lead
reply drafter, and the Lead Finder pitch writer. They had no run log, no cost
tracking, and no failure visibility. An "AI Agents" page that showed only the
five newest agents would be a module page wearing a platform's name — and the
question an owner actually asks is "is my AI working and what is it costing
me", across everything.

## Decision

**1. Categories, not modules.** Every AI capability declares what it is *used
for* (`sales`, `content`, `delivery`, `support`, `insight`) independent of
which module implements it. The monitor groups by that.

**2. Two kinds, one log.** *Agents* are `Agent` subclasses run by the queue,
with schemas and guardrails. *Assistants* are the host's existing endpoints,
instrumented with a context manager rather than rewritten. Both write to
`sdr_agent_runs`, so one view covers everything.

Rewriting the six existing features as agents was rejected: they work, they
are in production, and the value here is visibility, not uniformity. A
decorator per endpoint buys ~90% of the benefit at ~5% of the risk.

**3. `record_assistant` never raises.** Monitoring must not be able to break
the feature it monitors. Every failure path is swallowed and logged — a
problem writing a run cannot turn a working AI feature into a 500. There is
a test for this.

**4. Free providers as a chain, not a choice.** Six providers with genuine
free tiers, all OpenAI-protocol compatible, tried in priority order. A rate
limit or quota refusal falls through to the next. Single-provider free tiers
are unusable in production because they *will* refuse you; a chain is what
makes free viable. Groq and Cerebras lead because their limits reset per
minute, so a refusal costs seconds rather than a day.

**5. Navigation reorganised.** A top-level "AI Agents" section holds the
monitor plus every AI-driven surface (AI SDR, Lead Database, Lead Finder,
Website Audits, Deliverability). "Sales" keeps the non-AI CRM pages.

## Consequences

**Good.** The monitor is genuinely complete — 11 capabilities across 4 use
cases from day one, not just SDR. Adding a provider is one registry entry and
an env var, with no frontend change since the UI renders from the API. Any
future module gets run recording, cost tracking and the provider chain for
free.

**Bad.** The implementation still lives under `backend/sdr/agents/`, which no
longer matches what it is. Moving it to a top-level package is the right
eventual shape but is a large rename against a live deployment days before
launch, so it is deferred. `backend/ai_platform.py` is the facade that gives
the correct model now; the directory catches up later.

**Watch.** Streaming responses carry no usage object, so token counts for the
streamed assistants are approximated from text length. They are labelled as
estimates, consistent with `cost_usd_estimated` elsewhere — but they are
rougher than the agent numbers, which use the provider's reported usage.

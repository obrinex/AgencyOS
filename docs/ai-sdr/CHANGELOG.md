# AI SDR — Changelog

---

## Phase 5b — The outreach engine (2026-07-20)

Campaigns, sequences, drafting, approval and dispatch. **Ships in simulate
mode**: the entire pipeline runs and stops one call short of the wire.

### The shape

A **campaign** snapshots its sequence at launch (editing a sequence later must
never change what a running campaign sends). An **enrollment** is one lead's
journey through it. A **message** is one email, drafted to delivered.

Default sequence is three touches over eight days — opener, different angle,
breakup. Steps carry a *writing instruction*, not a template: copy is
generated per lead from that lead's audit and research.

### Not sending is the feature

The stop conditions get more code than the send path, because a sequence that
keeps writing after a reply is worse than one that never started:

| Trigger | Result |
|---|---|
| Lead replies | Enrollment stops, pending drafts cancelled |
| Unsubscribe / bounce / complaint | Suppressed, stopped, permanent |
| Stage → won/lost/rejected/archived | Stopped |
| Campaign stopped | All enrollments stopped |
| No lawful basis for their country | Stopped before a token is spent |

Re-checked at **draft time and again at dispatch** — the world moves in
between, and a reply arriving after approval must still kill the email.

### Double-send safety

The question the send agent is built around. Three layers, each covering what
the previous cannot:

1. Job idempotency keys block duplicate enqueues.
2. A unique `(enrollment, step)` index blocks duplicate drafts even after job
   records expire.
3. An atomic `approved → sending` claim blocks duplicate dispatch.

A retry that finds a message already in `sending` **does not call the
provider** — a previous attempt died mid-call and the outcome is unknown, so
it parks in `needs_review` for a human. Uncomfortable and correct: the
alternative is guessing, and a wrong guess is either a duplicate email or a
silently lost one. Refusals we can *classify* as not-sent (rate limit, quota)
release their claims and retry; anything ambiguous keeps them.

### Copy checks

Deterministic, run after the model has been asked nicely — and again on human
edits, because an operator's paste can fail hygiene as easily as a model's
draft. Blocks URLs (text-only by design), unfilled `[placeholders]`,
do-not-say terms, spam phrasing, over-length copy.

### Verified

- **486 tests pass** (up from 441), including: reply-between-approval-and-send,
  crashed-send never redials, rate-limit releases claims, ambiguous failure
  keeps them, forged and stale webhooks refused, daily new-lead cap paces
  step 1.
- **Live, end to end**: imported a lead → processed → qualified → created and
  launched a campaign → the tick queued a draft → the **real model wrote a
  grounded email** citing an actual detected gap (`no_chatbot`) → approved in
  the UI → scheduled for **17:34 IST Monday**, correctly inside the
  recipient's business hours with jitter applied.
- **The copy checks caught a human edit in the browser**: pasting a tracking
  URL into an approved draft was rejected with the reason.
- Deployed; no regressions; webhook fails closed (503) with no secret set.

### Wired but dormant

- `RESEND_WEBHOOK_SECRET` is unset, so delivery/bounce/complaint events are
  refused rather than trusted. Set it in Resend + Vercel to close the loop on
  bounce suppression.
- `send_mode` stays `simulate` until a domain passes DNS and warms up. Going
  live is an admin-only, separately-audited flip behind a confirmation.
- Inbound replies are still manual (`Mark replied` on a lead) until Phase 6.

## AI becomes a platform layer (2026-07-20)

The agent runtime stopped being an SDR feature. See ADR 0005.

### Free AI providers, chained

Six providers with genuine free tiers, all OpenAI-protocol compatible:
**Groq · Cerebras · Google Gemini · NVIDIA NIM · OpenRouter · Mistral**.

Tried in priority order — a rate limit or quota refusal **falls through to the
next provider** rather than failing the job. That is what makes free tiers
usable: any single one will refuse you eventually. Groq and Cerebras lead
because their limits reset per minute, so a refusal costs seconds not a day.

Order is set by `SDR_LLM_PROVIDERS`; each provider needs only its own env var.
With nothing configured it falls back to the existing NVIDIA setup, so this
changed no behaviour on deploy. The run log records which provider actually
served each call, so a quality or latency shift can be attributed.

### The monitor covers everything, not just SDR

The host app already had six AI features with no run log, no cost tracking and
no failure visibility. They are now **instrumented rather than rewritten** —
one context manager each:

| Use case | Capabilities |
|---|---|
| Sales & outreach | 5 SDR agents + lead reply drafter + Lead Finder pitch writer |
| Content & writing | Email writer, proposal writer |
| Delivery & projects | Meeting summariser |
| Insight & analysis | CRM assistant |

**11 capabilities across 4 use cases.** Agents and assistants are visually
distinguished but share one run log, so success rate, latency and spend are
comparable across all of them.

`record_assistant` **never raises** — monitoring must not be able to break the
feature it monitors. There is a test asserting a dead database still leaves the
AI feature working.

### Navigation

New top-level **AI Agents** section: Agent Monitor, AI SDR, Lead Database,
AI Lead Finder, Website Audits, Deliverability. "Sales" keeps the non-AI CRM
pages (Pipeline, Contacts, Emails, Proposals).

### Verified

- **441 tests pass** (up from 414), including provider fallback on a simulated
  429 and the assertion that a recording failure cannot break a feature.
- **Live**: ran the real email writer and meeting summariser, then confirmed
  both appeared in the monitor with true timings (7,468ms and 3,686ms), cost
  and provider — features that had *never* been observable before.
- Deployed; no regressions.

### Found while building

- I instrumented `_complete_and_save` first, but the endpoints actually use
  `_stream_and_save` — so nothing recorded. The `kind` keys were wrong too.
  Caught by checking the monitor for real rather than trusting the wiring.
- Streaming responses carry no usage object, so those token counts are
  approximated from text length. Rougher than the agent figures, and labelled
  as estimates.

## Volume sized to the Resend free plan (2026-07-20)

Resend is already connected. Its free tier allows **1,000 emails/day and
3,000/month** — and the monthly figure is the one that binds.

### The correction worth knowing

New leads per day is **not** emails per day. A sequence sends roughly one
email per touch, so a 3-touch sequence multiplies the lead rate by three at
steady state:

| New leads/day | Emails/month (3 touches) | Fits 3,000? |
|---|---|---|
| 30 | 2,700 | **yes** |
| 40 | 3,600 | no — quota gone ~day 25 |
| 50 | 4,500 | no — quota gone ~day 20 |

Running out mid-month is worse than starting slower: prospects get an opener
and one follow-up, then silence, which reads as a bot that broke.

**Default set to 30 new leads/day**, the top of what the plan sustains at three
touches. The requested 30–50 range is configurable, but 40 and 50 are flagged
as over-budget rather than silently accepted.

### Built

- `sdr/domain/quota.py` — pure plan maths: sustainable lead rate, projected
  monthly volume, plan-fit verdicts, remaining budget. Provider plans as a
  registry (`resend_free`, `resend_pro`, `custom`).
- **Three distinct caps**, because conflating them is the whole bug:
  `daily_new_leads_cap` (30), `daily_send_cap` (100 total incl. follow-ups),
  `monthly_send_cap` (3,000).
- **Monthly quota enforced in pre-flight**, on its own month-scoped counter.
  Not summed from daily counters — those expire after a week, so summing
  would under-report and let the cap be blown.
- `release_claim()` now hands back the monthly slot too, so a provider outage
  cannot silently consume a month of quota.
- The org daily cap now counts across *all* identities, not one — two
  identities previously doubled the intended ceiling.
- `GET /api/sdr/quota` and `POST /api/sdr/quota/simulate`.
- **Volume & quota** tab on the Deliverability page: live monthly/daily
  meters, and a planner that recomputes as you type.

### Verified

- **414 tests pass** (up from 394), including the exact 30/40/50 case and a
  test asserting the *shipped defaults* fit the configured plan.
- In the browser: meters reading `0 / 3,000` monthly and `0 / 100` daily;
  typing `50` immediately warns *"about 4,500 emails/month, over the 3,000
  limit… would run out around day 20… Recommended: 30 new leads/day."*
- Deployed to production, no regressions, no startup errors.

## Deployed to production (2026-07-20)

Live at [obrinexcrm.vercel.app](https://obrinexcrm.vercel.app) (frontend) and
`backend-five-hazel-13.vercel.app` (API). Module ships **disabled** — all
channels off, nothing runs or sends until it is switched on.

### ⚠️ Incident: the first deploy took production down

**What happened.** The first backend deploy 500'd *every* endpoint in the
application, including pre-existing ones (`/api/leads`, `/api/clients`,
`/api/invoices`). Outage lasted about four minutes.

**Cause.** `create_sdr_indexes()` declared a partial index with
`partialFilterExpression: {"stage": {"$nin": [...]}}`. MongoDB only accepts a
restricted operator set there and rejects `$nin` outright
(`CannotCreateIndex: Expression not supported in partial index: $not`). The
exception escaped `create_indexes()` inside the FastAPI startup event, so the
app failed to boot and Vercel returned 500 for everything.

**Why tests missed it.** mongomock does not validate index specifications, so
`create_sdr_indexes()` ran green locally against the mock. The suite proved the
code executed, not that MongoDB would accept it.

**Response.** Rolled back to the previous production deployment first
(`vercel promote`) to restore service, then fixed and redeployed.

**Fixes.**
1. The partial filter is now `{"sdr_managed": True}` — a simple equality, and
   better scoped anyway since the index exists for SDR-managed leads.
2. **Blast radius closed.** Every index now goes through `_safe_index()`,
   which logs and continues. A rejected spec can no longer abort startup, and
   one bad spec no longer skips the indexes after it. This module must never
   be able to take the host application down.
3. `PARTIAL_FILTER_SAFE_OPERATORS` documents the accepted set, and
   `tests/sdr/test_index_specs.py` parses the source AST to enforce it —
   verified to fail on the original `$nin` and pass on the fix.

**Lesson worth keeping.** A shared startup path is a shared failure domain.
Anything a feature module adds there needs to be non-fatal by construction,
because the cost of a mistake is the whole app, not the feature.

### Also changed for deploy

- The third cron entry (`/api/automations/cron/sdr`) was **removed** from
  `vercel.json` — the Hobby plan caps cron count, and the two existing jobs
  (payment reconciliation, reminders) matter more. The endpoint still exists;
  the external pinger is the real scheduler per ADR 0003.

### Verified in production

| Check | Result |
|---|---|
| `/api/` | 200 |
| Pre-existing endpoints (`/api/leads`, `/api/clients`, `/api/invoices`, `/api/auth/me`) | 401 — auth required, no regression |
| SDR endpoints (`/api/sdr/*`) | 401 — registered and guarded (were 404) |
| Forged unsubscribe token | 400 — signature check live |
| Index failures in startup logs | none |
| `obrinexcrm.vercel.app`, `/ai-sdr` route | 200 |
| Shipped JS bundle | contains AI SDR, Lead Database, Website Audits, Deliverability |

### Security verification in production (unauthenticated)

| Check | Result |
|---|---|
| All 5 SPA routes (`/ai-sdr`, `/leads`, `/audits`, `/deliverability`, `/agents`) | 200 |
| Route guard: anonymous `/ai-sdr/deliverability` | redirects to `/login` |
| 11 SDR read endpoints, anonymous | all 401 — none reachable |
| Admin writes (create identity, kill switch, add/remove suppression), anonymous | all 401 |
| `/api/automations/cron/sdr` without `CRON_SECRET` | 401 |
| Forged unsubscribe token, GET and POST | 400 both |
| Console errors on the live site | none |

**Not verified:** the *visual* rendering of the logged-in pages. That needs a
human session, and the credentials for it are not something to hand to an
agent — the same bundle was verified extensively against the same API contract
locally, so the residual risk is cosmetic rather than functional.

Running record of what each phase delivered. See
`00-existing-architecture-report.md` for the forensics that shaped all of it.

---

## Phase 5a — Deliverability and compliance core (2026-07-20)

**Sending remains off.** This is the layer that decides whether a message is
*allowed* to go out; nothing sends yet. Built now rather than after launch
because warm-up needs weeks of domain reputation — the identities and DNS
checks have to exist before 1 August for a first send to be possible after it.

### Created

**Pure domain**
- `sdr/domain/warmup.py` — the volume ramp (5/day to target over ~3 weeks) and
  reputation thresholds. Bounce ≥3% throttles, ≥5% pauses; complaints are
  judged an order of magnitude tighter. A blocked identity is never
  auto-restored.
- `sdr/domain/send_window.py` — business hours in the **recipient's** timezone,
  with public holidays and deterministic per-message jitter. Parses before
  comparing, because lexicographic comparison across offsets is wrong.

**Services**
- `sdr/services/dns_check.py` — real SPF/DKIM/DMARC/MX lookups via dnspython
  (already a dependency). Catches the invisible misconfigurations: multiple
  SPF records (a permerror receivers treat as *no* SPF), `+all`, revoked DKIM
  keys, `p=none` DMARC.
- `sdr/services/preflight.py` — the single gate every send passes. Ten checks,
  ordered cheapest-and-most-absolute first, each returning a reason.

**Repositories**
- `identities.py` — sending identities with DNS state, warm-up, health, and an
  **atomic** rate limiter (`$inc`, not read-modify-write — under concurrent
  drains a read-then-write races and lets both callers past the cap).
- `suppression.py` — suppression list, consent audit trail, and HMAC-signed
  unsubscribe tokens.

**Public** — `GET/POST /api/public/sdr/unsubscribe`, one-click, unauthenticated
by necessity, signed so the URL cannot be edited to suppress a third party.

### Verified

- **388 tests pass** (up from 333).
- **Live DNS against several real domains**, with correct per-record verdicts
  including the failure cases (missing selector, `p=none` DMARC).

### Design decisions worth knowing

- **The rate-limit slot is claimed last.** Everything that can refuse refuses
  first, because claiming consumes allowance — a message refused after the
  claim burns a send that never happened.
- **A domain-capped send releases the identity slot too.** Otherwise a
  domain-capped recipient quietly eats the identity's daily allowance.
- **GET on unsubscribe does not mutate.** Mail clients and security scanners
  prefetch links; unsubscribing on GET would opt out people who never clicked.
- **Suppression is checked before anything is consumed**, and there is a test
  asserting a suppressed recipient burns zero allowance.

### What a sending domain will need

No sending domain has been chosen yet. Whichever one is used, the gate
requires all three of SPF, DKIM and DMARC to pass before an identity can be
activated — and the DNS checker was exercised live against several real
domains to confirm it reports each record correctly.

The two things that most commonly block activation, in practice:

- **A DKIM selector.** DKIM records live at `<selector>._domainkey.<domain>`
  and selectors cannot be enumerated, so the checker reports `unknown` rather
  than guessing. The email provider issues the selector when the domain is
  verified with them.
- **DMARC at `p=none`.** Valid, and the correct starting point, but it
  enforces nothing — so it is reported as a warning rather than a pass.

Warm-up then takes about three weeks from activation, so whenever a domain is
picked, that ramp is the long pole for outreach — not the code.

### Deliverability page (added same day)

`/ai-sdr/deliverability`, inside the existing dashboard shell — one route, one
`NAV_SECTIONS` entry, existing primitives only. No new layout, no new design
system. Three tabs:

- **Sending identities** — add an address, run a live DNS check, see per-record
  SPF/DKIM/DMARC/MX verdicts, watch the warm-up ramp and reputation, start or
  pause warm-up.
- **Suppression list** — searchable, with counts by reason, add entries, and
  admin-only removal behind a confirmation that explains the consequence.
- **Test a send** — dry-runs the real pre-flight gate and shows every check
  with its verdict. Releases the rate-limit slot it claims, so testing never
  consumes an identity's daily allowance.

**Verified in the browser against live DNS**, not stubs:
- A real DNS check rendering all four record verdicts (MX, SPF, DKIM, DMARC).
- **"Start warm-up" refused** for a domain with no DKIM selector — the
  identity stayed `PAUSED` and the error named the exact fix. This is the
  gate working: an unverified domain cannot be activated.
- The pre-flight tester correctly refusing a suppressed address
  (`suppressed — email suppressed (unsubscribe)`), and correctly refusing on
  `channel_disabled` first when email was off — the ordering is deliberate.
- Zero console errors.

The email channel was temporarily enabled to demonstrate the suppression
check, then **set back to off**, which is the correct shipping state.

### Not built yet (rest of Phase 5)

Campaigns, sequences, the Personalization/Outreach/Follow-up agents, A/B
testing, and the Outreach and Campaigns pages. The gate for those — *a campaign
sends real personalised email with all pre-flight checks enforced* — cannot be
met until a domain passes DNS anyway.

---

## Phase 4 — Research and scoring (2026-07-20)

### Created

**Detection and audit**
- `sdr/services/safe_fetch.py` — SSRF-guarded fetching. Resolve-then-validate,
  every redirect hop revalidated, private/link-local/metadata ranges refused
  in v4 and v6. Every URL the auditor touches is prospect-controlled, which
  makes this the module's most directly attackable surface.
- `sdr/domain/detect.py` — pure HTML detection: TLS, mobile viewport, forms,
  chat/booking/CRM/analytics/automation vendors, WhatsApp, click-to-call,
  structured data, SEO structure, response time.
- `sdr/agents/website_audit/` — deterministic, **no LLM**. Every output is a
  factual claim about a real business that ends up in an email to them; a
  model adds nothing to "does this HTML contain a form" and adds a way to be
  confidently wrong.
- `sdr/repositories/audits.py` — append-only audits, replaced-per-audit signals.

**Scoring and research**
- `sdr/agents/scoring/` — `lead_scoring` and `lead_qualification`, both
  deterministic wrappers over the Phase 1 domain layer. Hard rules
  (suppression, DNC, no contact route, no compliance profile, already a
  client) beat any score.
- `sdr/agents/research/` — the one LLM agent here. Produces the pitch angle,
  constrained to cite a signal that was actually detected.
- `sdr/services/enrich_chain.py` — enrich → audit → research → score →
  qualify, inline or queued, one correlation id across all five.

**UI** — `SDRAudits.jsx` (gap frequency across all prospects, audit drawer,
scope disclaimer), plus signals, ROI-with-assumptions and a Process action in
the lead drawer.

### Verified

- **333 tests pass** (up from 277).
- **The Phase 4 gate, end to end against a live website and the live model:**
  a lead flowed discovery → audit → 9 detected gaps → score 57 → qualified,
  with a per-component breakdown and a grounded pitch angle tied to a real
  signal.
- **In the browser:** the Audits page showing real gap frequencies, and the
  lead drawer rendering the full breakdown, all nine signals with evidence
  coverage, and an ROI estimate with its assumptions behind a disclosure.

### Two real bugs, both found by running it for real

1. **The grounding guardrail was over-firing and suppressing every pitch
   angle.** The model cited evidence as `"country_code: IN"` rather than
   `"IN"`; grounding only matched bare values, so it rejected perfectly
   traceable citations. `collect_grounding_facts` now emits both forms. A
   guardrail that fires on everything gets switched off, which is worse than
   one calibrated to the shapes real output takes.
2. **The inline chain exceeded Vercel's request ceiling.** A live run
   finished at **64 seconds** with nothing deferred, because the budget only
   checked elapsed time — every step started under budget and then overran.
   It now reserves each step's worst case (`elapsed + timeout <= ceiling`)
   and queues what does not fit. Conservative in the common case, correct in
   the bad one.

### Honest limitations

- **No Playwright, no Lighthouse, no Core Web Vitals.** Vercel's Python
  runtime has no Chromium and a 60-second ceiling (ADR 0004). Audits run over
  HTTP. Six of nineteen signals depend on facts this cannot measure and
  therefore never fire — by design, they claim nothing rather than guessing.
  Every audit records its `unmeasured` list and the UI shows it, so a clean
  audit does not read as a clean bill of health.
- `poor_website_performance` and `poor_seo` fall back to measurable proxies
  (server response time, structural SEO checks). Named `seo_score_basic`, not
  `lighthouse_seo`, so nobody mistakes it for the real audit.
- Competitor analysis is **not built** — it was Phase 4 scope in the spec and
  is deferred. It needs external search, and no compliant search provider is
  configured.

---

## Phase 3 — Agent runtime (2026-07-20)

### Created

**The runner and its guarantees**
- `sdr/agents/base/agent.py` — the `Agent` contract and runner. Run recording,
  output validation, cost ceilings, timeouts and guardrail capture live in
  `run()`, not in each agent. With 21 agents planned, anything optional would
  eventually be skipped by the agent that most needed it.
- `sdr/agents/base/guardrails.py` — prompt-injection fencing, grounding checks,
  PII/secret redaction.
- `sdr/agents/base/cost.py` — token accounting and per-run ceilings. Figures are
  labelled `cost_usd_estimated` because NVIDIA NIM bills in credits, not tokens.
- `sdr/agents/base/llm.py` — JSON completion with one repair attempt, over the
  host app's existing NVIDIA client.
- `sdr/domain/backoff.py` — exponential backoff with jitter, per-queue budgets.
- `sdr/repositories/agent_runs.py` — the observability spine, with
  `correlation_id` traces and 24h health stats.

**The queue (ADR 0003)**
- `sdr/services/jobs.py` — enqueue with unique idempotency keys, atomic
  claim-with-lease, retry, dead-letter, replay, and a time-boxed `drain()`.
- `/api/automations/cron/sdr` — the drain entrypoint, behind the existing
  `CRON_SECRET` guard. A daily Vercel cron is registered as a floor; the real
  cadence comes from an external pinger every few minutes.

**The reference agent**
- `sdr/agents/enrichment/` — schema, versioned prompts, agent. Providers first,
  model second, grounding checked before anything is written. Never overwrites
  an existing value with an inference; never outputs contact details at all.

**UI**
- `pages/sdr/SDRAgents.jsx` — agent health, queue stats, run list, run
  inspector, dead-letter tab with one-click replay.

### Verified

- **277 tests pass** (up from 205).
- **The Phase 3 gate, for real:** 100 leads enqueued, drained, and enriched —
  100 runs recorded, 90 complete / 10 honestly marked unenriched, cost
  accounted, re-enqueueing the same batch a no-op. Separately: a job failing 5
  times, dead-lettering, and being replayed to success after the cause was fixed.
- **In the browser:** enqueued and drained 5 real enrichment jobs, then opened
  the run inspector. It shows the distinction that matters — the *run* succeeded
  while the *enrichment* failed (`"no website content to infer from"`) — so job
  health and data quality are never conflated.
- `craco build` clean; still 15 pre-existing warnings, none from new code.

### Found along the way

- **A scoping bug in my own runner**, caught before it shipped: Python unbinds
  `except ... as exc` at the end of the block, so the repair prompt referenced a
  dead name and would have raised `NameError` on every malformed LLM response —
  i.e. exactly when the repair path was needed.
- **`routers/ai._get_client()` raises a FastAPI `HTTPException`** when
  `NVIDIA_API_KEY` is missing. Correct in a request handler, wrong in an agent:
  it escaped untyped and looked like a crash. Now converted to a non-retryable
  `LLMNotConfiguredError`, so a missing key degrades to partial enrichment
  instead of burning five retries on a config problem.
- **Two test expectations of mine were wrong, not the code.** An unfetchable
  company is marked `failed`, not `partial` — we learned nothing about it, and
  saying otherwise would inflate enrichment coverage.

### Known gaps

- One agent of the planned 21. The rest land in Phase 4+.
- Enrichment has no enrich-capable provider wired yet (Google Places supports
  it but is unconfigured), so provider-first ordering is exercised in tests
  rather than against a live API.
- No stale-queue alert. If the external pinger dies, work accumulates silently;
  `oldest_queued_at` is exposed on the Agents page but nothing watches it.
- Live behaviour against a real model is unverified — no `NVIDIA_API_KEY`
  locally, so the LLM path is covered by stubs and by the graceful-degradation
  path only.

---

## Phase 2 — Data layer, providers and the lead database (2026-07-20)

### Created

**Domain (pure, tested)**
- `sdr/domain/normalize.py` — domain/name/phone/email canonicalisation. Phone
  parsing is best-effort E.164 and returns `None` rather than guessing: a wrong
  number routes a real message to a real stranger.
- `sdr/domain/dedupe.py` — multi-signal matching (domain → registration id →
  fuzzy name + city at 0.85 trigram similarity), field-level merge with source
  precedence, and batch collapsing.

**Providers**
- `sdr/providers/base.py` — the `DataProvider` port, canonical record shapes,
  and `clean()`, which is what actually stops vendor field names leaking past
  an adapter.
- `sdr/providers/osm_overpass.py` — the workhorse. No API key, wraps the
  approach already proven in `routers/leadfinder.py`.
- `sdr/providers/google_places.py` — real adapter, gated on
  `GOOGLE_PLACES_API_KEY`. Unconfigured, it reports itself unavailable and the
  registry skips it rather than failing the run.
- `sdr/providers/csv_import.py` — first-class provider so the module is useful
  with zero paid keys.
- `sdr/providers/registry.py` — capability matching, cost ordering,
  `SDR_PROVIDER_PRIORITY` override.

**Everything else**
- `sdr/dto/filters.py` — `DiscoveryFilters`, the single source of truth for
  search. The UI filter panel renders from its JSON Schema.
- `sdr/repositories/companies.py`, `leads.py` — upsert-with-merge, keyset
  pagination, stage transitions, soft delete.
- `sdr/services/discovery.py` — provider fan-out → post-filter → dedupe →
  storage, with partial success as a normal outcome.
- 16 new endpoints; `pages/sdr/SDRLeads.jsx` plus three SDR components.
- `tests/sdr/test_integration_import.py` — 18 tests against an in-memory Mongo.

### Modified

| File | Change |
|---|---|
| `backend/routers/sdr.py` | 16 endpoints added |
| `frontend/src/App.js` | `/ai-sdr/leads` route |
| `frontend/src/components/layout/Sidebar.jsx` | Lead Database nav entry |
| `frontend/src/lib/statusConfig.js` | **`interested` stage added** — see below |

**Why `statusConfig.js` changed.** `CRMPipeline.jsx:53` does
`map[l.stage]?.push(l)`, so a lead whose stage is absent from `STAGES_LIST` is
silently dropped from the board. Without adding `interested`, any SDR lead
reaching that stage would vanish from the CRM pipeline. `archived` deliberately
stayed out (it would become a Kanban column) and lives in the new
`lib/sdrConfig.js` instead.

### Verified

- **205 tests pass** (187 domain + 18 integration).
- **The Phase 2 gate, for real:** a 1,200-row CSV containing 200 deliberate
  duplicates imported to exactly 1,000 companies and 1,000 leads, then filtered
  and paginated with non-overlapping keyset pages.
- **Rendered in a browser** against an in-memory Mongo: logged in, imported a
  CSV through the real endpoint (7 rows → 1 skipped → 1 deduped → 5 companies),
  opened the lead drawer, and confirmed SDR leads appear on the existing CRM
  Kanban with the new INTERESTED column in place.
- Phone `020-2456-7890` → `+912024567890` and `https://www.brightsmile.in/…` →
  `brightsmile.in` confirmed visually in the drawer.
- `craco build` compiles clean; still 15 pre-existing warnings, none from new code.

### Found along the way

- **A real dedupe bug, caught by a test.** A company named only `"Ltd"`
  normalised to `"ltd"`, which would have given every junk-named record in a
  city the same dedupe key and merged unrelated businesses. Fixed in
  `normalize_name`.
- **The port mismatch is real and bites immediately.** `AuthContext` posts
  login same-origin (CRA proxy → :8000) while axios uses
  `REACT_APP_BACKEND_URL` (:8001). Local dev needs both aligned.
- **Pre-existing a11y issue, not fixed:** `CommandPalette`'s `CommandDialog`
  renders a `DialogContent` with no `DialogTitle`, logging a Radix screen-reader
  error on every page. Shared component, out of scope here.

### Known gaps

- Discovery runs inline, not queued — fine within the 60s ceiling for
  operator-triggered searches, but scheduled discovery needs Phase 3's runner.
- Enrichment, website audits and scoring are wired but not yet populated:
  every lead currently scores 0 until Phase 4.
- `mongomock` does not enforce unique indexes, so `dedupe_key` uniqueness is
  covered at the application level only. The index is the race backstop and
  only a real MongoDB proves it.

---

## Phase 1 — Foundation (2026-07-20)

Scope agreed with the owner: **Phases 0–4 before the 1 August launch**, with no
automated outbound sending. Scheduling runs off an external pinger rather than
a paid Vercel plan.

### Created

**Backend**
- `sdr/errors.py` — typed error hierarchy, each carrying `retryable` so the job
  runner can distinguish a transient provider failure from a bad input.
- `sdr/domain/pipeline.py` — lead stage state machine. Adopts the eleven stages
  already stored in `leads.stage` and adds `interested` and `archived`.
- `sdr/domain/scoring.py` — deterministic 0–100 score with a per-component
  explainable breakdown, versioned via `SCORING_VERSION`.
- `sdr/domain/signals.py` — declarative registry of 19 opportunity signals.
  Detectors return `None` for undeterminable, which yields no signal — a failed
  crawl must never become a claim in an outreach email.
- `sdr/domain/roi.py` — ROI model with diminishing returns across gaps, and
  assumptions returned alongside every figure.
- `sdr/config/countries.py` — country registry (IN, US, GB, AE + DEFAULT) with
  compliance profiles (DPDP, GDPR, CAN-SPAM, DEFAULT) and holiday calendars.
- `sdr/config/benchmarks.py` — versioned industry benchmarks with source notes.
- `sdr/collections.py` — collection names and idempotent index creation.
- `sdr/repositories/` — `base.py` (the tenancy chokepoint + keyset pagination),
  `settings.py` (singleton, feature flags, kill switch), `overview.py`.
- `routers/sdr.py` — 9 endpoints under `/api/sdr`.
- `pages/sdr/SDROverview.jsx` — Overview page in the existing shell.
- `tests/sdr/` — 95 tests over the pure domain layer. The first tests in this
  repo.
- `docs/ai-sdr/` — architecture report, ADRs 0001–0003, this changelog.

### Modified

| File | Change |
|---|---|
| `backend/server.py` | one import + one `include_router` line |
| `backend/auth_utils.py` | `"ai_sdr"` added to `PERMISSION_MODULES` |
| `backend/database.py` | `create_indexes()` now calls `create_sdr_indexes()` |
| `frontend/src/App.js` | import + one `/ai-sdr` route in the staff block |
| `frontend/src/components/layout/Sidebar.jsx` | `Bot` icon + one `NAV_SECTIONS` entry under Sales |
| `frontend/src/lib/api.js` | `fallbackForGet` entries for the two SDR object endpoints |

**Deleted: nothing.**

### Reused rather than rebuilt

Auth (`get_current_user`, `require_module`, `require_admin`), the `leads` /
`lead_activities` / `contacts` collections, `AppLayout` + `NAV_SECTIONS`,
`PageHeader` / `EmptyState` / `Card` / `Dialog` / `Switch`, sonner toasts,
`log_audit`, the `system_state` idempotency pattern, and the Fernet secret
encryption approach from `vault.py`.

### Verified

- `pytest tests/sdr` — **95 passed**.
- App boots with **9 SDR routes** registered; 207 total routes, no regression.
- `craco build` — **compiles clean**; 15 pre-existing `exhaustive-deps`
  warnings, none from new code.

### Not verified

**The page has not been rendered in a browser.** There is no local MongoDB or
Docker available, and the only reachable database is production Atlas — booting
against it would run `create_sdr_indexes()` as a real production write. Needs a
local Mongo or an explicit go-ahead.

### Known gaps carried forward

- The job runner is specified (ADR 0003) and its schema and indexes exist, but
  the runner itself lands in Phase 3.
- `sdr_agent_runs` and `sdr_jobs` are indexed but not yet written to, so the
  Overview health panel reads zeroes until Phase 3.
- Deliverability (identities, DNS, warm-up, suppression enforcement) is
  Phase 5. Every outbound channel ships **off** by default.

# Obrinex AI SDR — Session Handoff

Everything below is current as of **20 July 2026**. Launch is **1 August 2026**.

---

## 0. The two projects

| | Path | Deployed |
|---|---|---|
| **Website** | `C:\Grin\Obrinex Agency AI\obrinex web` | Hostinger (Node app, zip upload) — untouched this session |
| **CRM (AgencyOS)** | `C:\Grin\Obrinex Agency AI\agency dashboard\AgencyOS` | [obrinexcrm.vercel.app](https://obrinexcrm.vercel.app) + `backend-five-hazel-13.vercel.app`, MongoDB Atlas |

Git: AgencyOS only (`github.com/obrinex/AgencyOS`, branch `main`). Root is not a repo.

---

## 1. The stack — read this before writing any code

The AI SDR specification assumed Next.js + TypeScript + Postgres + Prisma +
RLS + pgvector + a job queue. **None of that is what this is.** Phase 0
forensics established the truth, and every decision since follows from it:

| Layer | Reality |
|---|---|
| Backend | **FastAPI + Motor + MongoDB**. No ORM, no migrations. |
| Frontend | **React 19 on CRA/CRACO**. `.jsx` only — `design_guidelines.json` **forbids TypeScript**. |
| UI kit | shadcn/ui (new-york) on Radix, 48 primitives at `@/components/ui/*` |
| Styling | Tailwind, CSS vars, **dark-only** (no light mode, do not add one) |
| Hosting | Vercel serverless, **60s request ceiling**, Hobby plan |
| Tests | 545, all under `tests/sdr/` — the only tests in the repo |

**House conventions that are not optional:** routers declare their own full
`/api/...` prefix; guards are `Depends(...)` on a last param named `user: dict`;
timestamps are **ISO-8601 strings**, never BSON dates; no `response_model`;
lists are row-stacks, never `<Table>` (`ui/table.jsx` exists but zero pages
import it); toasts are **sonner**, not the dead shadcn toast; every interactive
element needs a kebab-case `data-testid`.

Full detail: `docs/ai-sdr/00-existing-architecture-report.md`.

---

## 2. What exists now

**Phases 0–7 are built and tested.** Phases 0–5b are deployed; threading,
inbound replies (Phase 6) and meetings (Phase 7) are built but **not yet
deployed or committed** — see §6.4.

What remains unbuilt is WhatsApp (blocked on Meta approval) and A/B testing
(deliberately deferred — see §10.4).

### Backend — `backend/sdr/`

```
domain/          pure, no I/O, the tested layer
  pipeline.py    lead stage state machine (11 existing stages + interested/archived)
  scoring.py     deterministic 0-100 score with explainable breakdown
  signals.py     19-signal opportunity registry (declarative)
  roi.py         ROI with diminishing returns + stated assumptions
  detect.py      HTML/tech detection from a fetched page
  dedupe.py      multi-signal dedupe + field-level merge
  normalize.py   domain/name/phone/email canonicalisation
  quota.py       provider plan maths (leads/day vs emails/month)
  warmup.py      sending ramp + reputation thresholds
  send_window.py recipient-timezone business hours + jitter
  sequence.py    enrollment stop conditions + due calculation
  copy_checks.py deterministic pre-send copy hygiene
  backoff.py     retry delays, per-queue budgets
config/          countries.py (IN/US/GB/AE + DEFAULT), benchmarks.py
providers/       osm_overpass, google_places, csv_import, email_resend, registry
repositories/    the ONLY place touching db.* — base.py holds the tenancy seam
services/        discovery, enrich_chain, campaigns, jobs, preflight, safe_fetch, dns_check
agents/          base/ (agent, llm, providers, guardrails, cost) + 7 agents
```

**9 agents:** `lead_enrichment`, `website_audit`, `company_research`,
`lead_scoring`, `lead_qualification`, `outreach_personalization`,
`outreach_send`, `inbound_classifier`, `meeting_proposal`.

Two of those nine have **no LLM** (`outreach_send`, `meeting_proposal`) and a
third bypasses it whenever headers are decisive (`inbound_classifier`). That
is the pattern, not an oversight: a model is used for judgement and language,
never for facts the system already knows.

**Platform layer** — `backend/ai_platform.py` + `routers/ai_agents.py`. The AI
monitor covers **11 capabilities across 4 use cases**: the 7 agents plus the
host app's 6 pre-existing AI features (CRM assistant, email writer, proposal
writer, meeting summariser, lead reply drafter, Lead Finder pitch), which were
*instrumented, not rewritten*.

### Frontend — `frontend/src/pages/`

`agents/AIAgentsMonitor.jsx`, `sdr/SDROverview.jsx`, `SDRLeads.jsx`,
`SDRAudits.jsx`, `SDRDeliverability.jsx`, `SDRCampaigns.jsx`, `SDROutreach.jsx`,
`SDRAgents.jsx` + components under `components/sdr/`.

Nav is one **"AI Agents"** section in `Sidebar.jsx` `NAV_SECTIONS`:
Agent Monitor · AI SDR · Lead Database · AI Lead Finder · Campaigns · Outreach ·
Inbox · Website Audits · Deliverability.

### What works end to end, verified live

Import/discover leads → enrich → audit (19 signals) → research → score →
qualify → campaign → AI-drafted email → human approval → scheduled into the
recipient's business hours → simulated send → enrollment advances.

---

## 3. Decisions you must not accidentally undo

Recorded as ADRs in `docs/ai-sdr/adr/`:

1. **0001** — spec vs stack: existing codebase wins on conventions, spec wins
   on functionality.
2. **0002** — **single-tenant on purpose.** The app has no `org_id` anywhere.
   Adding it to SDR tables only would create a *false* security property. All
   queries route through `repositories/base.scope()` so tenancy is one function
   body away when it's done app-wide.
3. **0003** — **no queue product.** `sdr_jobs` collection claimed atomically via
   `find_one_and_update`, drained by cron. Vercel has no long-running process.
4. **0004** — **HTTP audits, no Playwright/Lighthouse.** No Chromium on Vercel
   Python. Six of nineteen signals therefore never fire — by design they claim
   nothing rather than guessing. Every audit records its `unmeasured` list.
5. **0005** — **AI is a platform layer**, not an SDR feature. Categories, not
   modules. Code still lives under `sdr/agents/` — moving it is right but was
   too risky pre-launch.

**Design invariants worth stating plainly:**

- **An absent fact claims nothing.** `signals.detect()` treats missing data as
  "unknown", never as "verified absent". This is what keeps false claims out of
  outreach emails.
- **Not sending is the feature.** Stop conditions (reply, unsubscribe, bounce,
  closed stage, compliance) are checked at draft time *and again at dispatch*.
- **Three layers of double-send protection**: job idempotency keys → unique
  `(enrollment, step)` index → atomic `approved→sending` claim. A retry finding
  `sending` **never calls the provider**; it parks in `needs_review`.
- **Monitoring can't break what it monitors.** `record_assistant` swallows
  every failure — there's a test asserting a dead DB leaves AI features working.
- **Index creation is non-fatal.** Learned the hard way (see §5).

---

## 4. Current state: everything is OFF

| Setting | Value | Meaning |
|---|---|---|
| `module_enabled` | `false` | No agents run |
| `channels.email` | `false` | No sends |
| `send_mode` | `simulate` | Pipeline runs, nothing leaves the building |
| `kill_switch` | `false` | Available, not engaged |
| `daily_new_leads_cap` | `30` | Sized to Resend free tier |
| `monthly_send_cap` | `3000` | Resend free hard limit |

**The quota maths that produced 30:** new leads/day ≠ emails/day. At 3 touches
per lead, 30/day = 2,700 emails/month (fits 3,000). 40/day exhausts the quota
by day 25, 50/day by day 20 — **mid-sequence**, stranding prospects after an
opener and one follow-up. The user asked for 30–50; only the bottom works.

---

## 5. The production incident — do not repeat

The **first** backend deploy 500'd **every endpoint in the app**, not just the
new ones. Outage ~4 minutes.

**Cause:** a partial index used `partialFilterExpression: {"stage": {"$nin": [...]}}`.
MongoDB rejects `$nin` there. The exception escaped `create_indexes()` inside
the FastAPI startup event, so the app couldn't boot.

**Why tests missed it:** mongomock does not validate index specs.

**Fixes:** filter is now `{"sdr_managed": True}`; every index goes through
`_safe_index()` which logs and continues; `tests/sdr/test_index_specs.py`
parses the source AST to enforce the allowed operator set (verified to fail on
the original bug).

**The lesson:** a shared startup path is a shared failure domain. Anything a
feature module adds there must be non-fatal by construction.

Response was: **roll back first** (`vercel promote` to the previous
deployment), then diagnose. Do that again if it happens.

---

## 6. Outstanding — user actions, in priority order

### 6.1 Credentials — four, all exposed in chat, none rotated

| Credential | Risk |
|---|---|
| **Atlas password** | **Highest** — full read/write on the production DB holding client records |
| CRM admin password (`info@obrinex.space`) | Shares the `Obrinex@2009` stem with the website admin phrase — rotate both |
| Cashfree live secret | Payments |
| Groq API keys (×2) | Billing/rate-limit identity; revoke both, generate a third |

I declined to enter any of these — API keys and passwords go in by hand.

### 6.2 Sending domain → the critical path

No domain is chosen. Whichever is used needs **SPF + DKIM + DMARC all passing**
before an identity can be activated (the gate refuses otherwise, by design).
The two usual blockers: no DKIM selector configured, and DMARC at `p=none`.

Then **~3 weeks of warm-up** from a 5/day start. *This is the long pole for any
outreach — the clock starts when the DNS changes are made, not when code is
written.*

### 6.3 Config gaps

- ~~`GROQ_API_KEY`~~ — **DONE (20 Jul).** Set in production and redeployed.
  Active chain is now `groq → nvidia`, model `llama-3.3-70b-versatile`.
  *Caveat: the key's existence and the chain wiring were verified; a real Groq
  completion was never observed, because that needs an authenticated session.
  Confirm on the Agent Monitor — the provider column on new runs should read
  `groq`. If it still reads `nvidia`, the key is being rejected and the chain
  is silently falling through.*
- **External pinger** on `POST /api/automations/cron/sdr` every ~5 min with
  `CRON_SECRET`. Without it, queued agent work never drains. (The Vercel cron
  entry was removed — Hobby caps cron count and the two existing jobs matter
  more.)
- **`RESEND_WEBHOOK_SECRET`** — without it the webhook returns 503 and bounces
  never auto-suppress. Endpoint: `/api/public/sdr/webhooks/resend`.
- **Company postal address** (Settings → Company). Required by CAN-SPAM/PECR
  for US/UK recipients; India's DPDP doesn't need it. Sends to US/UK park in
  `needs_review` without it.

### 6.4 Repo hygiene

- **~60 uncommitted files are live in production.** The backend deploys from
  the working tree via CLI, not git — so `main` cannot reproduce what's
  running. A rollback today restores a version production has never executed.
- `backfill_fx_rates.py` still unrun (USD invoice totals understated).
- Cashfree live transactions still not approved by Cashfree.

---

## 7. Not built (~two-thirds of the spec)

Rest of Phase 5 (A/B testing), Phase 6 (inbound email, threading, conversation
agent), 7 (meetings/calendar), 8 (proposals→contracts→invoices), 9 (analytics,
learning loop, experiments), 10 (WhatsApp/SMS/voice/LinkedIn), 11 (hardening,
load tests), 12 (globalisation). Competitor analysis from Phase 4 is also
deferred — needs a search provider that isn't configured.

Inbound replies are **manual** until Phase 6: a *Mark replied* action on the
lead stops its sequences.

---

## 8. Gotchas that cost time

- Frontend `package.json` proxies to **port 8000**; `.env.development` says
  8001. Wrong port = "could not reach the server".
- Vercel returns `[SENSITIVE]` for env values — `MONGO_URL` is unreadable from
  the CLI. Production DB work needs the string from git-ignored
  `backend/.env.purge`.
- Production admin has **2FA**; the deployed API can't be scripted into.
- `lib/api.js` `fallbackForGet()` resolves failed GETs to `[]`. **Any new GET
  returning an object needs an entry there**, or the page crashes on property
  access when the backend hiccups.
- The dev server uses an **ephemeral database** — restarting it wipes seeded
  data.
- `craco build` with `CI=true` fails on 15 **pre-existing** `exhaustive-deps`
  warnings. Zero come from SDR code. Don't "fix" this by touching those files.
- Streaming AI endpoints (`_stream_and_save`) carry no usage object, so those
  token counts are approximations from text length.

---

## 9. Verification commands

```bash
# Tests (545)
cd "agency dashboard/AgencyOS"
backend/.venv/Scripts/python.exe -m pytest tests/sdr -q

# Boot check
cd backend && MONGO_URL="mongodb://localhost:27017" DB_NAME="s" JWT_SECRET="x" \
  VAULT_ENCRYPTION_KEY="y" ADMIN_EMAIL="a@b.c" ADMIN_PASSWORD="p" \
  .venv/Scripts/python.exe -c "from server import app; print(len(app.routes))"

# Frontend build
cd frontend && npx craco build

# Deploy (backend FIRST, then frontend)
cd backend && npx vercel deploy --prod --yes
cd frontend && npx vercel deploy --prod --yes

# Roll back if production breaks
cd backend && npx vercel ls --prod          # find the last good deployment
npx vercel promote <url> --yes
```

---

## 10. What to build next

### 10.0 Threading headers — **done**

Built, because it was the one thing that could not be retrofitted: a message
sent without a `Message-ID` we chose earns a reply carrying an id we have no
record of, and nothing can match the two afterwards.

- `sdr/domain/email_threading.py` — pure minting and chain logic.
  `Message-ID: <sdr-{message_id}@{domain}>`, deterministic from the row, so a
  reply can be matched by lookup *or* by re-deriving.
- The domain comes from the sending identity, not a separate setting — a
  Message-ID whose domain disagrees with the envelope sender is a spam signal,
  and one source of truth cannot drift.
- Minted at dispatch, not at draft time, because pre-flight only picks the
  sending identity at that point. Stored on the message row in the same write
  that records the send.
- Follow-ups carry `In-Reply-To` and `References`, so the thread holds together
  in the recipient's client — which also reads as a conversation rather than a
  second cold email.
- New: `campaigns_repo.find_by_email_message_id()` — the lookup Phase 6 needs —
  plus sparse and compound indexes for it.

Two refusals worth keeping:

- **A parent that never actually arrived is not a parent.** Rejected drafts and
  simulated rehearsals are excluded from `threading_ancestor()`. Threading under
  one references an id the recipient's client has never seen — an orphan, worse
  than no threading. Half a chain is worse than none.
- **`reply_to_address` defaults to `None`, not `replies@{domain}`.** A Reply-To
  pointing at a mailbox that does not exist bounces the prospect's answer, which
  is strictly worse than the current behaviour (replies go to the From
  identity). Set it in Settings once the mailbox is real and monitored — which
  is the same moment Phase 6 ingestion goes live.

Tests: `tests/sdr/test_threading.py` (10). Suite now 496.

### 10.1 Phase 6 — Inbound replies — **backend done, UI and setup outstanding**

This is what made the system non-autonomous: it drafted, sent and followed up,
but a human had to watch an inbox and click *Mark replied*. Miss that, and the
sequence keeps writing to someone who already answered.

**Transport: Cloudflare Email Routing → Worker → webhook.** Chosen over Resend
inbound (limited), IMAP polling (fragile inside a 60s serverless ceiling) and a
paid parser (another vendor). The Worker source and the full setup runbook are
in [`inbound-worker.md`](./inbound-worker.md).

**What was built:**

| Piece | Where |
|---|---|
| Ingestion endpoint, HMAC-verified, fails closed | `routers/public.py` → `POST /api/public/sdr/webhooks/inbound` |
| Signature + envelope normalization | `sdr/providers/inbound_cloudflare.py` |
| Machine detection, category policy, ID parsing (pure) | `sdr/domain/inbound.py` |
| Storage, dedupe, sender fallback | `sdr/repositories/inbound.py`, collection `sdr_inbound_messages` |
| Classifier agent | `sdr/agents/inbound/` — key `inbound_classifier` |
| Match → classify → act | `sdr/services/inbound.py` |

**The five decisions worth not undoing:**

1. **Headers classify machines, not the model.** RFC 3834 markers and subject
   patterns run *first* and override the classifier entirely. The
   out-of-office trap is the one classification we least want an opinion on,
   and header detection is authoritative, free, and testable without a model.
   The OOO test passes with no classifier stubbed — if it only passed via the
   model, the real protection would not exist.
2. **Only a human reply stops a sequence.** `out_of_office` defers 7 days and
   never stamps the lead. `auto_reply` changes nothing at all. Getting this
   backwards strands a live lead in a state that *looks like* the best outcome
   the system produces, which is why nobody would ever notice.
3. **A sender-address match is a guess, so it asks a human.** Message-ID
   matching is exact; the from-address fallback cannot tell two campaigns
   apart, so anything matched that way is flagged `needs_human`.
4. **Dedupe is an explicit query, not the unique index.** Index creation here
   is deliberately non-fatal (see §5, the outage), so the index may
   legitimately be absent — nothing that must be correct can depend on it. The
   index is only the backstop for the concurrent race.
5. **A classifier outage parks the reply and touches nothing.** No guessing.
   A lead who answered gets a slow human response rather than another
   automated email.

**The inbox UI — built, in the existing dashboard.**

`/ai-sdr/inbox`, in the sidebar between Outreach and Audits. Page
`pages/sdr/SDRInbox.jsx`, drawer `components/sdr/InboundDrawer.jsx`, labels in
`lib/sdrConfig.js`. API: `GET /sdr/inbox`, `/sdr/inbox/summary`,
`/sdr/inbox/{id}`, `POST /sdr/inbox/{id}/reclassify`, `/reviewed`.

Three things it does deliberately:

- **Defaults to "Needs you", not "All".** The inbox is a work queue, not an
  archive. Low-confidence classifications and sender-matched replies surface
  first; unroutable replies get their own banner rather than a row that
  scrolls past.
- **A machine reply says so in words**, not just a grey pill: *"A machine sent
  this — nobody read your email."* A pill can be misread at a glance; that
  sentence is the same protection as the header check, at the UI layer.
- **Reclassify re-applies for real.** Correcting `interested` →
  `out_of_office` restarts the stopped sequence (`_resume_enrollment`). It
  refuses to resurrect anything stopped by a bounce or an unsubscribe — a
  suppression outranks a human's opinion about one email.

Also fixed on the way past: `.claude/launch.json`'s frontend config used
`npm --prefix "<path with spaces>"`, which fails on Windows. Now uses `cwd`.

**Still outstanding — both are yours, not code:**

- **The Cloudflare setup** — see the runbook. Ordering trap: enabling Email
  Routing changes MX, so do it *before* the domain warm-up starts, not during.
- `SDR_INBOUND_WEBHOOK_SECRET` in Vercel. Until it is set the endpoint returns
  503 and no reply is trusted. Redeploy after setting it — Vercel only picks up
  env changes on a fresh deploy.

Tests: `tests/sdr/test_inbound.py` (30). The UI was verified
against a local backend with seeded replies: rendering, filters, drawer, and a
reclassify round-trip persisting as `category_source: "human"`.

### 10.2 Phase 7 — Meetings — **done**

**The agent offers; it does not book.** This is a deliberate departure from
the original plan ("creates the event"), and the reason matters.

An agent that parses "Thursday works" and writes to the calendar has two
failure modes with real cost: misreading a date, and racing another booking
into the same slot while the email sits unread. The app already had a public
booking page that cannot do either — it re-validates against live availability
and returns 409 if the slot went. So the agent computes concrete times and
puts them next to a booking link; the existing page does the writing.

| Piece | Where |
|---|---|
| Slot intersection, spread, formatting, no-show test (pure) | `sdr/domain/meetings.py` |
| Proposal, signed refs, attach, no-show sweep | `sdr/services/meetings.py` |
| `meeting_proposal` agent | `sdr/agents/meetings/` |
| Booking accepts `ref`, attaches to the lead | `routers/bookings.py` |
| `?ref=` forwarded from the booking page | `frontend/src/pages/BookMeeting.jsx` |
| No-show sweep on the tick | `sdr/services/campaigns.py` |

API: `GET /sdr/leads/{id}/meeting-slots`, `POST /sdr/leads/{id}/propose-meeting`,
`POST /sdr/meetings/sweep-no-shows`.

**Decisions worth keeping:**

1. **The proposal agent has no LLM.** Every other outreach message uses one, so
   the exception needs justifying: this message is almost entirely specific
   times and a URL — the two things a model is worst at. A hallucinated time is
   a missed meeting; a hallucinated link is a dead end with no error. The copy
   reads plainer. That is the right trade here.
2. **A slot must sit inside *both* working days.** Agency availability is
   agency-local (`booking_settings`); the lead's day comes from their company's
   country profile. Offering 8am your time because it is 3pm theirs is invisible
   until nobody shows up. Both ends of the call are checked, so a 30-minute slot
   at 18:45 against a 19:00 close is not offered.
3. **Booking stops the sequence.** Same reasoning as a reply — a lead who books
   and then gets the next automated follow-up has been told nobody noticed.
4. **A stale link cannot resurrect a closed lead.** `won` is terminal; the
   meeting still attaches for the record, the pipeline is left alone.
5. **The no-show sweep never overrules a human.** It only touches leads still
   sitting in `meeting_scheduled`; if someone already moved them to `discovery`,
   the meeting is resolved but the lead is not touched.

**Not wired, and deliberately:** no Google Calendar event is created by the
agent. `users.google_tokens` is strictly per-user and an autonomous agent has
no user, so this would need an explicit "calendar owner" setting. The booking
page already creates the meeting record and sends confirmation; adding a
Google event means picking whose calendar it lands on. Small, but it is a
product decision, not a coding one.

Tests: `tests/sdr/test_meetings.py` (19).

### 10.3 WhatsApp — start the approval clock early

`config/countries.py` already declares WhatsApp ahead of email for India, and
the sequencing engine does not assume email-first. But **Meta Business
verification plus per-template approval takes weeks**, exactly like DNS
warm-up.

If WhatsApp is wanted this year, start the Meta approval process now, in
parallel with everything else. The code work (a `whatsapp` channel provider,
a template registry with approval status, DLT registration for SMS) is
straightforward once approval exists — and pointless before it.

### 10.4 Smaller, genuinely useful

- **A/B testing** (rest of Phase 5) — variants at subject/body level,
  deterministic assignment by `hash(lead_id + experiment_id)` so assignment is
  stable. Only worth it once volume makes results significant; at 30
  leads/day that is months away. **Do not build this yet.**
- **Analytics rollups** (Phase 9) — the Overview page currently aggregates
  live. Fine at current volume, needs materialising well before 1M leads.
- **Competitor analysis** (deferred from Phase 4) — needs a search provider;
  revisit if one is configured.
- ~~**Stale-queue alert**~~ — **done.** `jobs.stats()` now returns
  `queue_stalled` / `queue_lag_minutes` (`queue_health()`, threshold 60 min),
  and the Agents page shows a banner. This was the one silent failure in the
  system: if the pinger dies there is no error and no failed job, just a
  pipeline that quietly stops.

### 10.5 Sequencing, honestly

| Order | Item | Blocked by | State |
|---|---|---|---|
| 1 | Threading headers (§10.0) | nothing | **done** |
| 2 | Phase 6 inbound + Inbox UI | ingestion route chosen (Cloudflare) | **done** |
| 3 | Phase 7 meetings | Phase 6 | **done** |
| 4 | Stale-queue alert | nothing | **done** |
| 5 | Rotate Atlas password, add keys, pinger | **you** | outstanding |
| 6 | Sending domain DNS → warm-up starts | **you** | outstanding |
| 7 | Cloudflare Email Routing + `SDR_INBOUND_WEBHOOK_SECRET` | **you** | outstanding |
| 8 | WhatsApp code | Meta approval (weeks) | not started |
| 9 | A/B testing | volume | **deliberately not built** |

**Everything remaining that is code is blocked on something that is not.**
Items 5–7 are yours and gate the entire pipeline going live; item 8 cannot
start until Meta approves, which takes weeks and should be kicked off now if
WhatsApp is wanted this year.

A/B testing stays unbuilt on purpose: at 30 leads/day, splitting traffic means
waiting months for a result that a single bad week would swamp. Building it now
would produce a feature that mostly generates false confidence.

---

Full history: `docs/ai-sdr/CHANGELOG.md`. Decisions: `docs/ai-sdr/adr/`.

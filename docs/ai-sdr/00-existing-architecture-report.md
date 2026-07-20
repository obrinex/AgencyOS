# Existing Architecture Report

**Repo:** `agency dashboard/AgencyOS` · **Date:** 2026-07-20 · **Phase:** 0 (forensics, no feature code written)

> **Read this first.** The AI SDR specification was written against an assumed stack — Next.js App Router, TypeScript, Postgres + Prisma/Drizzle with RLS, pgvector, a durable job queue. **None of that is what this repo is.** This report establishes what actually exists, and §12–§13 reconcile the spec against it. Per the spec's own rule 4: *the existing codebase wins on conventions, the spec wins on functionality.*

---

## 1. Stack Inventory

| Layer | Technology | Version | File evidence |
|---|---|---|---|
| Backend framework | FastAPI (Python) | — | `backend/server.py:39` |
| Async DB driver | Motor / PyMongo | 3.3.1 / 4.6.3 | `backend/database.py:7-9` |
| Database | **MongoDB Atlas** (document store) | — | `MONGO_URL`, `backend/database.py` |
| Validation | Pydantic v2 (request DTOs only) | 2.13.4 | inline per router, e.g. `backend/routers/crm.py:19-77` |
| Auth | Custom JWT (HS256, PyJWT) + bcrypt + TOTP 2FA | — | `backend/auth_utils.py` |
| Frontend framework | **React 19 + CRA via CRACO** (not Next.js) | 19.0.0 / 7.1.0 | `frontend/package.json:64-68` |
| Language | **JavaScript / JSX only — TypeScript forbidden** | — | `design_guidelines.json` `instructions_to_main_agent`; `components.json` `"tsx": false` |
| Router | react-router-dom | 7.15.0 | `frontend/src/App.js` |
| UI kit | shadcn/ui (new-york) on Radix, 48 primitives | — | `frontend/components.json`, `src/components/ui/*.jsx` |
| Styling | Tailwind 3.4.17, CSS variables, **dark-only** | — | `frontend/tailwind.config.js`, `src/index.css:32-69` |
| Icons / charts / toasts | lucide-react / recharts 3.6.0 / sonner 2.0.3 | — | — |
| HTTP client | axios 1.16.0 + interceptors | — | `frontend/src/lib/api.js` |
| LLM | NVIDIA NIM via `openai` SDK (`AsyncOpenAI`) | 1.99.9 | `backend/routers/ai.py:15-24` |
| Model | `meta/llama-3.3-70b-instruct` (default) | — | `NVIDIA_MODEL` |
| Email | Resend | — | `backend/routers/emails.py` |
| Payments | Cashfree (INR) + crypto (USD) | — | `backend/routers/public.py`, `payment_links.py` |
| Hosting | Vercel serverless (both apps) | — | `backend/vercel.json`, `frontend/vercel.json` |
| Migrations | **None** | — | no migration tooling anywhere |
| Tests | **None** in `frontend/src`; `tests/` at root is E2E-ish | — | — |
| Job queue | **None** | — | see §9 |

**Dead dependencies** (installed, zero imports — do not assume they're available patterns): backend `litellm`, `google-generativeai`, `google-genai`, `stripe`, `boto3`; frontend `@tanstack/react-query` (provider mounted, `useQuery` count = 0), `swr`, `react-hook-form` + `zod`, `ui/toast.jsx` + `ui/toaster.jsx` + `hooks/use-toast.js` (superseded by sonner), `ui/table.jsx` (imported by zero pages).

---

## 2. Directory Map (annotated)

```
AgencyOS/
├── backend/
│   ├── server.py              app factory, env validation, 25 router registrations, CORS, security headers
│   ├── database.py            Motor singleton `db`, serialize helpers, create_indexes()
│   ├── auth_utils.py          ★ JWT, get_current_user, require_roles/require_module, log_audit
│   ├── seed.py                seed_admin(), seed_company_settings()
│   ├── reminders.py           in-process asyncio loops (disabled in prod)
│   ├── automation_engine.py   run_won_automation — inline, synchronous
│   ├── email_service.py       Resend wrapper
│   ├── fx.py                  live USD→INR with fallback
│   ├── api/index.py           Vercel serverless entrypoint (sys.path shim → `from server import app`)
│   ├── vercel.json            routes /(.*) → api/index.py, maxDuration 60, crons
│   └── routers/               25 files, each declaring its OWN full /api/... prefix
│       ├── crm.py             ★ leads, lead_activities, contacts — the SDR core already exists
│       ├── leadfinder.py      ★ OSM/Overpass business discovery + LLM pitch + import-to-lead
│       ├── ai.py              ★ NVIDIA NIM client, streaming chat, generate-email/proposal/draft-reply
│       ├── emails.py          Resend send + sent_emails log (SEND-ONLY, no inbound)
│       ├── automations.py     ★ cron endpoints guarded by CRON_SECRET
│       └── … (see §3)
├── frontend/
│   ├── craco.config.js        webpack alias @/ → src/, inline ESLint config
│   ├── src/
│   │   ├── App.js             ★ full route table (public / staff-under-AppLayout / portal)
│   │   ├── lib/api.js         ★ axios instance, token injection, 401-refresh-replay, GET fallback
│   │   ├── contexts/AuthContext.jsx   sessionStorage + httpOnly refresh cookie
│   │   ├── components/layout/Sidebar.jsx   ★ NAV_SECTIONS (L11-63) — the one nav registry
│   │   ├── components/ui/     48 shadcn primitives (.jsx)
│   │   ├── components/        PageHeader, EmptyState, StatusBadge, CommandPalette, AIAssistant
│   │   ├── lib/statusConfig.js  STAGE_CONFIG et al — status pill definitions
│   │   └── pages/             45 pages incl. LeadFinder.jsx, Emails.jsx, PaymentLinks.jsx
│   └── api/proxy.js           Vercel rewrite → backend-five-hazel-13.vercel.app
├── docs/ai-sdr/               ← this module's docs (new)
└── design_guidelines.json     ★ binding visual + language constraints
```

---

## 3. Routing Model

**Backend.** No shared prefix injection. Each router file declares its own `APIRouter(prefix="/api/...")` and is registered flat in `server.py:53-78` with `app.include_router(x.router)`. A stub `/api/` health root exists at `server.py:45-53`.

**Frontend.** `react-router-dom` v7, single `<BrowserRouter>`. Three zones in `src/App.js`:
- **Public** (L61-68): `/login`, `/proposal/:token`, `/book/:slug`, `/pay/:token`, `/status/:token`, `/start/:slug`, `/agreement/:token`.
- **Staff** (L70-107): pathless route → `<ProtectedRoute roles={["admin","team_member"]}><AppLayout /></ProtectedRoute>`, children as absolute paths.
- **Client portal** (L109-126): `path="/portal"`, `roles={["client"]}`, `<PortalLayout />`, relative children.

**Where a new authenticated module goes:** a `<Route path="/ai-sdr/*" …>` (or discrete sibling routes) inside the **L70-107 block**, with the page component in `frontend/src/pages/`. That block is already inside `AppLayout`, so the sidebar/topbar/⌘K chrome comes free — no new layout of any kind.

---

## 4. Authentication & Authorization

**Provider:** custom, stateless JWT. No Supabase/NextAuth/Clerk.

- Access token: HS256, claims `sub`/`email`/`role`/`exp`/`type:"access"`, TTL `ACCESS_EXPIRE_MIN` (default 1440 min). Refresh token 7 days.
- Delivery: httpOnly cookies `access_token`/`refresh_token`, **with `Authorization: Bearer` accepted as fallback** (`auth_utils.py:67-69`) — which is what the frontend actually uses.
- 2FA: TOTP (`pyotp`, `valid_window=1`). Login returns `{requires_2fa, temp_token}`; `POST /api/auth/2fa/login` exchanges it. **Production admin has 2FA enabled** — the deployed API cannot be scripted into.
- Brute force: `login_attempts` collection, 5 failures → 15-min lock.

**Session helper signature — reuse verbatim:**
```python
async def get_current_user(request: Request) -> dict    # auth_utils.py:64
```
Returns a plain `dict` (not a model) with `id` as a **string** ObjectId; `password_hash` and `two_fa_secret` are stripped. It hits Mongo on **every request** — no cache.

**How to guard a route handler** (the only pattern in this codebase — guard is always the last parameter, always named `user: dict`):
```python
@router.get("/leads")
async def list_leads(..., user: dict = Depends(require_staff)):
```

**Role model** (`auth_utils.py:93-104`) — three global roles, no hierarchy:
```python
require_admin  = require_roles("admin")
require_staff  = require_roles("admin", "team_member")
require_client = require_roles("client")
```

**Module permissions** — the exact function to reuse (`auth_utils.py:108-126`):
```python
PERMISSION_MODULES = ["crm","emails","documents","clients","projects","support",
                      "calendar","finance","knowledge","vault","files","notes","analytics"]
require_module(module)   # admin always passes; team_member needs module in user["permissions"]
                         # NOTE: empty/missing permissions == full access (backward-compat)
```
Used by `finance.py:14`, `emails.py:10`, `vault.py:10`, `payment_links.py:14`.

**Frontend guard:** `src/components/ProtectedRoute.jsx` — `{ children, roles }`. Sidebar visibility filter (`Sidebar.jsx:69-74`, duplicated in `MobileNav` L146-151):
```js
const perms = user?.role === "team_member" ? (user?.permissions || []) : [];
const canSee = (item) => !item.module || perms.length === 0 || perms.includes(item.module);
```

> **Spec §11 reconciliation:** the spec's seven granular permissions (`sdr:read`, `sdr:leads:write`, `sdr:send`, …) have no home here — this system has one flat string per module, not verb-scoped scopes. Recommendation in §13.

---

## 5. Database

- **Client:** Motor `AsyncIOMotorClient`, module-level singleton, imported as `from database import db`. **No per-request session, no dependency injection, no transactions.**
- **Migration command:** *there is none.* No Alembic, no migration directory, no schema-version collection. Schema evolves implicitly — new fields appear on new documents and readers use `.get()` with defaults. Ad-hoc scripts fill the gap (`backfill_fx_rates.py`, `clear_operational_data.py`, `restore_settings.py`, `seed.py`).
- **Naming convention:** `snake_case` for collections, fields, and enum values. `_id` is a real `ObjectId`; every cross-reference field (`client_id`, `lead_id`, `owner_id`) stores a **string**, converted at the boundary via `to_object_id()` / `str()`.
- **Timestamps:** ISO-8601 **strings**, never BSON dates. Date comparisons are therefore lexicographic — correct for UTC ISO, but fragile.
- **Tenancy column name: none exists.** See below.
- **Indexes:** the only schema-ish declaration, `database.py:39-55`. Relevant: `leads` text index on `(company, email)`, `leads.stage`, `invoices.invoice_number` unique, `audit_logs.created_at`, TTL indexes on `password_reset_tokens.expires_at` and `google_oauth_states.expires_at`.
- **Pagination: does not exist anywhere.** Every list endpoint is `.to_list(1000)`.
- **RLS posture:** N/A — MongoDB, and the app does not implement row-level scoping of any kind.

### Existing collections relevant to SDR (reuse these, do not fork)

| Collection | Shape (abridged) | Verdict |
|---|---|---|
| `leads` | `company*, website, industry, employees, revenue, location, owner_id, source, priority, email, phone, linkedin, notes, tags[], stage, custom_fields{}, score, converted_client_id, ai_draft_reply, created_at, updated_at` | **Extend.** Additive columns + `source` discriminator. Already has `stage`, `score`, `custom_fields`, `tags`. |
| `lead_activities` | `lead_id, type, content, created_by, created_at` | **Extend.** The existing timeline. Lead-scoped only. |
| `contacts` | `name*, lead_id, client_id, company, position, email, phone, linkedin, timezone, birthday, notes` | **Extend.** No consent/DNC/verification fields yet. |
| `clients`, `projects`, `tasks`, `invoices`, `proposals`, `contracts` | see backend report | **Reuse as-is** — the won→client→project→invoice chain already works via `automation_engine.run_won_automation`. |
| `tasks` | has polymorphic `related_type` / `related_id` | **Reuse directly** for agent-generated human tasks (spec §10 "Tasks" page). |
| `files` | GridFS, same polymorphic pair | **Reuse** for screenshots / proposal PDFs. |
| `sent_emails` | `to, recipient_name, subject, body, sent_by, sent_by_name, provider_id, created_at` | **Send-only.** No thread, no direction, no status lifecycle, no inbound. Needs extension or a sibling collection. |
| `notifications`, `audit_logs`, `automation_logs`, `system_state` | — | **Reuse.** `system_state` is the existing idempotency mechanism. |

**Existing lead stages** (`crm.py:15-16`) — note these differ from the spec's:
`prospect, contacted, qualified, discovery, meeting_scheduled, proposal_sent, negotiation, won, lost, rejected, cold`

Spec proposes: `new, qualified, contacted, interested, meeting_scheduled, proposal_sent, negotiation, won, lost, archived`. Overlap is high; `prospect`≈`new`, and the repo adds `discovery`/`rejected`/`cold` while the spec adds `interested`/`archived`. **Recommendation: keep the existing eleven, add `interested` and `archived`.** Renaming `prospect`→`new` would break `CRMPipeline.jsx`, `STAGE_CONFIG`, and every stored lead.

---

## 6. Reusable UI Inventory

Full shadcn set (48 primitives) at `@/components/ui/*.jsx`. The ones a module actually needs:

| Component | Import path | Props summary | Where used |
|---|---|---|---|
| `PageHeader` | `@/components/PageHeader` | `{ title, description, actions, testId }` | 28 pages |
| `EmptyState` | `@/components/EmptyState` | `{ icon, title, description, action, testId }` | 22 pages |
| `StatusBadge` | `@/components/StatusBadge` | `{ config, value, testId }` — pairs with `lib/statusConfig.js` | Invoices, CRM, Tasks |
| `Card` | `@/components/ui/card` | `Card, CardHeader, CardTitle, CardContent, CardFooter` | everywhere |
| `Button` | `@/components/ui/button` | `Button, buttonVariants` (`size`, `variant`) | everywhere |
| `Dialog` | `@/components/ui/dialog` | `Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter` | house modal idiom |
| `Select` | `@/components/ui/select` | `Select, SelectTrigger, SelectValue, SelectContent, SelectItem` | forms |
| `Input`, `Label`, `Textarea`, `Checkbox`, `Switch`, `Tabs`, `Badge`, `Skeleton`, `ScrollArea`, `Popover`, `Tooltip`, `DropdownMenu`, `Sheet`, `Drawer`, `Progress`, `Separator` | `@/components/ui/*` | stock shadcn | — |
| `DatePicker` | `@/components/DatePicker` | Popover + react-day-picker | Tasks, Invoices |
| `formatMoney` | `@/lib/currency` | `(amount, code)`; `SUPPORTED_CURRENCIES = ["INR","USD"]` | Finance |
| `useFxRate` | `@/hooks/useFxRate` | `(currency, {enabled}) → {rate, asOf, source, stale, …}` | Invoices |
| `cn` | `@/lib/utils` | `twMerge(clsx(...))` | everywhere |

**Two traps:**
1. **`ui/table.jsx` exists but zero pages import it.** There are no HTML tables in this app. Every list is a stack of bordered rows or cards. A `<Table>` would look foreign. The spec's "virtualised/paginated DataTable" must be built as the house row-stack idiom.
2. **`ui/toast.jsx` / `ui/toaster.jsx` / `hooks/use-toast.js` are dead.** Use `import { toast } from "sonner"`.

**Charts:** recharts, `ResponsiveContainer height={240}`, no `CartesianGrid`, `axisLine={false} tickLine={false}`, graphite `#85858C` ticks, hardcoded hexes:
```js
const PIE_COLORS = ["#3B82F6","#10B981","#F59E0B","#EF4444","#85858C","#B5B5BC"];
const tooltipStyle = { background:"#18181A", border:"1px solid rgba(255,255,255,0.1)", borderRadius:8, fontSize:12 };
```

---

## 7. Design Tokens

`--radius: 0.75rem`. HSL triplets in `src/index.css:32-69`:

| Token | Value | Hex |
|---|---|---|
| `background` | `240 5% 8%` | `#131315` |
| `foreground` | `240 5% 96%` | `#F4F4F5` |
| `surface-1` / `-2` / `-3` | `240 4% 10%` / `240 4% 14%` / `240 3% 18%` | `#18181A` / `#222225` / `#2D2D30` |
| `carbon` / `graphite` / `ash` | `240 3% 30%` / `54%` / `240 5% 72%` | `#4A4A4E` / `#85858C` / `#B5B5BC` |
| `success` / `warning` / `danger` / `info` | — | `#10B981` / `#F59E0B` / `#EF4444` / `#3B82F6` |
| `border` | `240 3% 30% / 0.3` | hairline `border-white/10` |

**Fonts:** `Archivo` (display + sans), `Space Mono` (mono — all numerics and metadata).

**Dark mode strategy: there isn't one — the app is dark-only.** The dark palette lives in `:root`; the `.dark` block merely repeats two vars; `html { color-scheme: dark }`; no `ThemeProvider` is mounted. **Do not add a light variant or `prefers-color-scheme` handling.**

**Binding rules from `design_guidelines.json`:** Swiss/high-contrast archetype. 8px spacing scale, `p-6` page containers, `gap-4` clusters, `rounded-xl` panels, `rounded-md` inputs, **1px hairlines and no shadows**, sticky blurred `z-50` headers, no hamburger on `md+`. Typography: `label: text-xs font-mono uppercase tracking-[0.2em]`, `meta: text-sm font-mono text-[#85858C]`. **JS/JSX only, never TypeScript. Every interactive element needs a kebab-case `data-testid`.**

---

## 8. Data-fetching & Validation Conventions

**Backend — canonical read + write** (`crm.py:80-102`, copy this shape exactly):
```python
@router.get("/leads")
async def list_leads(stage: Optional[str] = None, owner_id: Optional[str] = None,
                     search: Optional[str] = None, user: dict = Depends(require_staff)):
    query = {}
    if stage: query["stage"] = stage
    if owner_id: query["owner_id"] = owner_id
    if search: query["company"] = {"$regex": search, "$options": "i"}
    leads = await db.leads.find(query).sort("updated_at", -1).to_list(1000)
    return serialize_list(leads)

@router.post("/leads")
async def create_lead(payload: LeadCreate, user: dict = Depends(require_staff)):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({"score": 0, "owner_id": doc.get("owner_id") or user["id"],
                "created_at": now, "updated_at": now, "converted_client_id": None})
    res = await db.leads.insert_one(doc)
    await db.lead_activities.insert_one({"lead_id": str(res.inserted_id), "type": "note",
        "content": "Lead created", "created_by": user["id"], "created_at": now})
    await log_audit(user["id"], "create_lead", "lead", str(res.inserted_id))
    lead = await db.leads.find_one({"_id": res.inserted_id})
    return serialize_doc(lead)
```
House rules visible here, none of them enforced by tooling: Pydantic model defined inline at the top of the router file; **no `response_model` anywhere**; `model_dump()` then `doc.update({...server fields...})` — so the **stored document is a superset of the Pydantic model** and is only discoverable by reading the insert; re-read after insert rather than echoing the payload; `log_audit` called manually on writes that matter.

**Frontend — canonical fetch.** No react-query, no SWR, despite both being installed. Universal pattern is `useState(null)` + `useEffect` + `api.get`, with `null` doubling as the loading flag and a manual `load()` re-invoked after every mutation:
```js
const [things, setThings] = useState(null);
const load = async () => { const { data } = await api.get("/things"); setThings(data); };
useEffect(() => { load(); }, []);
if (!things) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;
```
Mutations: `try { await api.post(...); toast.success(...); load(); } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }`.

**Copy-me page template:** `frontend/src/pages/PaymentLinks.jsx` (153 lines) — header + action, warning banner, empty state, row list with badges, create dialog, destructive-confirm dialog. Row-style list: `Invoices.jsx:93-104`. Card grid: `Clients.jsx:70-109`.

**API client gotcha** (`lib/api.js:88-120`): the response interceptor makes failing **GET** requests resolve with a synthetic `200` whose body comes from `fallbackForGet(url)` — default `[]`. So a broken new GET endpoint silently renders your empty state instead of throwing. **If a new GET returns an object rather than a list, add a branch to `fallbackForGet` (L43-53)** or the page will crash on `.someProperty` of `[]`.

**Validation library:** Pydantic v2 backend-side. Frontend has `zod` installed but unused; forms are plain controlled `useState`.

---

## 9. Background Jobs / Scheduling

**What exists today:**

1. **In-process asyncio loops** — `reminders.py`, started at `server.py:116-120` **only if `RUN_BACKGROUND_LOOPS=true`** (default false, and must stay false on Vercel).
2. **Stateless authenticated cron endpoints** — `routers/automations.py`, the production path. Guarded by `require_cron_secret`, which accepts either `x-cron-secret:` or `Authorization: Bearer` (Vercel Cron uses the latter). Registered for **both GET and POST** because Vercel issues GETs.
3. **Idempotency:** `_already_ran_today(job, today)` / `_mark_ran` via the `system_state` collection (`reminders.py:116-123`). This is the *only* double-execution guard in the codebase.
4. **Inline synchronous work:** `automation_engine.run_won_automation` fires within the request on `PATCH /api/leads/{id}/stage → won`.

**Schedule** (`backend/vercel.json`):
```json
"crons": [
  { "path": "/api/automations/cron/daily",     "schedule": "30 2 * * *" },
  { "path": "/api/automations/cron/reminders", "schedule": "0 14 * * *" }
]
```

**There is no queue, no worker pool, no retry/backoff, no dead-letter, no Celery/RQ/APScheduler/Inngest/Trigger.dev/QStash.**

### ⚠️ This is the single hardest constraint on the whole spec

The spec assumes 15 named queues, exponential backoff with jitter, per-provider circuit breakers, dead-letter replay, and warm-up schedulers that ramp daily caps. On the current platform:

- **Vercel Hobby permits only daily crons** — an hourly schedule was already rejected on deploy (documented in the session handoff). So the finest scheduling granularity available today is **once per day**.
- **60-second hard request ceiling** (`maxDuration: 60`). `leadfinder.py:149-151` already tunes its `httpx` timeouts around this. Nothing that takes longer can run inside a request.
- **No in-process shared state survives an invocation** — no memory caches, no rate-limit counters, no queues. `login_attempts` and `fx_rates` are collections precisely because of this.

**Recommended mechanism, with justification:** a **MongoDB-backed job collection drained by the existing cron endpoints**, not a new queue product.

- A `sdr_jobs` collection with `{status, run_after, attempts, max_attempts, idempotency_key (unique index), locked_until, payload}`. Claim via atomic `find_one_and_update({status:"queued", run_after:{$lte:now}, …}, {$set:{status:"running", locked_until:…}})` — this gives real at-most-once claiming without any new infrastructure, and it's the same trick `next_counter` already uses.
- Drained by a new `/api/automations/cron/sdr` handler that loops until the 60s budget is nearly spent, then returns. Idempotency keys make redelivery safe.
- **This does not make the SDR "24/7 autonomous" on the current plan.** Once-daily draining means outreach sends in one batch per day and inbound replies wait up to 24h for agent processing. See §13 blocking question 1 — this is a **plan/hosting decision, not a code decision**, and it gates the spec's core promise.

---

## 10. Env Vars & Secrets

**Loading:** `server.py:4-5` does `load_dotenv(ROOT_DIR / ".env")` **before any other import**, so `database.py`'s module-level `os.environ["MONGO_URL"]` works. Everything else reads `os.environ` directly at import time. **No `pydantic-settings`, no typed config object.** Two access styles coexist: `os.environ["X"]` (hard fail) and `os.environ.get("X", default)` (soft).

**Validation:** only `validate_environment()` (`server.py:24-38`). Required: `MONGO_URL, DB_NAME, JWT_SECRET, VAULT_ENCRYPTION_KEY`. In production also enforces JWT_SECRET ≥32 chars and not in a weak-value blocklist, VAULT_ENCRYPTION_KEY ≥32, and `CRON_SECRET` present. Runs before `FastAPI()` is constructed, so a misconfigured deploy fails fast. **Extend this function, don't add a parallel one.**

Existing keys: `APP_ENV`, `FRONTEND_URL`, `CORS_ORIGINS`, `ALLOWED_HOSTS`, `MONGO_URL`, `DB_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `JWT_SECRET`, `ACCESS_EXPIRE_MIN`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, `VAULT_ENCRYPTION_KEY`, `CRON_SECRET`, `RUN_BACKGROUND_LOOPS`, `RESEND_API_KEY`, `SENDER_EMAIL`, `CASHFREE_*`, `BACKEND_URL`, `FX_FALLBACK_USD_INR`, `GOOGLE_CLIENT_ID/_SECRET/_REDIRECT_URI`, `NVIDIA_API_KEY/_MODEL/_BASE_URL`, `OVERPASS_URLS`, `REACT_APP_BACKEND_URL`.
Undocumented in `.env.example` but live: `ACCESS_EXPIRE_MIN`, `NVIDIA_BASE_URL`, `OVERPASS_URLS`.

**Secret storage precedent exists:** `vault.py` uses Fernet envelope encryption keyed by `VAULT_ENCRYPTION_KEY`, with a `POST /{id}/reveal` endpoint and masked reads. The spec's `provider_accounts.credentials_encrypted` should reuse this exact mechanism rather than inventing one.

**Operational note:** Vercel returns `[SENSITIVE]` for env values, so `MONGO_URL` is unreadable from the CLI; production DB work needs the string from the git-ignored `backend/.env.purge`.

---

## 11. Deployment & CI

**Two targets are configured simultaneously** — Vercel serverless (`backend/vercel.json` + `backend/api/index.py`, the live one) and Render long-running (`render.yaml`, `uvicorn server:app`, free plan). They disagree on the LLM model (`llama-3.3` vs `llama-3.1`).

- Frontend: `obrinexcrm.vercel.app`; `vercel.json` rewrites `/api/*` → `api/proxy.js` → `backend-five-hazel-13.vercel.app`.
- **There is no CI.** No `.github/workflows`, no typecheck/lint/test gate, no security scanning, no preview-environment seeding.
- **Backend deploys from the working tree via CLI, not from git** — which is why 51 uncommitted files are currently in production but not in the repo (see §13).
- No `Dockerfile`, no `docker-compose`.
- No feature-flag mechanism exists.

**Local dev gotcha:** `frontend/package.json` proxies to port **8000**, while `.env.development` sets `REACT_APP_BACKEND_URL=http://localhost:8001`. Wrong port → "could not reach the server". `.claude/launch.json` is configured: `agencyos-backend` :8000, `agencyos-frontend` :3000.

---

## 12. INTEGRATION PLAN

### Confirmed reuse decisions

| Concern | Decision |
|---|---|
| **Auth** | `get_current_user` / `require_staff` / `require_admin` + a new `"ai_sdr"` entry in `PERMISSION_MODULES` (`auth_utils.py:108`). No new auth anything. |
| **Tenancy** | **None** — matching the app. Every new collection gets `owner_id` for assignment, not tenancy. See §13 Q2. |
| **Tables** | Extend `leads`, `lead_activities`, `contacts`. New collections only for genuinely new concepts (`sdr_*` prefix). Never a parallel `sdr_leads`. |
| **UI** | `AppLayout` + `NAV_SECTIONS` + `PageHeader`/`EmptyState`/`StatusBadge`/`Card`/`Dialog`. Row-stack lists, never `<Table>`. Dark-only, JSX-only, `data-testid` on everything. |
| **Jobs** | Mongo-backed `sdr_jobs` claimed atomically, drained by a new cron endpoint. No new queue product. |
| **LLM** | `routers.ai._get_client()` + `NVIDIA_MODEL` via lazy in-function import (the `leadfinder.py:242` / `emails.py:32` pattern, which avoids circular imports). |
| **Secrets** | Fernet envelope encryption per `vault.py`, keyed by `VAULT_ENCRYPTION_KEY`. |
| **Email send** | `email_service.py` (Resend). |
| **Idempotency** | `system_state` collection pattern + unique index on `idempotency_key`. |
| **Discovery** | **Extend `routers/leadfinder.py`** — it already does OSM/Overpass discovery, LLM pitch generation, and import-to-lead. This becomes the first `DataProvider` adapter, not a competitor to one. |

### Files to CREATE (Phase 1 scope only — later phases will extend this list)

```
backend/sdr/__init__.py
backend/sdr/models.py             Pydantic DTOs for all SDR entities
backend/sdr/collections.py        collection name constants + create_sdr_indexes()
backend/sdr/errors.py             typed error hierarchy with retryable flag
backend/sdr/domain/pipeline.py    lead stage state machine (pure, no I/O)
backend/sdr/domain/scoring.py     deterministic scoring + explainability (pure)
backend/sdr/domain/signals.py     declarative opportunity-signal registry
backend/sdr/domain/roi.py         ROI formulas with stated assumptions (pure)
backend/sdr/config/countries.py   country registry — currency/locale/tz/holidays/compliance
backend/sdr/repositories/*.py     the only place touching db.* for SDR collections
backend/routers/sdr.py            APIRouter(prefix="/api/sdr")
frontend/src/pages/sdr/Overview.jsx
frontend/src/lib/sdrStatusConfig.js
docs/ai-sdr/*.md, docs/ai-sdr/adr/*.md
tests/sdr/…                       first tests in the repo (see §13 Q4)
```

### Files to MODIFY (exact list, one line each)

| File | Reason |
|---|---|
| `backend/server.py` | one import + one `app.include_router(sdr.router)` line in the L53-78 block |
| `backend/auth_utils.py` | add `"ai_sdr"` to `PERMISSION_MODULES` (L108) |
| `backend/database.py` | call `create_sdr_indexes()` from `create_indexes()` |
| `backend/routers/automations.py` | add `/cron/sdr` handler (GET+POST, cron-secret guarded) |
| `backend/vercel.json` | add the `/api/automations/cron/sdr` cron entry |
| `backend/.env.example` (root `.env.example`) | document new SDR keys |
| `frontend/src/App.js` | import + route entries inside the staff block (L70-107) |
| `frontend/src/components/layout/Sidebar.jsx` | lucide import + `NAV_SECTIONS` entries under a new "AI SDR" section |
| `frontend/src/components/CommandPalette.jsx` | optional `QUICK_ACTIONS` entry |
| `frontend/src/lib/api.js` | `fallbackForGet` branches for SDR GETs returning objects |
| `README.md` | short AI SDR section linking to `docs/ai-sdr/` |

**Files to DELETE: zero.**

---

## 13. Risks, Conflicts & Open Questions

### Spec-vs-reality conflicts and how each is reconciled

| # | Spec requires | Reality | Reconciliation |
|---|---|---|---|
| 1 | Next.js App Router, server actions, RSC | CRA + react-router, plain SPA | Follow the repo. Pages are client components fetching via axios. No server actions exist to use. |
| 2 | Strict TypeScript, no implicit `any`, ESLint boundary rules | **TypeScript explicitly forbidden** by `design_guidelines.json` | JSX + Pydantic. Type safety lives at the backend boundary via Pydantic; frontend gets JSDoc where it earns its keep. Layer boundaries enforced by convention + review, not lint. |
| 3 | Postgres, migrations, RLS, pgvector | MongoDB, no migrations, no RLS | Collections + an idempotent `create_sdr_indexes()`. Vector search unavailable → KB retrieval uses Mongo text indexes. |
| 4 | `org_id` on every table, tenant-filtered queries, cross-tenant tests | **Zero tenancy in the entire app** | See Q2 — this is the largest open decision. |
| 5 | 15 durable queues, backoff+jitter, circuit breakers, dead-letter | No queue; daily-only crons; 60s ceiling | Mongo-backed `sdr_jobs` + cron drain. Real retries and dead-lettering are implementable; **sub-daily scheduling is not, on the current plan.** See Q1. |
| 6 | ≥80% coverage on domain/application, contract + E2E + perf + security suites | **Zero tests exist** | See Q4. |
| 7 | Money as `numeric(14,2)` | Mongo floats; `currency` + `conversion_rate` already convention | Store as Decimal128 for new SDR money fields, or match the existing float convention. Recommend matching existing to avoid a mixed regime — and note the `conversion_rate` bug precedent (defaulted to 1.0, counting $100 as ₹100). |
| 8 | `timestamptz` UTC | ISO-8601 **strings** | Follow the repo. Timezone-aware send windows must parse-then-compare, never rely on string ordering across zones. |
| 9 | Soft delete on leads/campaigns/companies | Hard deletes throughout (`DELETE /leads/{id}`) | Add `deleted_at` on new SDR collections only; leave existing endpoints alone. |
| 10 | Granular `sdr:*` permissions | One flat module string per user | Single `"ai_sdr"` module key + `require_admin` for destructive/settings actions. Verb-scoped permissions would require rebuilding the permission system app-wide. |
| 11 | Feature flag per org, per channel | No flag mechanism | Store flags in the existing `company_settings` singleton. |
| 12 | Open tracking off, `List-Unsubscribe`, warm-up, DNS verification | Resend send-only, no identity model, no bounce webhook | Buildable, but the spec's deliverability layer is genuinely the largest net-new subsystem here. |

### Additional risks

- **`sent_emails` is send-only.** There is no inbound email path at all — no webhook, no thread matching, no `Message-ID`/`In-Reply-To` handling. The spec's Phase 6 (conversation) is entirely greenfield and depends on inbound routing that Resend must be configured to deliver.
- **No pagination anywhere.** Every list is `.to_list(1000)`. The spec targets 1M leads/org. A lead table at that scale needs keyset pagination introduced — which means touching `crm.py`, and existing pages assume they receive a full array.
- **`get_current_user` hits Mongo per request** and there's no caching layer; agent-heavy traffic will multiply this.
- **51 uncommitted files are live in production** but absent from git. Any SDR work branches from a tree that doesn't match `main`. **This should be resolved before Phase 1 writes code** — otherwise a rollback restores a version production has never run.
- **Two credentials were exposed in chat** and are still unrotated (Atlas password, Cashfree live secret). Independent of this module, but it's live production risk.
- **Scraping/ToS:** the spec's §5 already forbids LinkedIn cookie scraping, and `leadfinder.py` correctly declares a `USER_AGENT` per OSM policy. Any new provider adapter must respect `robots.txt` and rate-limit per host; capabilities with no compliant path return `unsupported` rather than being faked.
- **Cost governance has no precedent.** `ai.py` constructs a client per call, tracks no tokens, and `build_crm_context()` naively stuffs 20 leads + 20 clients + 50 invoices into every system prompt. Per-org spend caps and token accounting are net-new.

---

### Blocking questions (5, each with a recommended default so work can proceed)

**Q1 — Scheduling granularity. This gates the product's core promise.**
"Autonomous 24/7" needs sub-daily execution; Vercel Hobby gives one cron per day. Options: (a) upgrade to Vercel Pro (~$20/mo) for minute-level crons; (b) add a free external pinger (cron-job.org / GitHub Actions schedule) hitting `/api/automations/cron/sdr` every 5 min with `CRON_SECRET`; (c) accept daily batches.
→ **Recommended default: (b)** — zero cost, no platform change, and the cron endpoint is already secret-guarded and idempotent. Build the job runner so the trigger source is irrelevant, so (a) remains a one-line switch later.

**Q2 — Multi-tenancy.** The spec calls it mandatory from line one; the app has none, and `TENANT_SECURITY.md` already documents tenancy as future work. Adding `org_id` to SDR collections only produces a half-tenanted system whose guarantees are illusory (a lead is tenant-scoped, the client it converts into is not).
→ **Recommended default: build single-tenant, matching the app**, but route every SDR read/write through the repository layer so a tenant filter can be injected in exactly one place later. Document as an ADR. Retrofitting tenancy app-wide is its own project.

**Q3 — Scope and sequencing.** The spec is 12 phases and realistically many months. Launch is **1 August 2026** — twelve days out — and Cashfree go-live is still blocked.
→ **Recommended default: Phases 0–4 only before launch** (foundation → lead data + discovery → agent runtime → research/scoring/qualification). That delivers a genuinely useful "find, research, score, qualify" system reusing the existing Lead Finder, with **no automated outbound sending**. Phase 5+ (outreach, deliverability, conversation) lands after launch, when warm-up alone needs weeks of domain reputation building before the first real send.

**Q4 — Testing.** The repo has zero tests and no CI; the spec demands ≥80% coverage plus contract/E2E/perf/security suites.
→ **Recommended default: pytest on `backend/sdr/domain/` only** (state machine, scoring, ROI, dedupe, timezone math — all pure, all trivially testable) plus a smoke test per new endpoint. Introducing a full test pyramid *and* CI to a repo that has neither is a separate initiative; I'll note it in an ADR rather than silently skipping it.

**Q5 — Uncommitted production state.** 51 files are live but uncommitted, including `routers/payment_links.py`, `routers/emails.py`, and their pages.
→ **Recommended default: commit them as-is before Phase 1**, in one clearly-labelled commit. They're already running in production; leaving them uncommitted means the repo cannot reproduce what's deployed.

---

## Gate

**Phase 0 complete. No feature code written.** Per the working protocol, I'll proceed to Phase 1 using the recommended defaults above unless corrected — with the exception of **Q1 and Q3**, which change what gets built and in what order, and are worth an explicit answer.

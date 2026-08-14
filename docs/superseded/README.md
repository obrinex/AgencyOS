# Superseded documents — do not use as a source of truth

Everything in this folder describes a **planned migration that was never
carried out**: moving AgencyOS from FastAPI/MongoDB/Vercel to Hostinger managed
Node.js with Supabase PostgreSQL, Supabase Auth, Supabase Storage and
Stripe/Razorpay payments.

None of it shipped. The files are kept only for historical context.

## Why they are archived rather than deleted

On 2026-07-22 these documents were read as current state and used to write a
specification for a new module. The result was a spec built entirely on
Postgres DDL, `pgvector`, Supabase Auth and Next.js route handlers — none of
which exist in this repository. Phase 0 forensics caught it before any code was
written, but the cost was a full spec cycle.

They are moved and banner-headed so the next person — or the next agent — reads
the warning before the content.

## What the system actually is

| | Reality |
|---|---|
| Backend | FastAPI 0.110, Python 3.11 |
| Database | MongoDB Atlas via Motor. No SQL, no migrations, no RLS |
| Frontend | React 19 on CRA + CRACO, `.jsx` only, no TypeScript |
| Auth | Custom JWT (HS256, httpOnly cookies) + bcrypt + TOTP; roles `admin` / `team_member` / `client` + per-module permissions |
| Hosting | **Vercel**, two projects (`backend`, `frontend`), 60s function ceiling |
| Payments | **Cashfree** (~15 direct call sites, no abstraction) |
| Scheduling | Vercel crons (daily) + GitHub Actions `*/5` for the SDR drain |
| Vector search | MongoDB Atlas Vector Search |

Authoritative current-state documents:

- `docs/agent-module/00-forensics.md` — full forensics, 2026-07-22
- `docs/ai-sdr/00-existing-architecture-report.md` — the same exercise for the SDR module
- `docs/ai-sdr/adr/` — five accepted ADRs, including
  `0001-reconciling-the-spec-with-the-existing-stack.md`

## Files here

| File | What it wrongly asserts |
|---|---|
| `ARCHITECTURE_DECISION.md` | A "final target architecture" of Hostinger Node + Supabase Auth + Stripe/Razorpay |
| `SUPABASE_SCHEMA_PLAN.md` | A 23-table Postgres schema with UUID PKs, `agency_id` multi-tenancy and RLS |
| `BACKEND_ATLAS_SUPABASE_DEPLOYMENT.md` | Atlas → Supabase deployment path |
| `DATABASE_MIGRATION.md` | Mongo → Supabase PostgreSQL migration process |
| `HOSTINGER_DEPLOYMENT.md` | That the backend deploys to Hostinger managed Node |
| `HOSTINGER_COMPATIBILITY.md` | A migration compatibility matrix (its own status column reads "Not implemented") |

Note the multi-tenancy point especially: `SUPABASE_SCHEMA_PLAN.md` puts
`agency_id` on every table. AgencyOS is **single-tenant on purpose**
(ADR 0002); the seam is `repositories/base.scope()`.

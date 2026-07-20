# ADR 0001 — Reconciling the AI SDR spec with the existing stack

**Status:** Accepted · **Date:** 2026-07-20 · **Phase:** 0

## Context

The AI SDR specification was written against an assumed stack: Next.js App
Router with server actions and RSC, strict TypeScript with ESLint boundary
rules, Postgres with Prisma/Drizzle migrations and Row Level Security,
pgvector for retrieval, and a durable job queue (Inngest / Trigger.dev /
BullMQ).

AgencyOS is none of those. Phase 0 forensics established it as FastAPI +
MongoDB + React 19 on CRA/CRACO, in JavaScript, deployed to Vercel
serverless, with no migrations, no queue, no tests and no CI.

The spec's own working protocol resolves this: *the existing codebase wins on
conventions, this spec wins on functionality.* This ADR records how that rule
was applied so the deviations are deliberate and legible rather than looking
like drift.

## Decision

Translate the spec's intent onto the host stack rather than importing its
implementation choices.

| Spec assumes | We do | Why |
|---|---|---|
| Next.js server actions | FastAPI routers + axios | No Next.js in the repo. Adding it would mean a second frontend app, which rule 2 forbids. |
| Strict TypeScript | JavaScript/JSX + Pydantic | `design_guidelines.json` explicitly forbids TypeScript: *"Use ONLY React + Tailwind + pure JavaScript"*. Type safety is enforced at the API boundary by Pydantic instead. |
| Postgres + migrations + RLS | MongoDB + idempotent `create_sdr_indexes()` | No second database (rule 5). Mongo has no migrations here; index creation is idempotent and runs at startup. |
| pgvector for KB retrieval | Mongo text indexes | Vector search is unavailable on this deployment. Documented as a limitation; retrieval quality will be lower. |
| ESLint layer-boundary rules | Convention + code review | No lint boundary tooling exists and adding it repo-wide is out of scope. The layering is documented in `sdr/__init__.py` and mirrored by the directory structure. |
| `numeric(14,2)` money | Existing float + `currency` + `conversion_rate` convention | A mixed money regime is worse than one imperfect one. Noted: the host app already shipped a bug here where `conversion_rate` defaulted to 1.0. |
| `timestamptz` | ISO-8601 strings | Matches every existing collection. Send-window logic must parse before comparing, never rely on string ordering across zones. |
| Granular `sdr:*` permissions | One `ai_sdr` module key | The host permission system is one flat string per module. Verb-scoped scopes would mean rebuilding permissions app-wide. Destructive actions additionally require `require_admin`. |
| Per-org feature flags | Flags in the SDR settings singleton | No flag mechanism exists; this matches how `company_settings` already works. |

## Consequences

**Good.** The module is genuinely native — it inherits auth, layout, theming,
audit logging and deployment for free, and a developer who knows AgencyOS can
read it without learning a second set of conventions.

**Bad.** We lose compile-time type safety on the frontend, schema-enforced
migrations, and database-level tenant isolation. The first is mitigated by
Pydantic at the boundary; the second by idempotent index creation and
defensive `.get()` reads; the third is deferred entirely (ADR 0002).

**Watch.** Every future phase must re-apply this rule rather than reaching for
the spec's literal implementation. When in doubt, read an existing router and
copy its shape.

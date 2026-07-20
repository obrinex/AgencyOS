# ADR 0002 — Ship single-tenant, isolate the seam

**Status:** Accepted · **Date:** 2026-07-20 · **Phase:** 1

## Context

The spec makes multi-tenancy non-negotiable: *"Every new table has an
organisation/tenant scope column and every query is tenant-filtered. There is
no such thing as a global query in this module."*

AgencyOS has no tenancy whatsoever. A grep for `org_id`, `tenant_id`,
`workspace_id` and `organization` across the backend returns zero matches.
Queries start `query = {}` (`crm.py:82`) and `db.clients.find({})`
(`clients.py:42`). `company_settings` is a singleton keyed `{"key": "main"}`
with the agency name hardcoded. The repo's own `TENANT_SECURITY.md` states the
current schema "is not sufficient for a multi-tenant SaaS release."

The closest thing to scoping is ownership (`owner_id`) and the client portal
boundary (`portal.py:33` reads `user["client_id"]`) — neither is a tenant.

## Options

1. **Add `org_id` to SDR collections only.** Satisfies the letter of the spec.
2. **Retrofit tenancy across all 37 collections first.** Satisfies its intent.
3. **Build single-tenant, route every query through one function.**

## Decision

Option 3.

Option 1 produces a half-tenanted system whose guarantees are illusory and
therefore actively dangerous: an SDR lead would be tenant-scoped, but the
client it converts into via `run_won_automation`, the project created
alongside it, and the invoice attached to that project would all be global.
An engineer reading `org_id` on `sdr_companies` would reasonably conclude the
system is multi-tenant. It would not be. A security property that is believed
but false is worse than one that is absent and known.

Option 2 is a separate project touching every router, every collection and the
entire auth model, with a 1 August launch twelve days out.

So: single-tenant, matching the app — but **every SDR read and write goes
through `sdr/repositories/base.scope()`**, which today only filters soft-deleted
rows. When tenancy lands, it becomes one function body plus a backfill, not an
archaeology exercise across dozens of call sites.

```python
def scope(query=None, *, user=None):
    scoped = dict(query or {})
    # When tenancy lands, this is the line:
    #     scoped["org_id"] = require_org_id(user)
    scoped.setdefault("deleted_at", None)
    return scoped
```

## Consequences

**Good.** No false security claim. The seam is one function with one obvious
edit. SDR collections stay consistent with the 37 that came before them.

**Bad.** The module cannot be sold as multi-tenant SaaS until tenancy is done
app-wide. The spec's cross-tenant test matrix is not implementable and is
deliberately not written — a passing test against a single-tenant system would
be theatre.

**Enforcement.** Any SDR code issuing a raw `db[...]` query outside
`sdr/repositories/` is a defect, because it bypasses the seam this decision
exists to preserve.

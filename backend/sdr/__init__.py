"""AI SDR module.

A native extension of AgencyOS, not a separate application. It reuses the host
app's auth (`auth_utils`), database handle (`database.db`), LLM client
(`routers.ai`), email sender (`email_service`) and cron entrypoints
(`routers.automations`).

Layering, enforced by convention (this repo has no lint boundary tooling):

    routers/sdr.py        HTTP only - auth guard + Pydantic validation, no logic
      -> sdr/services     orchestration, transactions, side effects
        -> sdr/domain     pure functions. Zero I/O, zero imports from anywhere
                          else in this package. This is the tested layer.
        -> sdr/repositories   the ONLY place that touches db.*

`sdr/domain/` must never reference a country, currency, timezone or phone
prefix literal - those live in `sdr/config/countries.py`. See
docs/ai-sdr/00-existing-architecture-report.md for the full integration plan.
"""

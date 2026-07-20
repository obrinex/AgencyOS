# Here are your Instructions

## AI SDR module

An autonomous prospecting module built natively inside this dashboard — it
reuses the existing auth, layout, CRM collections and deployment rather than
standing up anything parallel. Lives at `/ai-sdr` in the app, `backend/sdr/`
and `backend/routers/sdr.py` on the server.

Docs are in [`docs/ai-sdr/`](docs/ai-sdr/):

- [`00-existing-architecture-report.md`](docs/ai-sdr/00-existing-architecture-report.md) — how this codebase actually works, and how the SDR spec was mapped onto it. **Read this first.**
- [`CHANGELOG.md`](docs/ai-sdr/CHANGELOG.md) — what each phase delivered.
- [`adr/`](docs/ai-sdr/adr/) — the decisions that are hard to reverse and why they went the way they did.

Run the domain tests with `python -m pytest tests/sdr`.

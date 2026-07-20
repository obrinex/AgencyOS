"""Configuration registries.

Everything market-specific lives here - currencies, timezones, phone formats,
holidays, compliance obligations, industry benchmarks. `sdr/domain/` and
`sdr/services/` resolve values from these registries and must never contain a
country, currency, timezone or dialling-code literal of their own.

The check at the end of every phase is a grep for "India", "INR", "IST" and
"+91" outside this package. Any hit is a bug.
"""

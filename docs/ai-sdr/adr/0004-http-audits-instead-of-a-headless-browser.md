# ADR 0004 — HTTP audits instead of a headless browser

**Status:** Accepted · **Date:** 2026-07-20 · **Phase:** 4

## Context

The spec's Website Audit agent calls for a headless crawl: Lighthouse scores,
Core Web Vitals, mobile rendering, and testing whether the contact form
actually submits.

The backend runs on Vercel's Python serverless runtime. There is no Chromium
in the image, no way to install one within the deployment size limit, and a
60-second request ceiling that a cold Playwright launch plus a Lighthouse run
would consume on its own. The queue drains inside that same ceiling, so a
browser-based audit could not run there either.

## Options

1. **Add Playwright.** Requires leaving Vercel for the backend, or a second
   long-running service. Both are large infrastructure changes twelve days
   before launch, and the spec forbids introducing a long-running server where
   none exists.
2. **Use a hosted API** (PageSpeed Insights, WebPageTest). Real Lighthouse
   data, no infrastructure — but a paid dependency and an external rate limit
   on the hot path of every audit.
3. **Audit over plain HTTP** and be explicit about what that cannot see.

## Decision

Option 3 now, with option 2 as the documented upgrade path.

One HTTPS fetch through the SSRF guard, then pure detectors over the HTML.
That measures more than it sounds: TLS validity, mobile viewport, forms and
their shape, chat/booking/CRM/analytics/marketing vendors by fingerprint,
WhatsApp and click-to-call routes, structured data, structural SEO, and server
response time. Thirteen of the nineteen shipped signals fire from it.

**The part that makes this honest rather than a compromise:** facts we cannot
measure are *absent* from the audit, not `False`. `signals.detect()` treats an
absent fact as "unknown — claim nothing" and emits no signal, so an
unmeasurable gap produces silence rather than a fabricated finding. That
behaviour was built in Phase 1 and this is what it was for.

Two signals that depended solely on Lighthouse were rewired to measurable
proxies — response time for performance, structural checks for SEO — and named
accordingly (`seo_score_basic`, not `lighthouse_seo`) so the weaker measure is
never mistaken for the real one. Both prefer a genuine Lighthouse score if one
is ever supplied.

Every audit stores its `unmeasured` list, and the Audits page states plainly
what is not covered. An audit that silently omitted Core Web Vitals would read
as a clean bill of health on performance.

## Consequences

**Good.** No new infrastructure, no cost, no external rate limit. Fast enough
to run inside the queue's budget. Deterministic and fully unit-testable
against fixtures. No fabricated findings.

**Bad.** Six signals never fire: `no_ai_receptionist`, `slow_response_time`,
`no_review_automation`, `no_booking_reminders`, `stale_content`,
`high_review_volume_no_response`, plus `broken_contact_form` can detect a
missing form but not a broken one. Prospects with genuine performance problems
that only show up in rendering will not be flagged. Single-page audits miss
gaps on interior pages.

**Upgrade path.** Adding PageSpeed Insights as an enrichment provider would
populate `lighthouse_performance` and `lighthouse_seo`, and both detectors
already prefer those over the proxies — no change to the signal registry, the
scoring, or the UI. That is the first thing to do if audit quality becomes the
bottleneck.

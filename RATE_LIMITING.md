# Rate Limiting

## Current strategy

Login brute-force protection exists through Mongo `login_attempts`.

`backend/rate_limit.py` provides a general DB-backed fixed-window limiter
(`check_rate_limit`) keyed on IP or any caller-supplied identity, with
self-expiring counters. Mongo rather than Redis, because the deployment target
has none. It fails open: an outage in the limiter lets requests through, since
dropping real leads is worse than briefly accepting junk.

## Coverage

| Category | Examples | Status |
| --- | --- | --- |
| Auth | login, reset password, 2FA | Done — `login_attempts`, 5 failures then a 15-minute lock |
| Public forms | lead capture, booking | **Lead capture done** — 30/hr per IP on the webhook; 5/hr per IP and 3/hr per email on the public lead form, plus 24-hour deduplication by address. **Booking not yet covered.** |
| AI | chat, generation | Not implemented — needs a user/agency quota and daily usage table |
| Uploads | files | Not implemented — needs per-user count and size limits |
| Cron | automation endpoints | `CRON_SECRET` plus provider IP allowlist if available |

The lead form was the urgent one: unauthenticated, and each submission wrote
three documents, notified every admin, sent a WhatsApp message and spent an LLM
call. That is a billing exposure, not a spam nuisance.

## Caveat on client IP

`client_ip()` trusts `X-Forwarded-For`, which is correct behind Render's or
Vercel's proxy and forgeable by anyone reaching the app directly. It is a speed
bump against scripted abuse, not an access control — never authorise on it.

This remains Hostinger-compatible because it can be implemented in Supabase PostgreSQL without Redis.

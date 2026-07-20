# Rate Limiting

## Current strategy

Login brute-force protection exists through Mongo `login_attempts`. Broader endpoint rate limiting is not implemented.

## Required categories

| Category | Examples | Initial strategy |
| --- | --- | --- |
| Auth | login, reset password, 2FA | DB-backed identifier/IP throttling |
| Public forms | lead capture, booking | DB-backed IP/email throttling |
| AI | chat, generation | user/agency quota and daily usage table |
| Uploads | files | per-user count and size limits |
| Cron | automation endpoints | `CRON_SECRET` plus provider IP allowlist if available |

This remains Hostinger-compatible because it can be implemented in Supabase PostgreSQL without Redis.

# Backend Audit

## Executive summary

Obrinex AgencyOS is currently a React single-page frontend plus a Python FastAPI backend. It is not currently a Hostinger managed Node.js Web App backend. The backend uses MongoDB through Motor, custom JWT authentication, local disk uploads, and startup-created background loops.

## Current stack

- Frontend: React 19, Create React App via CRACO, Tailwind, Radix UI, axios, React Router.
- Backend: Python FastAPI, Uvicorn-compatible ASGI app, Pydantic, Motor/PyMongo.
- Database: MongoDB configured by `MONGO_URL` and `DB_NAME`.
- Authentication: custom email/password auth with bcrypt, JWT access/refresh cookies, optional TOTP 2FA.
- Authorization: role checks through `require_roles`, `require_staff`, `require_admin`, and client-role checks in selected routes. No centralized agency membership enforcement exists.
- API architecture: FastAPI routers under `/api/*`.
- Storage: local backend `uploads/` directory plus Mongo metadata.
- Email: Resend when `RESEND_API_KEY` is configured; mocked logging fallback otherwise.
- Payments: Stripe package present and payment link/request code exists; webhook verification must be reviewed before production.
- AI: OpenAI SDK pointed at NVIDIA-compatible API key/model in `routers/ai.py`; key is server-side.
- Automations: Python async startup loops in `reminders.py`; now disabled by default unless `RUN_BACKGROUND_LOOPS=true`.

## Feature backend status

- Auth: real backend, custom JWT, bcrypt, refresh cookies, reset flow, 2FA.
- Dashboard: real Mongo aggregation/count queries.
- Clients/contacts/leads/pipeline: real Mongo routes.
- Tasks/projects/support/knowledge/notes/meetings: real Mongo routes.
- Invoices/expenses/payment requests: real Mongo routes with server-calculated totals, but float money handling remains a production risk.
- Files: real local upload/download/delete; not production-compatible as permanent storage.
- Vault: encrypted password field using server-side Fernet key; list route hides ciphertext and reveal is explicit.
- Portal: real routes using client user role/client_id.
- Automations: real code, but persistent loop design is incompatible with managed Node hosting.

## Findings

| Severity | Finding | Evidence | Status |
| --- | --- | --- | --- |
| CRITICAL | Backend stack is Python/FastAPI, not Node.js. | `backend/server.py`, `backend/requirements.txt` | Requires migration to Node or a hosting product that supports Python; VPS is disallowed. |
| CRITICAL | Database is MongoDB, not Supabase PostgreSQL. | `backend/database.py` | Requires managed Postgres schema/migration for target architecture. |
| CRITICAL | No multi-tenant agency isolation model. | Queries generally omit `agency_id`. | Not production SaaS-ready. |
| HIGH | Local file storage is used for uploads. | `backend/routers/files.py` | Must migrate to Supabase Storage before Hostinger production. |
| HIGH | Startup background loops existed. | `backend/server.py`, `backend/reminders.py` | Disabled by default; stateless cron endpoints added. |
| HIGH | Financial values use floating point. | `backend/routers/finance.py` | Must migrate to integer minor units or Decimal/numeric. |
| HIGH | Frontend API base URL depends on `REACT_APP_BACKEND_URL`. | `frontend/src/lib/api.js` | For same-origin Hostinger deployment, use empty/same-origin value or Node API proxy. |
| MEDIUM | Rate limiting is limited to login attempts in Mongo. | `auth_utils.py` | Needs category-based limits for auth, AI, uploads, public forms. |
| MEDIUM | Audit logging exists but is not agency-aware. | `auth_utils.log_audit` | Add `agency_id`, request id, resource ownership context. |
| MEDIUM | Email can silently mock when key is missing. | `email_service.py` | Production env validation should require email key if email features are enabled. |
| LOW | Render deployment artifact remains. | `render.yaml`, `DEPLOYMENT.md` | Replace with Hostinger-specific deployment docs. |

## Browser storage

Search results show no application-wide sensitive `localStorage` or `sessionStorage` persistence in the source scan. Auth is cookie based. Recheck before release after future frontend changes.

## Exposed secrets

No literal secret value was identified in the initial scan, but the repo contains environment variable names for MongoDB, JWT, Resend, Stripe, Google OAuth, and NVIDIA AI. Real credentials in any untracked `.env` or previous commits must be rotated if ever committed.

## Production blockers

1. Python backend is not deployable as the requested Hostinger managed Node.js app.
2. MongoDB data model is not Supabase PostgreSQL/RLS.
3. Tenant isolation is not implemented.
4. Local upload storage is not durable production storage.
5. Persistent background workers were part of runtime design.

# AgencyOS — Deployment Guide

Stack: **FastAPI + MongoDB** (backend) and **React (CRA)** (frontend).

On its first startup, the backend creates the administrator from `ADMIN_EMAIL`
and `ADMIN_PASSWORD`. It never changes an existing password during startup.

> **Cookies:** the browser only ever talks to `crm.obrinex.space`, because
> `/api/*` is rewritten to a proxy function on that same origin. The auth
> cookie is therefore first-party and the frontend and backend do **not** need
> to share a root domain. Remove that proxy and they do — at which point
> `COOKIE_SAMESITE` and `CORS_ORIGINS` both start to matter.

## How this is actually deployed

Two Vercel projects from one GitHub repo, `github.com/obrinex/AgencyOS`.
Nothing runs on Render; `render.yaml` is a leftover of an earlier plan and is
not used by anything.

| Project | Root directory | Serves |
|---|---|---|
| `frontend` | `frontend` | `crm.obrinex.space` |
| `backend` | `backend` | `backend-five-hazel-13.vercel.app` |

The frontend never calls the backend directly. `frontend/api/proxy.js` is a
Vercel function that forwards `/api/*` to `BACKEND_ORIGIN`, which is why
`REACT_APP_BACKEND_URL` is empty and the browser only ever talks to one
origin - no CORS, and the auth cookie stays first-party. Changing the backend
URL means editing that file, not an environment variable.

Both projects deploy on push to `main`. They were previously deployed by
running `vercel --prod` from a laptop, which is how an entire uncommitted
module once ended up in production while `main` knew nothing about it - if
you find yourself reaching for the CLI, prefer a push.

### Database — MongoDB Atlas

1. Create a cluster at https://cloud.mongodb.com
2. Create a database user with a strong generated password. Under **Network
   Access**, allow only your backend host's outbound IPs or private network.
3. Set `MONGO_URL` and `DB_NAME` in the `backend` project's environment.

### Backend environment

Set in the Vercel `backend` project, not in a file:

| Variable | Notes |
|---|---|
| `MONGO_URL` | Atlas connection string |
| `DB_NAME` | `agencyos` |
| `APP_ENV` | `production` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | the first-run administrator |
| `JWT_SECRET` | 64+ characters; also signs unsubscribe tokens |
| `VAULT_ENCRYPTION_KEY` | Fernet key |
| `CORS_ORIGINS` / `ALLOWED_HOSTS` | the CRM domain |
| `COOKIE_SECURE` / `COOKIE_SAMESITE` | `true` / `none` |
| `RESEND_API_KEY`, `SENDER_EMAIL` | outbound email |
| `LLM_PROVIDERS` | provider order; `SDR_LLM_PROVIDERS` still honoured |
| `NVIDIA_API_KEY` and friends | at least one, or AI features return 503 |

`JWT_SECRET` deserves care: `suppression.py` derives one-click unsubscribe
tokens from it. Rotating it invalidates every unsubscribe link in email
already delivered, so those recipients can no longer opt out from the footer.

### Serverless notes

- `backend/vercel.json` routes everything to `api/index.py` and sets
  `includeFiles: legal/**`. Those eleven legal documents are markdown that no
  Python module imports, so without that line the bundler leaves them out and
  the Terms page renders blank. `/api/policies/_health` lists any that are
  missing.
- Background loops do not run. `RUN_BACKGROUND_LOOPS` stays false and the
  scheduled work is driven by the crons in `backend/vercel.json`, which hit
  authenticated endpoints guarded by `CRON_SECRET`.

## Running locally

```
# backend (needs local MongoDB, or point MONGO_URL at Atlas)
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8000

# frontend
cd frontend
yarn install
yarn start
```

Local config lives in `backend/.env` and `frontend/.env` (both gitignored).

## Security checklist
- Keep `.env` files out of source control; use your hosting provider's secret manager.
- Rotate any API key or password that has been pasted into a chat, terminal log, or commit.
- Use HTTPS for both the dashboard and API, set `COOKIE_SECURE=true`, and set exact CORS origins and allowed hosts.
- With the temporary Vercel and Render domains, set `COOKIE_SAMESITE=none`.
  Once custom subdomains are in place, use `COOKIE_SAMESITE=lax` for stronger
  browser privacy defaults.
- Enable MongoDB backups and restrict Atlas network access before accepting client data.
- The AI assistant uses NVIDIA's API (https://build.nvidia.com). Set
  `NVIDIA_API_KEY` (and optionally `NVIDIA_MODEL`) — without it, the AI
  assistant returns a "not configured" error but the rest of the app works.

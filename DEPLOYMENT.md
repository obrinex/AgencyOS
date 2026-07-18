# AgencyOS — Deployment Guide

Stack: **FastAPI + MongoDB** (backend) and **React (CRA)** (frontend).

On its first startup, the backend creates the administrator from `ADMIN_EMAIL`
and `ADMIN_PASSWORD`. It never changes an existing password during startup.

> **Important:** auth cookies use `SameSite=Lax`, so the frontend and backend
> **must share the same root domain** in production (e.g.
> `dashboard.obrinex.space` + `api.obrinex.space`). Hosting them on unrelated
> domains (e.g. `*.vercel.app` + `*.onrender.com`) will break login.

## Recommended setup (free tier friendly)

### 1. Database — MongoDB Atlas
1. Create a free M0 cluster at https://cloud.mongodb.com
2. Create a database user with a strong generated password. Under **Network
   Access**, allow only your backend host's outbound IPs or private network.
3. Copy the connection string, e.g.
   `mongodb+srv://<user>:<pass>@cluster0.xxxxx.mongodb.net`

### 2. Backend — Render
1. Push this repo to GitHub.
2. On https://render.com create a **Blueprint** from the repository. The
   included `render.yaml` creates the FastAPI service. Enter all variables
   marked as private in Render's secret manager; do not copy local `.env` files.
3. Build command:
   ```
   pip install -r requirements.txt
   ```
4. Start command:
   ```
   uvicorn server:app --host 0.0.0.0 --port $PORT
   ```
5. Environment variables:
   | Variable | Value |
   |---|---|
   | `MONGO_URL` | Atlas connection string |
   | `DB_NAME` | `agencyos` |
   | `APP_ENV` | `production` |
   | `ADMIN_EMAIL` | private administrator email |
   | `ADMIN_PASSWORD` | unique password, 14+ characters |
   | `JWT_SECRET` | a newly generated 64+ character secret |
   | `VAULT_ENCRYPTION_KEY` | a newly generated Fernet key |
   | `FRONTEND_URL` | `https://dashboard.obrinex.space` |
   | `CORS_ORIGINS` | `https://dashboard.obrinex.space` |
   | `ALLOWED_HOSTS` | `api.obrinex.space` |
   | `COOKIE_SECURE` | `true` |
   | `COOKIE_SAMESITE` | `none` for a `vercel.app` + `onrender.com` launch; `lax` once both use `*.yourdomain.com` |
   | `NVIDIA_API_KEY` | (optional) from https://build.nvidia.com — AI assistant |
   | `NVIDIA_MODEL` | (optional) defaults to `meta/llama-3.3-70b-instruct` |
   | `STRIPE_API_KEY` | (optional) invoice payments |
   | `CASHFREE_APP_ID` | Cashfree client id — card/UPI/net banking |
   | `CASHFREE_SECRET_KEY` | Cashfree client secret (also verifies webhooks) |
   | `CASHFREE_ENV` | `sandbox` or `production` (default `sandbox`) |
   | `BACKEND_URL` | Public URL of this backend, so Cashfree can reach the webhook |
   | transactional email key / `SENDER_EMAIL` | required for invoice and password-reset emails |
   | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | (optional) Calendar sync |
6. Under **Settings → Custom Domains** add `api.obrinex.space`, then create
   the CNAME record it shows you in your DNS provider for `obrinex.space`.

### 3. Frontend — Vercel
1. On https://vercel.com import the same repo, root directory `frontend`.
2. Framework preset: **Create React App** (build runs via craco automatically).
3. Environment variable:
   - `REACT_APP_BACKEND_URL` = your Render API URL, for example `https://agencyos-api.onrender.com`
4. Under **Settings → Domains** add `dashboard.obrinex.space` and create the
   CNAME record in your DNS.

### 4. Verify
1. Open `https://dashboard.obrinex.space`
2. Log in with the private administrator credentials configured in your host.

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

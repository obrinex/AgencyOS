# Backend Deployment: MongoDB Atlas + Supabase Reality Check

## Current backend

The current backend is a Python FastAPI application in `backend/`. It connects to MongoDB through `MONGO_URL` and `DB_NAME`.

## What can be deployed now

- Database: MongoDB Atlas free/shared cluster.
- Backend compute: a Python-capable host such as Render free web service, Railway, Fly, or another managed Python web app host.
- Frontend: Vercel, already deployed.

## What cannot be deployed as-is

Supabase does not run this Python FastAPI app. Supabase Edge Functions are TypeScript/Deno serverless functions, so deploying this backend to Supabase requires porting API routes from FastAPI/Python to Supabase Edge Functions or a Node/Deno backend.

## MongoDB Atlas setup

1. Create a MongoDB Atlas project.
2. Create a free/shared Atlas cluster.
3. Create a database user with a strong password.
4. In Network Access, allow your backend host outbound access. For free hosts with changing IPs, use `0.0.0.0/0` only temporarily and tighten it when the host provides fixed outbound IPs.
5. Copy the connection string.
6. Use database name `agencyos`.

Example connection string format:

```text
mongodb+srv://<db_user>:<db_password>@<cluster-host>/agencyos?retryWrites=true&w=majority
```

## Verify the Atlas connection locally

After setting `MONGO_URL` and `DB_NAME` in `backend/.env`, run:

```bash
cd backend
python verify_atlas.py
```

Expected output:

```text
MongoDB Atlas connection OK: database=agencyos
```

## Backend environment variables

Set these in the backend host secret manager:

```text
APP_ENV=production
MONGO_URL=<MongoDB Atlas connection string>
DB_NAME=agencyos
ADMIN_EMAIL=<owner admin email>
ADMIN_PASSWORD=<strong one-time bootstrap password>
JWT_SECRET=<64+ character random secret>
VAULT_ENCRYPTION_KEY=<Fernet key>
CRON_SECRET=<64+ character random secret>
RUN_BACKGROUND_LOOPS=false
FRONTEND_URL=https://frontend-eta-wheat-p5nx1g2pih.vercel.app
CORS_ORIGINS=https://frontend-eta-wheat-p5nx1g2pih.vercel.app
ALLOWED_HOSTS=<backend-hostname>
COOKIE_SECURE=true
COOKIE_SAMESITE=none
```

Optional:

```text
RESEND_API_KEY=
SENDER_EMAIL=
STRIPE_API_KEY=
STRIPE_WEBHOOK_SECRET=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
NVIDIA_API_KEY=
NVIDIA_MODEL=
```

## Build and start commands for the current backend

Build:

```bash
pip install -r requirements.txt
```

Start:

```bash
uvicorn server:app --host 0.0.0.0 --port $PORT
```

Root directory:

```text
backend
```

Health check:

```text
/api/
```

## Connect Vercel frontend to backend

After the backend deploys, set this Vercel environment variable:

```text
REACT_APP_BACKEND_URL=https://<backend-hostname>
```

Then redeploy the frontend.

## Supabase path

Supabase can be used later for:

- Auth
- Postgres database
- Storage
- Edge Functions

That is a migration, not a deployment of this existing backend. The practical rewrite path is:

1. Move Mongo collections to Supabase PostgreSQL.
2. Replace custom JWT auth with Supabase Auth.
3. Move uploads to Supabase Storage.
4. Port `/api/*` routes to Node/Deno serverless handlers or a Node backend.
5. Retire the FastAPI/Mongo service.

Until that migration is complete, MongoDB Atlas is the correct managed database for this existing backend.

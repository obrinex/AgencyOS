> # ⛔ SUPERSEDED — NEVER IMPLEMENTED. DO NOT USE AS A SOURCE OF TRUTH.
>
> This document describes a planned migration to **Hostinger managed Node.js +
> Supabase PostgreSQL/Auth** that **was never carried out**. No part of it
> shipped. Nothing in it describes the running system.
>
> **AgencyOS actually runs on:** FastAPI + MongoDB Atlas (Motor) + React 19 on
> CRA/CRACO, deployed to **Vercel**, with custom JWT/bcrypt/TOTP auth,
> three roles (`admin`/`team_member`/`client`), and **Cashfree** payments.
>
> Archived 2026-07-22: these files were mistaken for current state and produced
> a module specification written against a stack that does not exist.
> For the verified live architecture see `docs/agent-module/00-forensics.md` §0.

# Architecture Decision

## Existing architecture

React SPA frontend plus Python FastAPI API, MongoDB, local disk file storage, custom JWT auth, Resend email, Stripe-related payment flows, NVIDIA/OpenAI-compatible AI calls, and in-process automation loops.

## Final target architecture

- Host: Hostinger managed Node.js Web App.
- Frontend: existing React UI and branding.
- Backend: one Node.js application serving the React build and `/api/*` routes.
- Database: Supabase managed PostgreSQL.
- Auth: Supabase Auth preferred.
- Storage: Supabase Storage private buckets.
- Email: managed Resend API.
- Payments: managed Stripe/Razorpay APIs with server-side webhook verification.
- AI: managed AI APIs called only server-side.
- Automations: stateless authenticated cron endpoints.

## Why no VPS is required

The target design delegates infrastructure to managed services: Hostinger runs the Node app, Supabase runs database/auth/storage, and external providers run email/payments/AI. No root access, OS services, Docker, PM2, Nginx, Redis, or persistent workers are required.

## Known limitations

Hostinger managed Node hosting should run request/response workloads, not permanent workers. Scheduled work must be externally triggered. File persistence must not depend on the app filesystem.

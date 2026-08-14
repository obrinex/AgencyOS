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

# Database Migration

## Current database

MongoDB collections managed ad hoc through application code and index creation.

## Target database

Supabase PostgreSQL with SQL migrations committed to the repository.

## Production process

1. Create a Supabase production project.
2. Apply schema migrations to a staging project first.
3. Run data migration scripts from MongoDB export to PostgreSQL staging.
4. Validate counts, ownership, financial totals, files, and portal access.
5. Back up production before migration.
6. Apply migrations without resetting production data.

Never run destructive resets against production.

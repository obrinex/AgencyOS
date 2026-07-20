# Tenant Security

## Current state

The current MongoDB schema and route queries generally do not include `agency_id`. Roles are global (`admin`, `team_member`, `client`) rather than agency-scoped. This is not sufficient for a multi-tenant SaaS release.

## Required model

- `profiles`: user profile linked to Supabase Auth user.
- `agencies`: tenant/workspace.
- `agency_members`: user to agency membership with role.
- Tenant tables: include non-null `agency_id`.
- Client portal users: constrained to the agency and client they belong to.

## RLS strategy

Enable RLS on every tenant-sensitive Supabase table. Policies must check membership, not `USING (true)`. Service-role operations must still validate membership and resource ownership before using elevated credentials.

## Server-side rules

Never trust `agency_id` from the frontend. Determine agency access from the authenticated user and membership rows. For every sensitive API route validate authentication, agency membership, permission, and resource ownership.

## Cross-tenant tests

Add tests proving Agency A cannot read, update, delete, or sign Agency B resources for clients, invoices, files, documents, tasks, vault entries, AI conversations, and settings.

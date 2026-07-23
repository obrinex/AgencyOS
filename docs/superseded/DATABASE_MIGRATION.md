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

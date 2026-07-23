# Supabase Schema Plan

Do not create every possible table blindly. Start with tables matching currently implemented production features.

## Phase 1 tables

- `profiles`
- `agencies`
- `agency_members`
- `clients`
- `contacts`
- `leads`
- `pipeline_stages`
- `tasks`
- `projects`
- `invoices`
- `invoice_items`
- `payments`
- `proposals`
- `contracts`
- `meetings`
- `files`
- `notifications`
- `activity_logs`
- `audit_logs`
- `ai_conversations`
- `ai_messages`
- `integration_connections`
- `agency_settings`

## Table rules

- Use UUID primary keys.
- Include `agency_id` on every tenant table.
- Enable RLS on tenant tables.
- Add foreign keys for ownership.
- Add `created_at` and `updated_at`.
- Add indexes based on real queries: `agency_id`, `created_at`, `status`, `client_id`, `user_id`, `due_date`, and email fields where searched.
- Store financial amounts as integer minor units or PostgreSQL `numeric`, not floats.

## Storage

Use private Supabase Storage buckets and a `files` metadata table containing `agency_id`, bucket, storage path, original filename, MIME type, byte size, uploader, and timestamps.

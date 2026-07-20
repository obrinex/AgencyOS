# Backup And Recovery

Use Supabase managed backup features appropriate to the selected plan. Do not assume point-in-time recovery is available unless the chosen Supabase plan includes it.

Manual owner actions:

- Confirm Supabase plan backup capability before production.
- Export database before destructive migrations.
- Document restore steps and test restore in a non-production project.
- Store critical exported backups securely.
- Review storage retention for contracts, invoices, and signed documents before deleting files.

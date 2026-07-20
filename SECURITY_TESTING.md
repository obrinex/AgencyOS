# Security Testing

Minimum production test coverage:

- Authentication: valid, invalid, unauthenticated, expired token.
- Authorization: owner/admin/member/viewer/client restrictions after RBAC migration.
- Tenant isolation: cross-agency read/update/delete denied for clients, invoices, documents, files, vault, settings.
- Invoices: server-side totals, invalid money, unauthorized access.
- Payments: invalid signature, duplicate webhook, valid webhook.
- Vault: plaintext not stored, list hides secrets, unauthorized reveal denied.
- Files: invalid MIME, oversize, cross-agency access, signed URL authorization.
- AI: unauthenticated denied, quota enforced, vault data excluded.
- Automations: invalid cron secret denied, duplicate execution controlled, bounded batches.

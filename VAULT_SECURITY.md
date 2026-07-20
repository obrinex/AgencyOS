# Vault Security

## Current state

Vault passwords are encrypted server-side with `VAULT_ENCRYPTION_KEY` using Fernet. List responses remove `encrypted_password`; reveal requires a dedicated endpoint and staff role.

## Required production controls

- Keep encryption keys server-side only.
- Rotate keys through versioned key material before SaaS launch.
- Add `agency_id` to every vault record.
- Require specific `vault.read` / `vault.manage` permissions.
- Audit reveal actions with actor, agency, resource id, request id, and timestamp.
- Never log decrypted values.
- Never include vault secrets in AI context or analytics.

## Limitations

Current access control is global-role based, not tenant-membership based. Do not enable vault for external SaaS tenants until agency isolation is complete.

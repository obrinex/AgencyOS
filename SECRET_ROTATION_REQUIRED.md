# Secret Rotation Required

No real credential value was found during the source scan performed in this pass. Environment variable names are present, but `.gitignore` excludes `.env`, `.env.*`, credential JSON files, keys, and token files.

Rotate credentials immediately if any real secret was ever committed in prior history, shared in screenshots/logs, or pasted into deployment files. Secrets to review:

- `MONGO_URL`
- `JWT_SECRET`
- `VAULT_ENCRYPTION_KEY`
- `RESEND_API_KEY`
- `STRIPE_API_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `GOOGLE_CLIENT_SECRET`
- `NVIDIA_API_KEY`
- Future Supabase service role key

Do not expose service-role, payment, AI, OAuth, database, or vault encryption secrets to frontend environment variables.

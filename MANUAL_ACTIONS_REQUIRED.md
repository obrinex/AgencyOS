# Manual Actions Required

## Hostinger Node.js support

ACTION: Confirm your Hostinger plan supports Node.js Web Apps.  
WHY REQUIRED: The target architecture depends on Hostinger running a Node app.  
WHERE TO DO IT: Hostinger hPanel.  
EXACT VALUE OR VARIABLE NEEDED: None.  
WHEN TO DO IT: Before backend migration/deployment.  
HOW TO VERIFY: hPanel shows Node.js app setup for the hosting plan.

## Supabase project

ACTION: Create production Supabase project.  
WHY REQUIRED: Managed PostgreSQL/Auth/Storage target.  
WHERE TO DO IT: Supabase dashboard.  
EXACT VALUE OR VARIABLE NEEDED: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, server-only service role key after migration.  
WHEN TO DO IT: Before database migration.  
HOW TO VERIFY: Project is reachable and migrations apply in staging.

## Production secrets

ACTION: Configure environment variables in Hostinger.  
WHY REQUIRED: Secrets must not be committed.  
WHERE TO DO IT: Hostinger Node.js app environment settings.  
EXACT VALUE OR VARIABLE NEEDED: See `.env.example`.  
WHEN TO DO IT: Before first deployment.  
HOW TO VERIFY: App starts without missing-env errors.

## Domain and SSL

ACTION: Point `app.obrinex.com` to the Hostinger app and enable SSL.  
WHY REQUIRED: Secure same-origin app/API deployment.  
WHERE TO DO IT: DNS provider and Hostinger hPanel.  
EXACT VALUE OR VARIABLE NEEDED: Hostinger DNS target.  
WHEN TO DO IT: Before production launch.  
HOW TO VERIFY: `https://app.obrinex.com` loads with valid HTTPS.

## Provider credentials

ACTION: Configure Resend, Stripe/Razorpay, Google OAuth, and AI provider credentials only for features you will launch.  
WHY REQUIRED: External integrations need managed provider accounts and webhook/OAuth setup.  
WHERE TO DO IT: Each provider dashboard plus Hostinger env vars.  
EXACT VALUE OR VARIABLE NEEDED: API keys, webhook secrets, OAuth client IDs/secrets.  
WHEN TO DO IT: Before enabling each integration.  
HOW TO VERIFY: Integration health checks and webhook tests pass.

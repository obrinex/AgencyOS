# Hostinger Deployment

## Current deployment warning

The existing backend is Python FastAPI. Hostinger managed Node.js Web App hosting requires a Node.js application, so deploy only after the backend is migrated to Node or wrapped into a supported Node API. Do not use VPS, PM2, Docker, Nginx, or root-server instructions.

## Target setup

1. Use a Hostinger plan that supports Node.js Web Apps.
2. Connect the GitHub repository in hPanel.
3. Select the migrated Node app project directory.
4. Use the Node version supported by the project `package.json`.
5. Build command: project-specific Node build command after migration.
6. Start command: project-specific Node start command that binds `process.env.PORT`.
7. Domain: prefer `https://app.obrinex.com`.
8. API: prefer same-origin `https://app.obrinex.com/api/*`.
9. Configure environment variables in Hostinger, not in source.
10. Configure Supabase Auth site URL and allowed redirects for `https://app.obrinex.com`.
11. Configure CORS to explicit production origins only.
12. Configure payment webhook URLs under `/api/webhooks/*` after routes exist.
13. Verify SSL/HTTPS from hPanel.
14. Run database migrations before first production traffic.
15. Verify login, tenant isolation, uploads, payment webhooks, email, AI, and cron triggers.

## Required environment variables

Use `.env.example` as the variable inventory. Do not paste real credentials into Git.

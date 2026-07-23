# Hostinger Managed Hosting Compatibility

Target: Hostinger managed Node.js Web App hosting, no VPS, no Docker, no PM2, no self-managed services.

| Current component | Compatibility | Managed-hosting replacement | Migration impact | Implementation status |
| --- | --- | --- | --- | --- |
| Python FastAPI backend | Incompatible with Node.js Web App runtime | Single Node.js backend/API or Next.js route handlers | High: port API routes and tests | Not implemented |
| MongoDB/Motor | Not target architecture | Supabase managed PostgreSQL | High: relational schema and data migration | Not implemented |
| Startup async loops | Risky/incompatible | Authenticated cron endpoints triggered by managed scheduler | Medium | Persistent loops disabled by default; cron endpoints added |
| Local uploads directory | Incompatible for durable files | Supabase Storage private buckets | Medium/high | Validation hardened; storage migration pending |
| Custom JWT auth | Deployable but not preferred | Supabase Auth | Medium/high | Existing custom auth retained until migration |
| Render deployment files | Wrong platform | Hostinger Node app instructions | Low | Hostinger docs added |
| Same-origin API | Preferred | `https://app.obrinex.com/api/*` | Medium after Node migration | Documented |

## Compatibility decision

The current backend cannot honestly be called Hostinger managed Node.js-compatible. The production path is to migrate the backend to Node.js while keeping the frontend unchanged, move persistence to Supabase, and use Supabase Auth/Storage. No VPS is required or recommended.

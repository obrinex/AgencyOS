# API Inventory

All current routes are FastAPI routes under `/api`. Authentication is cookie/JWT based unless noted as public.

| Area | Methods/routes | Purpose | Auth | Permission | Validation/rate-limit status |
| --- | --- | --- | --- | --- | --- |
| Auth | `POST /api/auth/login`, `/2fa/login`, `/logout`, `/refresh`, `/forgot-password`, `/reset-password`, `/2fa/*`, `GET /api/auth/me` | Login, session, password reset, 2FA | Mixed public/auth | User/self/admin depending route | Pydantic validation; login brute force only |
| AI | `POST /api/ai/chat`, `/summarize-meeting`, `/generate-email`, `/generate-proposal`, `/leads/{id}/draft-reply`, `GET /api/ai/history` | AI assistant/generation | Staff | Staff | Needs quota/rate limits |
| Automations | `GET /api/automations/logs`, `POST /api/automations/cron/reminders`, `/cron/daily` | Logs and stateless scheduled jobs | Staff or cron secret | Staff/cron | Cron secret added |
| Bookings | `/api/bookings/settings`, `/api/public/booking/{slug}/*` | Booking configuration and public booking | Mixed | Staff/public | Needs public rate limits |
| Clients | `GET/POST /api/clients`, `GET/PUT/DELETE /api/clients/{id}`, portal user routes | Client CRM | Staff/admin | Staff/admin | Needs tenant checks |
| CRM | `/api/leads*`, `/api/contacts*`, `/api/webhooks/lead-capture` | Leads, pipeline, contacts | Mixed | Staff/public webhook | Needs tenant checks and webhook rate limits |
| Dashboard | `GET /api/dashboard/stats`, `/activity` | Dashboard metrics | Staff | Staff | Needs pagination/tenant filters |
| Documents | `/api/proposals*`, `/api/contracts*` | Proposals/contracts/PDF/share/sign | Mixed | Staff/client/public token | Needs tenant/resource checks |
| Files | `GET /api/files`, `POST /api/files/upload`, `GET /api/files/{id}/download`, `DELETE /api/files/{id}` | Upload/download/delete | Auth | User/client scoped partly | MIME/path checks added; storage migration required |
| Finance | `/api/invoices*`, `/api/expenses*`, `/api/finance/*` | Invoices, expenses, reports | Staff/admin | Staff/admin | Needs Decimal/minor units |
| Payments | `/api/public/pay/{token}`, `/api/public/cashfree/webhook` | Cashfree links (auto-created) + crypto claims | Public | Public | Webhook is HMAC-verified; unsigned payloads dropped |
| Knowledge | `/api/knowledge*` | Knowledge base | Staff | Staff | Needs tenant checks |
| Lead finder | `/api/leadfinder/*` | AI/external lead discovery | Staff | Staff | Needs quota/rate limits |
| Lead form | `/api/leadform/settings`, `/api/public/leadform/{slug}` | Public lead capture | Mixed | Staff/public | Needs public rate limits |
| Meetings | `/api/meetings*`, `/api/meetings/google/*` | Calendar meetings and Google integration | Staff | Staff | OAuth secrets server-side |
| Notes | `/api/notes*` | User notes | Auth | User | User-scoped, tenant review needed |
| Notifications | `/api/notifications*` | User notifications | Auth | User | User-scoped |
| Portal | `/api/portal/*` | Client portal | Client | Client | Client ownership checks exist in places; tenant review needed |
| Projects/tasks | `/api/projects*`, `/api/tasks*`, `/api/team/utilization`, time/milestones | Projects and tasks | Staff | Staff | Needs tenant checks |
| Public | `/api/public/proposals/{token}`, `/projects/{token}`, `/agreements/{token}/*` | Public shared links | Public token | Token | Token entropy/expiry review needed |
| Search | `GET /api/search` | Global search | Staff | Staff | Needs tenant filtering |
| Settings | `/api/settings/company`, `/team`, `/audit-logs` | Company/team/settings | Staff/admin | Admin for mutating team | Needs agency-scoped RBAC |
| Support | `/api/support*` | Tickets/messages | Staff/client | Role-specific | Needs tenant checks |
| Vault | `/api/vault*` | Password vault | Staff/admin | Staff/admin | Encryption exists; needs tenant RBAC |

## Required route hardening

Every private route must enforce authentication, agency membership, permission, resource ownership, request validation, and a rate-limit category. Current implementation does not consistently enforce agency/resource isolation.

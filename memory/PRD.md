# AgencyOS — Product Requirements Document

## Original Problem Statement
Build a production-ready SaaS "AgencyOS" for an AI Automation Agency (Obrinex) — a complete
Agency Operating System replacing HubSpot, ClickUp, Notion, Stripe Dashboard, Google Calendar,
accounting software, client portals and PM tools in one platform. Requested stack: Next.js 15 +
Prisma + PostgreSQL + Supabase + Auth.js. **Adapted stack** (platform constraint): React +
FastAPI + MongoDB, same UX/feature target. Full spec covers CRM, Client Management, Client
Portal, Projects, Tasks, Finance/Invoices, Proposals, Contracts, Support Desk, Knowledge Base,
Password Vault, Files, Automation Center, Lead Capture, AI Assistant, Analytics, Notifications,
Integrations, Global Search, Command Palette, Reports, Settings, RBAC/2FA/Audit security.

## Design System
Obrinex monochrome brand: Ink Black `#131315` bg, Signal White `#F4F4F5` text, Carbon/Graphite/Ash
neutrals, Archivo (headings), Space Mono (tags/meta/timestamps). Semantic accents: success (green),
warning (amber), danger (red), info (blue) for status badges only. Dark mode only. Guidelines
stored at `/app/design_guidelines.json`.

## Architecture
- Backend: FastAPI (`/app/backend`), modular routers in `backend/routers/*` (auth, crm, clients,
  portal, projects, finance, documents, support, knowledge, vault, files, notifications,
  dashboard, search, ai, settings, meetings, automations). Shared: `database.py` (Mongo helpers,
  `serialize_doc`), `auth_utils.py` (JWT cookies, RBAC deps, 2FA/TOTP, brute-force lockout, audit
  log), `automation_engine.py` (Won-deal + meeting-booked automations), `seed.py` (admin bootstrap).
- Frontend: React (CRA) + Tailwind + shadcn/ui + Framer Motion + Recharts + cmdk command palette.
  `contexts/AuthContext.jsx`, `components/layout/{Sidebar,Topbar,AppLayout,PortalLayout}.jsx`,
  `components/{CommandPalette,AIAssistant,StatusBadge,EmptyState,DatePicker}.jsx`, pages under
  `pages/*` (staff) and `pages/portal/*` (client-restricted).
- DB: MongoDB collections — users, leads, lead_activities, contacts, clients, projects, tasks,
  milestones, invoices, expenses, payment_transactions, proposals, contracts, tickets,
  kb_articles, vault_entries, files, notifications, audit_logs, automation_logs, meetings,
  company_settings, counters, login_attempts, password_reset_tokens, ai_chat_messages.

## Roles
- **admin**: full access.
- **team_member**: staff access (no team management/vault delete/audit logs).
- **client**: portal-only, strictly scoped to own `client_id` via `/api/portal/*` + ownership
  checks on shared endpoints (invoices, files, tickets).

## What's Been Implemented (as of 2026-07-05)
- Auth: JWT httpOnly cookies (access+refresh), TOTP 2FA (setup/enable/disable/login-verify),
  brute-force lockout (email-keyed), audit logging, bcrypt hashing, forgot/reset password.
- CRM: 11-stage Kanban pipeline w/ drag-and-drop, lead detail w/ timeline/notes, contacts CRUD,
  lead-capture webhook.
- **Won-deal automation**: auto-creates Client + Onboarding Project + default tasks + draft
  Invoice + onboarding checklist + activity/notification/automation-log entries.
- Client Management: client profile (projects/invoices/contacts/tickets/contracts/checklist),
  Portal account provisioning (temp password shown once).
- Client Portal: overview, projects, invoices (+ Stripe Pay Now), contracts, files, support
  tickets — fully isolated from agency data via RBAC.
- Projects/Tasks: Kanban+List views, task Kanban per-project, milestones, budget/cost/profit,
  My Tasks/Team Tasks.
- Finance: revenue/expense/MRR/ARR/margin KPIs, revenue trend chart, expenses CRUD.
- Invoices: create/send/list, Stripe Checkout integration (test key), payment polling + webhook.
- Proposals: CRUD + AI-generated drafts (streaming) + version history.
- Contracts: CRUD + status/renewal tracking.
- Support Desk: tickets w/ threaded messages (staff + client reply flows).
- Knowledge Base: categorized articles (wiki/prompt/automation/SOP/docs/templates).
- Password Vault: Fernet-encrypted secrets, reveal-on-demand + audit log.
- Files: upload/download/delete (local disk storage + Mongo metadata).
- Automation Center: automation run logs (deal-won, meeting-booked) with step timelines.
- Analytics: lead sources, project status distribution, client LTV charts.
- AI Assistant: SSE-streaming chat (Emergent LLM key, gpt-5.4) w/ CRM context, + generate-email/
  summarize-meeting/generate-proposal endpoints.
- Global Search + Command Palette (Cmd/Ctrl+K), Notifications bell, Settings (company, team
  invite, 2FA, audit logs).
- Fixed in testing: Stripe redirect (FRONTEND_URL not request Origin), brute-force IP-proxy bug,
  `/settings/team` RBAC leak, Command Palette cmdk filter conflict, Login render warning, Tasks
  assignee defaulting, native date inputs → shadcn Calendar/Popover DatePicker.

## Explicitly Deferred (Phase 2 — not built yet)
- Gantt/Timeline project views (Kanban/List/Calendar shipped; Gantt not built).
- E-signatures for proposals/contracts (status tracking exists, no signature capture).
- Real email delivery — Resend not configured (no API key provided); emails are logged to
  backend console only (**MOCKED**).
- Live Google Calendar/Meet, Zoom, Microsoft Teams, Calendly OAuth sync (meetings are tracked
  internally only).
- Multi-channel Communication Hub (Slack/Discord/WhatsApp Business/Telegram/call logs) — only
  in-app notifications + ticket threads exist.
- CSV import for leads, PDF export for invoices/reports.
- n8n/Zapier/Make native connectors (generic `/api/webhooks/lead-capture` exists).
- Custom domain/branding theming UI beyond company name/currency.
- Cascade delete of dependent records when a client is removed (data-integrity nice-to-have).

## Test Credentials
See `/app/memory/test_credentials.md` (admin@obrinex.com / AgencyOS@2026). Team/client portal
accounts are generated dynamically via Settings/Client Detail with temp passwords shown once.

## Next Action Items / Backlog
- P0: None blocking — core E2E flows verified via 2 testing rounds (regression fixes confirmed).
- P1: Resend email integration (needs user's Resend API key) to stop console-mocking emails;
  Gantt/Timeline project view; e-signature for contracts/proposals.
- P2: Google Calendar/Zoom/Meet OAuth sync; Slack/WhatsApp/Telegram channels; CSV import; PDF
  export; n8n/Zapier native connectors; cascade-delete integrity job.

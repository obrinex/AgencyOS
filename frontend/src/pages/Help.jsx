import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import {
  LayoutDashboard, KanbanSquare, Users, FileText, Building2, FolderKanban, CheckSquare,
  LifeBuoy, DollarSign, Receipt, FileSignature, BookOpen, Lock, FolderOpen, StickyNote,
  Zap, BarChart3, Settings as SettingsIcon, HelpCircle, Search, CalendarDays, Sparkles, MessageCircle,
} from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { Input } from "@/components/ui/input";
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const HELP_SECTIONS = [
  {
    category: "Overview",
    items: [
      {
        icon: LayoutDashboard, title: "Dashboard",
        description: "Your command center — a live snapshot of revenue, pipeline, tasks and projects.",
        steps: [
          "KPI cards (Revenue, MRR, ARR, Profit, Outstanding, Pipeline Value) update automatically as invoices, leads and expenses change — all shown in your company's base currency.",
          "Use the Sales Funnel chart to see how many leads sit in each pipeline stage.",
          "The Revenue Trend chart tracks paid invoices month over month.",
          "Today's Tasks and Upcoming Meetings widgets pull directly from Tasks and Meetings — click 'All' to jump to the full list.",
          "Use the quick-action buttons (New Lead / New Invoice) to skip straight into creation flows.",
        ],
      },
    ],
  },
  {
    category: "Sales",
    items: [
      {
        icon: KanbanSquare, title: "Pipeline (CRM)",
        description: "Track every lead from first contact to closed deal across an 11-stage Kanban board.",
        steps: [
          "Drag a lead card between stage columns to update its status — dropping into 'Won' auto-creates a Client, onboarding Project, default tasks and a draft Invoice.",
          "Click a lead card to open its detail page: log notes, view the activity timeline, and edit deal value.",
          "New leads can be added manually, via 'Import CSV' (needs a 'company' column; website/industry/revenue/etc. are optional), or captured automatically via the `/api/webhooks/lead-capture` endpoint.",
        ],
      },
      {
        icon: Users, title: "Contacts",
        description: "A directory of individual people linked to your leads and clients.",
        steps: [
          "Add a contact and link them to a company/client so their details surface on the Client Detail page.",
          "Use Contacts to keep track of decision-makers separate from the company record.",
        ],
      },
      {
        icon: FileText, title: "Proposals",
        description: "Draft, send and track sales proposals — including AI-assisted drafting.",
        steps: [
          "Create a proposal and use 'Generate with AI' to produce a first draft based on the lead context.",
          "Every save creates a version in the history so you can compare edits over time.",
          "Share the public link (`/proposal/:token`) with a prospect — no login required. They can Accept or Decline and type their name/email as a lightweight signature.",
        ],
      },
    ],
  },
  {
    category: "Delivery",
    items: [
      {
        icon: Building2, title: "Clients",
        description: "Every won deal becomes a Client record with its own workspace.",
        steps: [
          "Open a client to see Onboarding checklist, Projects, Invoices, Contacts, Tickets and Contracts in one place.",
          "Use 'Create Portal Access' to generate a login for your client so they can log into their own restricted Client Portal.",
          "Revenue and Outstanding figures shown here are always converted to your base currency automatically.",
        ],
      },
      {
        icon: FolderKanban, title: "Projects",
        description: "Manage delivery work with Kanban, List or Gantt/Timeline views.",
        steps: [
          "Switch views using the toggle at the top of the Projects page.",
          "Track budget vs. cost to see project profitability, and set milestones to mark key delivery dates.",
          "Each project can have its own task board — click into a project to manage its tasks directly.",
        ],
      },
      {
        icon: CheckSquare, title: "Tasks",
        description: "Your personal and team-wide to-do list, organized by project or standalone.",
        steps: [
          "Use 'My Tasks' to see only what's assigned to you, or 'Team Tasks' for a full view.",
          "Drag tasks across status columns (To Do / In Progress / Done) on the Kanban view.",
          "Set due dates — anything due today automatically appears on your Dashboard.",
        ],
      },
      {
        icon: LifeBuoy, title: "Support Desk",
        description: "A shared ticketing system for client support requests.",
        steps: [
          "Open a ticket to reply in a threaded conversation — clients can reply too from their Portal.",
          "Update ticket status (open/pending/resolved/closed) as you work through requests.",
        ],
      },
      {
        icon: CalendarDays, title: "Meetings",
        description: "Schedule meetings and optionally two-way sync with Google Calendar.",
        steps: [
          "Click 'Connect' under Google Calendar to link your Google account (needs Calendar API credentials set up by an admin).",
          "Once connected, any meeting you create here is pushed to your primary Google Calendar automatically, and deleting it here removes the Google event too.",
          "Click 'Sync Now' to pull existing events from your Google Calendar into AgencyOS.",
          "'New Meeting' works even without Google connected — it just stays internal to AgencyOS.",
        ],
      },
    ],
  },
  {
    category: "Finance",
    items: [
      {
        icon: DollarSign, title: "Finance",
        description: "Revenue, expenses, profit & multi-currency expense tracking.",
        steps: [
          "All totals (Revenue, Profit, MRR, ARR, etc.) are shown in your base currency (INR by default, set in Settings → Company).",
          "Click 'Add Expense' to log a cost — choose a Currency (INR or USD). If you pick USD, enter a Conversion Rate (how many ₹ per $1) so the amount is correctly converted into base currency for your totals.",
          "Every expense also needs a Type: Personal Withdrawal (money you took out personally), Business Expense (a real cost of running the agency), or Unclassified (sort it later).",
          "The Expense Breakdown pie chart groups all spending by type so you can see how much is personal vs. business at a glance.",
          "Click 'Download Report' to export a PDF summary of all key finance metrics and the expense breakdown.",
        ],
      },
      {
        icon: Receipt, title: "Invoices",
        description: "Create, send and collect payment on client invoices.",
        steps: [
          "New Invoice lets you pick a Currency and Conversion Rate the same way as Expenses — the invoice total is stored in its own currency, but rolls up into your base-currency reports automatically.",
          "Use 'Send to Client' to email the invoice — it also becomes visible in the Client Portal.",
          "When a client clicks 'Click to Pay', a payment request is created for your team. You can attach a payment link from the Dashboard and it will be emailed to the client.",
          "Click the download icon on any invoice row (or 'Download PDF' on the invoice detail page) to export it as a PDF.",
        ],
      },
      {
        icon: FileSignature, title: "Contracts",
        description: "Track signed agreements per client, with renewal dates.",
        steps: [
          "Mark a contract as signed yourself, or have the client sign it from their Portal (typed-name signature).",
          "Set renewal/expiry dates to keep track of upcoming contract end dates.",
        ],
      },
    ],
  },
  {
    category: "Resources",
    items: [
      {
        icon: BookOpen, title: "Knowledge Base",
        description: "Your team's internal wiki — SOPs, prompts, templates and docs.",
        steps: ["Categorize articles as wiki / prompt / automation / SOP / docs / templates for easy filtering."],
      },
      {
        icon: Lock, title: "Password Vault",
        description: "Securely store shared credentials (client logins, API keys, etc.).",
        steps: [
          "Secrets are encrypted at rest — click 'Reveal' to decrypt on demand (each reveal is audit-logged for security).",
        ],
      },
      {
        icon: FolderOpen, title: "Files",
        description: "Upload and share files linked to clients or projects.",
        steps: ["Files uploaded here are also visible to clients in their Portal if linked to their account."],
      },
      {
        icon: StickyNote, title: "Notes",
        description: "A private scratchpad only you can see — not shared with your team.",
        steps: [
          "Click 'New Note' to jot something down. Give it a title, color-code it, and it saves instantly.",
          "Pin important notes to keep them at the top of the list.",
          "Click any note card to edit or delete it.",
        ],
      },
    ],
  },
  {
    category: "System",
    items: [
      {
        icon: Zap, title: "Automations",
        description: "See a log of every automated workflow that has fired (e.g. deal-won, meeting-booked).",
        steps: ["Each run shows a step-by-step timeline so you can debug what happened automatically."],
      },
      {
        icon: BarChart3, title: "Analytics",
        description: "Deeper reporting across sales, revenue, clients and projects.",
        steps: ["View lead sources, project status distribution and client lifetime value charts."],
      },
      {
        icon: SettingsIcon, title: "Settings",
        description: "Company profile, team management, security and audit logs.",
        steps: [
          "Company tab: set your company name and base Currency (INR/USD) — this is what all Dashboard/Finance totals aggregate to.",
          "Team tab: invite team members — a temporary password is generated once, share it securely.",
          "Security tab: enable Two-Factor Authentication (TOTP) for your own account.",
          "Audit Logs (admin only): a full history of sensitive actions across the platform.",
        ],
      },
    ],
  },
];

export default function Help() {
  const [query, setQuery] = useState("");
  const { openAssistant } = useOutletContext();

  const guideSuggestions = [
    "What should I check every morning on the dashboard?",
    "How do I create and send an invoice?",
    "How does moving a lead to Won work?",
    "Which setup items should I finish before hosting?",
  ];

  const askGuide = (prompt = "Help me understand how to use this dashboard. Start with the most important modules and where I should click for common tasks.") => {
    openAssistant({ mode: "guide", prompt, suggestions: guideSuggestions });
  };

  const filtered = HELP_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter(
      (i) => !query || i.title.toLowerCase().includes(query.toLowerCase()) || i.description.toLowerCase().includes(query.toLowerCase())
    ),
  })).filter((section) => section.items.length > 0);

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6" data-testid="help-page">
      <PageHeader
        title="Help & How to Use"
        description="A quick guide to every module in AgencyOS"
        actions={
          <Button data-testid="help-ai-guide-btn" size="sm" className="gap-1.5" onClick={() => askGuide()}>
            <Sparkles className="h-3.5 w-3.5" /> Ask Guide AI
          </Button>
        }
      />

      <Card className="p-4 bg-surface-1 border-white/10" data-testid="dashboard-guide-ai-card">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-2 border border-white/10">
              <MessageCircle className="h-4 w-4 text-graphite" />
            </div>
            <div>
              <p className="font-display text-sm font-semibold">Dashboard Guide AI</p>
              <p className="mt-1 text-sm text-graphite">Ask where a feature lives, what a metric means, or what steps to take next.</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button data-testid="guide-ai-startup-check-btn" size="sm" variant="outline" className="border-white/10" onClick={() => askGuide("Walk me through the dashboard checks I should do before starting work today.")}>Daily check</Button>
            <Button data-testid="guide-ai-hosting-check-btn" size="sm" variant="outline" className="border-white/10" onClick={() => askGuide("What should I verify in AgencyOS before hosting this dashboard publicly?")}>Hosting check</Button>
          </div>
        </div>
      </Card>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-graphite" />
        <Input
          data-testid="help-search-input"
          placeholder="Search modules (e.g. invoices, notes, finance)..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="pl-9 bg-surface-1 border-white/10"
        />
      </div>

      {filtered.length === 0 && (
        <Card className="p-6 bg-surface-1 border-white/10 text-center text-sm text-graphite" data-testid="help-empty-state">
          <HelpCircle className="h-5 w-5 mx-auto mb-2 text-graphite" />
          No modules match "{query}"
        </Card>
      )}

      {filtered.map((section) => (
        <div key={section.category}>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite mb-2">{section.category}</p>
          <Card className="bg-surface-1 border-white/10 px-4" data-testid={`help-section-${section.category.toLowerCase()}`}>
            <Accordion type="single" collapsible>
              {section.items.map((item) => (
                <AccordionItem key={item.title} value={item.title} className="border-white/10" data-testid={`help-item-${item.title.toLowerCase().replace(/\s+/g, "-")}`}>
                  <AccordionTrigger className="hover:no-underline">
                    <span className="flex items-center gap-2.5">
                      <item.icon className="h-4 w-4 text-graphite shrink-0" />
                      <span className="text-left">
                        <span className="block font-medium">{item.title}</span>
                        <span className="block text-xs text-graphite font-normal">{item.description}</span>
                      </span>
                    </span>
                  </AccordionTrigger>
                  <AccordionContent>
                    <ul className="space-y-1.5 pl-7 list-disc text-ash">
                      {item.steps.map((s, i) => <li key={i} className="text-sm">{s}</li>)}
                    </ul>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </Card>
        </div>
      ))}
    </div>
  );
}

import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import {
  LayoutDashboard, KanbanSquare, Users, FileText, Building2, FolderKanban, CheckSquare,
  LifeBuoy, DollarSign, Receipt, FileSignature, BookOpen, Lock, FolderOpen, StickyNote,
  Zap, BarChart3, Settings as SettingsIcon, HelpCircle, Search, CalendarDays, Sparkles, MessageCircle,
  Bot, Cpu, Database, Megaphone, Inbox, Send,
} from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { Input } from "@/components/ui/input";
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const HELP_SECTIONS = [
  {
    // First on purpose: it is the part of the app people have the fewest
    // existing mental models for, so it needs explaining the most.
    category: "AI Agents",
    items: [
      {
        icon: Bot, title: "What the AI actually is",
        description: "Plain-English explanation of agents, assistants, and what is running behind the scenes.",
        steps: [
          "There are two kinds of AI here. An **assistant** waits for you to ask — you press a button, it writes something, you read it. The AI Assistant panel, the email writer and the proposal writer are all assistants.",
          "An **agent** works on its own schedule. Nobody presses a button. It wakes up every few minutes, checks whether it has anything to do, does it, and records what happened. The nine AI SDR agents are all of this kind.",
          "That difference is the whole reason for the Agent Monitor. An assistant that fails tells you immediately, because you are sat there waiting. An agent that fails does so quietly at 3am, so it needs somewhere to be watched.",
          "Every agent has a spending limit and a time limit. If a job costs more or takes longer than its limit, it is stopped rather than allowed to run away. You can see both on the Agent Monitor.",
          "Not every agent uses AI. Website Audits, scoring, sending and meeting proposals are all ordinary code — deliberately. A language model is used for judgement and for writing, never for facts the system already knows. A made-up meeting time is worse than a plainly-worded one.",
          "Nothing runs unless the AI SDR module is switched on, and nothing is emailed unless three separate switches are all on. Off is the default at every level.",
        ],
      },
      {
        icon: Cpu, title: "Agent Monitor",
        description: "One page showing every AI capability in the app — what it does, whether it is working, and what it costs.",
        steps: [
          "Open this first when something AI-related seems broken. It lists all 15 capabilities grouped by what they are for, whether or not they belong to the AI SDR.",
          "Each card shows a success rate and how many times it has run. 'No runs yet' means exactly that — it has never been used, which is not the same as broken.",
          "The Spend figure is an estimate based on token counts. It exists so a runaway loop shows up as money rather than as a surprise bill.",
          "'Queued jobs' is the work waiting to happen. If that number climbs and never falls, the scheduler has stopped — there is a warning banner for this on the Agents page.",
          "Click any recent run to open it: the exact input, the exact output, which AI provider answered, how long it took, and any guardrail that fired. Personal data is removed before a run is stored.",
          "AI providers are listed at the bottom with the order they are tried in. All are free tiers. If one refuses or rate-limits, the next one is tried automatically — that fallback is what makes free plans usable rather than a demo.",
        ],
      },
      {
        icon: Sparkles, title: "AI Lead Finder",
        description: "Find real businesses anywhere in the world and let AI write the pitch. Free — no API key needed.",
        steps: [
          "Pick a business type and a city, then press 'Find Leads'. It searches OpenStreetMap, the same open map data behind many map apps. There is no cost and no key.",
          "Results are real businesses with real addresses and, where published, phone numbers and websites.",
          "A business with 'NO WEBSITE — opportunity' is exactly what it sounds like — usually your best prospect.",
          "Press 'AI Pitch' on any result. It suggests which of your services fit, explains why, and drafts both a cold email and a shorter WhatsApp message. You can copy either.",
          "'Add to Pipeline with this pitch' creates a CRM lead with the drafts attached, so you are not starting from a blank page later.",
          "This is the hands-on tool: you choose each business and press each button. If you want that to happen on its own, that is the AI SDR below.",
        ],
      },
      {
        icon: Bot, title: "AI SDR — what it is",
        description: "The autonomous version: finds businesses, researches them, writes emails, sends them, and handles the replies.",
        steps: [
          "Think of it as the AI Lead Finder with nobody pressing the buttons. It runs on a schedule and does the whole sequence itself.",
          "The order it works in: find businesses → fill in missing details → check their website for gaps → research them → score them 0-100 → decide if they are worth contacting → write an email → wait for your approval → send it inside their business hours → read the reply.",
          "You stay in control at the point that matters. By default every email waits for you to approve it, and you can edit the words before it goes.",
          "It is designed around not sending. If someone replies, unsubscribes, bounces, or their deal closes, the sequence stops — and that is checked twice, once when the email is written and again just before it goes out, because things change in between.",
          "Start in Simulate mode. The entire pipeline runs and stops one step before the send, marking the message as a rehearsal. Use it to read what the AI writes before any stranger does.",
          "The switches, in the order they must be on: Module (AI SDR page) → Email channel (same page) → LIVE mode (Outreach page). All three are off when the system is first installed.",
        ],
      },
      {
        icon: Database, title: "AI SDR — Lead Database",
        description: "Every business the AI has found or you have imported, with its score and research.",
        steps: [
          "'Discover' searches OpenStreetMap for businesses by type and city. 'Import CSV' takes a list you already have — it only needs one column named Company, Business or Name.",
          "In the Discover dialog, switch on 'Also create CRM leads' — it is off by default, and without it you get businesses but nothing that can be contacted.",
          "Click any lead, then 'Enrich, audit & score'. This is the step people miss: only leads it marks as **qualified** can go into a campaign. Skip it and your campaign will have nothing to send to.",
          "The score is not a guess by an AI — it is a fixed calculation, and the breakdown explains every point. If you disagree with a score, you can see exactly which rule caused it.",
          "The website audit checks 19 things, but six of them cannot be measured without a full browser, which this cannot run. Those are reported as 'unmeasured' rather than as a pass — the system never claims to know something it does not.",
        ],
      },
      {
        icon: Megaphone, title: "AI SDR — Campaigns & Outreach",
        description: "A sequence of emails pointed at a set of qualified leads, with your approval in the middle.",
        steps: [
          "A campaign is a name plus a sequence. Each step is an instruction to the writer, not a template — so every email is written for that specific business rather than filled into a form.",
          "'I approve each email' is the default and the right starting point. 'Send automatically' removes you from the loop entirely — only use it once you trust the copy.",
          "Leads are attached when you press Launch, not when you create the campaign. Only qualified leads appear in that list.",
          "On the Outreach page, drafts wait under 'Approval queue'. Click one to read it. 'Facts this draft is grounded in' shows what it actually knows about that business — everything it claims must come from that list.",
          "You can edit the subject and body before approving, and your edits are what gets sent.",
          "'Reject, rewrite' throws the draft away and writes a fresh one. 'Reject, stop sequence' removes that lead from the campaign entirely.",
          "Approved emails do not send immediately — they are scheduled for the recipient's next working hours, in their timezone, with a small random delay so a batch does not look machine-generated.",
        ],
      },
      {
        icon: Inbox, title: "AI SDR — Inbox",
        description: "Replies, matched back to the email that earned them and sorted into what needs you.",
        steps: [
          "It checks your mailbox every few minutes and reads new replies. It never marks anything as read — you can keep using that mailbox normally and unread mail stays unread.",
          "Each reply is sorted: interested, not now, an objection, wrong person, an unsubscribe request, a bounce, or a machine.",
          "The important distinction is human versus machine. An out-of-office is **not** a reply — treating one as interest would stop your sequence permanently while the person never even read the email. Out-of-office pushes the next touch out by a week instead.",
          "The Inbox opens on 'Needs you' rather than everything, because it is a work queue and not an archive.",
          "'Unmatched' means the reply could not be tied to any campaign — usually because the sender's email client stripped the tracking headers. Somebody answered and is waiting, so those get a banner rather than a row that scrolls past.",
          "If it gets a category wrong, change it in the reply's panel. That re-applies for real — correcting an 'interested' to an out-of-office actually restarts the stopped sequence.",
        ],
      },
      {
        icon: Send, title: "AI SDR — Deliverability",
        description: "Whether your email will actually arrive. The least glamorous page and the one that decides everything.",
        steps: [
          "A sending identity is the address emails come from. It cannot send until SPF, DKIM and DMARC all pass — those are DNS records proving the mail is really from you.",
          "'Check DNS' tests all four records and tells you which one is wrong. Do this before activating anything.",
          "Warm-up is the three-week ramp from about 5 emails a day up to your target. This is not a limitation of the software — it is how Gmail and Outlook decide to trust a new domain. Sending 200 on day one gets you filtered for months.",
          "'Volume & quota' is where you set how many new leads to start per day. New leads per day is not the same as emails per day: at 3 touches each, 30 leads a day means about 2,700 emails a month.",
          "'Test a send' is the most useful button on this page. Enter any address and it shows you every gate in order and exactly which one is blocking. Use it whenever something will not send and you cannot work out why.",
          "The suppression list is people who must never be contacted again — unsubscribes, bounces, complaints. It is permanent by design and is checked before every single send.",
        ],
      },
      {
        icon: MessageCircle, title: "Getting help from the AI",
        description: "Two different assistants, for two different kinds of question.",
        steps: [
          "The **AI Assistant** button in the top bar answers questions about your actual data — 'which deals are most likely to close', 'what is outstanding this month'. It can see your leads, clients and invoices.",
          "The **Guide AI** on this page answers questions about how to use the dashboard — where a feature lives, what a metric means, what to do next. Use the button at the top of this page.",
          "Both give short, practical answers. If one starts guessing about a feature that does not exist, tell whoever maintains the system — that is a gap in what it has been told, not something to work around.",
          "Neither can change anything. They read and explain; every action is still yours to take.",
        ],
      },
      {
        icon: Zap, title: "What is coming next",
        description: "Built but waiting on approvals, and deliberately not built yet.",
        steps: [
          "**WhatsApp** — the system already ranks WhatsApp above email for India, and the sequencing does not assume email. What is missing is Meta's business verification and per-template approval, which takes weeks. That clock has to be started before any code matters.",
          "**Meeting booking** — built. Once someone replies with interest, it can propose call times in their timezone and link to your booking page. It offers times rather than booking them itself, because a misread date is a missed meeting and the booking page already checks for clashes.",
          "**Competitor analysis** — needs a web-search provider to be configured. None is at the moment.",
          "**A/B testing of email copy** — deliberately not built. At 30 leads a day it would take months to produce a result you could trust, and a half-significant result is worse than none because people act on it.",
        ],
      },
    ],
  },
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
          "Clients pay themselves: opening an invoice's payment page creates a Cashfree link automatically (INR and USD) for card, UPI or net banking. USD invoices lead with crypto since it avoids FX spread and card fees. Payments are auto-captured and the invoice marks itself paid — you just get the notification.",
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

/** Renders **bold** inside a help step. Deliberately tiny — the steps are
 *  hand-written prose, not user input, so a full markdown parser would be a
 *  dependency bought for one piece of syntax. */
function emphasise(text) {
  return String(text).split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={i} className="text-foreground font-semibold">{part.slice(2, -2)}</strong>
      : part
  );
}

export default function Help() {
  const [query, setQuery] = useState("");
  const { openAssistant } = useOutletContext();

  const guideSuggestions = [
    "What is the difference between AI Lead Finder and the AI SDR?",
    "How do I try the AI SDR without emailing anyone?",
    "Why is my campaign not sending anything?",
    "What should I check every morning on the dashboard?",
    "How do I create and send an invoice?",
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
            <Button data-testid="guide-ai-sdr-btn" size="sm" variant="outline" className="border-white/10" onClick={() => askGuide("Explain the AI SDR in simple terms. What does it do on its own, where do I stay in control, and how do I try it without emailing anyone?")}>Explain the AI</Button>
            <Button data-testid="guide-ai-notsending-btn" size="sm" variant="outline" className="border-white/10" onClick={() => askGuide("My AI SDR campaign is not sending anything. Walk me through every switch and setting that could be blocking it, in the order I should check them.")}>Nothing is sending</Button>
            <Button data-testid="guide-ai-startup-check-btn" size="sm" variant="outline" className="border-white/10" onClick={() => askGuide("Walk me through the dashboard checks I should do before starting work today.")}>Daily check</Button>
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
                      {item.steps.map((s, i) => <li key={i} className="text-sm">{emphasise(s)}</li>)}
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

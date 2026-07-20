import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, KanbanSquare, Users, Building2, FolderKanban, CheckSquare,
  DollarSign, Receipt, FileText, FileSignature, LifeBuoy, BookOpen, Lock,
  FolderOpen, Zap, BarChart3, Settings, ChevronsLeft, ChevronsRight, StickyNote, HelpCircle, CalendarDays, Sparkles, Mail, Link2, Bot, Database, Cpu, ScanSearch, Send, Megaphone, Inbox, MailCheck,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";

export const NAV_SECTIONS = [
  {
    label: "Overview",
    items: [{ to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, testId: "nav-dashboard" }],
  },
  {
    // Everything AI-driven lives together, whatever it is used for. The
    // monitor is first because it is the way in: it shows every capability
    // in the app, not just lead generation.
    label: "AI Agents",
    items: [
      { to: "/ai-agents", label: "Agent Monitor", icon: Cpu, testId: "nav-ai-agents" },
      { to: "/ai-sdr", module: "ai_sdr", label: "AI SDR", icon: Bot, testId: "nav-ai-sdr" },
      { to: "/ai-sdr/leads", module: "ai_sdr", label: "Lead Database", icon: Database, testId: "nav-sdr-leads" },
      { to: "/lead-finder", module: "crm", label: "AI Lead Finder", icon: Sparkles, testId: "nav-lead-finder" },
      { to: "/ai-sdr/campaigns", module: "ai_sdr", label: "Campaigns", icon: Megaphone, testId: "nav-sdr-campaigns" },
      // Outreach is the approval queue (outbound), so the inbox icon belongs
      // to the actual inbox sitting next to it.
      { to: "/ai-sdr/outreach", module: "ai_sdr", label: "Outreach", icon: MailCheck, testId: "nav-sdr-outreach" },
      { to: "/ai-sdr/inbox", module: "ai_sdr", label: "Inbox", icon: Inbox, testId: "nav-sdr-inbox" },
      { to: "/ai-sdr/audits", module: "ai_sdr", label: "Website Audits", icon: ScanSearch, testId: "nav-sdr-audits" },
      { to: "/ai-sdr/deliverability", module: "ai_sdr", label: "Deliverability", icon: Send, testId: "nav-sdr-deliverability" },
    ],
  },
  {
    label: "Sales",
    items: [
      { to: "/crm", module: "crm", label: "Pipeline", icon: KanbanSquare, testId: "nav-crm" },
      { to: "/contacts", module: "crm", label: "Contacts", icon: Users, testId: "nav-contacts" },
      { to: "/emails", module: "emails", label: "Emails", icon: Mail, testId: "nav-emails" },
      { to: "/proposals", module: "documents", label: "Proposals", icon: FileText, testId: "nav-proposals" },
    ],
  },
  {
    label: "Delivery",
    items: [
      { to: "/clients", module: "clients", label: "Clients", icon: Building2, testId: "nav-clients" },
      { to: "/projects", module: "projects", label: "Projects", icon: FolderKanban, testId: "nav-projects" },
      { to: "/tasks", module: "projects", label: "Tasks", icon: CheckSquare, testId: "nav-tasks" },
      { to: "/support", module: "support", label: "Support Desk", icon: LifeBuoy, testId: "nav-support" },
      { to: "/calendar", module: "calendar", label: "Calendar", icon: CalendarDays, testId: "nav-calendar" },
    ],
  },
  {
    label: "Finance",
    items: [
      { to: "/finance", module: "finance", label: "Finance", icon: DollarSign, testId: "nav-finance" },
      { to: "/invoices", module: "finance", label: "Invoices", icon: Receipt, testId: "nav-invoices" },
      { to: "/payment-links", module: "finance", label: "Payment Links", icon: Link2, testId: "nav-payment-links" },
      { to: "/contracts", module: "documents", label: "Contracts", icon: FileSignature, testId: "nav-contracts" },
    ],
  },
  {
    label: "Resources",
    items: [
      { to: "/knowledge-base", module: "knowledge", label: "Knowledge Base", icon: BookOpen, testId: "nav-kb" },
      { to: "/vault", module: "vault", label: "Password Vault", icon: Lock, testId: "nav-vault" },
      { to: "/files", module: "files", label: "Files", icon: FolderOpen, testId: "nav-files" },
      { to: "/notes", module: "notes", label: "Notes", icon: StickyNote, testId: "nav-notes" },
    ],
  },
  {
    label: "System",
    items: [
      { to: "/automations", module: "analytics", label: "Automations", icon: Zap, testId: "nav-automations" },
      { to: "/analytics", module: "analytics", label: "Analytics", icon: BarChart3, testId: "nav-analytics" },
      { to: "/settings", label: "Settings", icon: Settings, testId: "nav-settings" },
      { to: "/help", label: "Help", icon: HelpCircle, testId: "nav-help" },
    ],
  },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const { user } = useAuth();

  // Team members with a restricted permissions list only see their allowed modules.
  const perms = user?.role === "team_member" ? (user?.permissions || []) : [];
  const canSee = (item) => !item.module || perms.length === 0 || perms.includes(item.module);
  const sections = NAV_SECTIONS
    .map((s) => ({ ...s, items: s.items.filter(canSee) }))
    .filter((s) => s.items.length > 0);

  return (
    <aside
      data-testid="main-sidebar"
      className={cn(
        "hidden md:flex flex-col shrink-0 border-r border-white/10 bg-background transition-all duration-200",
        collapsed ? "w-[68px]" : "w-[240px]"
      )}
    >
      <div className="flex h-16 items-center gap-2 px-4 border-b border-white/10">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-foreground text-background font-display font-bold text-sm shrink-0">
          O
        </div>
        {!collapsed && (
          <div className="flex flex-col leading-none overflow-hidden">
            <span className="font-display font-bold text-sm tracking-tight">AgencyOS</span>
            <span className="font-mono text-[10px] text-graphite tracking-wide">OBRINEX</span>
          </div>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto scrollbar-thin py-4 px-2 space-y-5">
        {sections.map((section) => (
          <div key={section.label}>
            {!collapsed && (
              <p className="px-2.5 mb-1.5 font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">{section.label}</p>
            )}
            <div className="space-y-0.5">
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  data-testid={item.testId}
                  className={({ isActive }) =>
                    cn(
                      "group flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors relative",
                      isActive
                        ? "bg-surface-2 text-foreground"
                        : "text-ash hover:bg-surface-1 hover:text-foreground"
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-foreground" />}
                      <item.icon className="h-4 w-4 shrink-0" />
                      {!collapsed && <span className="truncate">{item.label}</span>}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <button
        data-testid="sidebar-collapse-toggle"
        onClick={() => setCollapsed((c) => !c)}
        className="flex items-center justify-center gap-2 h-11 border-t border-white/10 text-graphite hover:text-foreground hover:bg-surface-1 transition-colors text-xs"
      >
        {collapsed ? <ChevronsRight className="h-4 w-4" /> : <><ChevronsLeft className="h-4 w-4" /> Collapse</>}
      </button>
    </aside>
  );
}

export function MobileNav({ open, onOpenChange }) {
  const close = () => onOpenChange(false);
  const { user } = useAuth();

  // Same permission-based filtering as the desktop sidebar.
  const perms = user?.role === "team_member" ? (user?.permissions || []) : [];
  const canSee = (item) => !item.module || perms.length === 0 || perms.includes(item.module);
  const sections = NAV_SECTIONS
    .map((s) => ({ ...s, items: s.items.filter(canSee) }))
    .filter((s) => s.items.length > 0);

  return (
    <div
      data-testid="mobile-nav"
      className={cn(
        "fixed inset-0 z-50 md:hidden transition pointer-events-none",
        open ? "pointer-events-auto" : ""
      )}
      aria-hidden={!open}
    >
      <button
        type="button"
        aria-label="Close navigation"
        onClick={close}
        className={cn(
          "absolute inset-0 bg-black/70 transition-opacity",
          open ? "opacity-100" : "opacity-0"
        )}
      />
      <aside
        className={cn(
          "absolute left-0 top-0 h-full w-[82vw] max-w-[320px] border-r border-white/10 bg-background transition-transform duration-200",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-16 items-center gap-2 px-4 border-b border-white/10">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-foreground text-background font-display font-bold text-sm shrink-0">
            O
          </div>
          <div className="flex flex-col leading-none overflow-hidden">
            <span className="font-display font-bold text-sm tracking-tight">AgencyOS</span>
            <span className="font-mono text-[10px] text-graphite tracking-wide">OBRINEX</span>
          </div>
        </div>

        <nav className="h-[calc(100%-4rem)] overflow-y-auto scrollbar-thin py-4 px-3 space-y-5">
          {sections.map((section) => (
            <div key={section.label}>
              <p className="px-2.5 mb-1.5 font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">{section.label}</p>
              <div className="space-y-0.5">
                {section.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    data-testid={`mobile-${item.testId}`}
                    onClick={close}
                    className={({ isActive }) =>
                      cn(
                        "group flex items-center gap-3 rounded-lg px-2.5 py-2.5 text-sm transition-colors relative",
                        isActive
                          ? "bg-surface-2 text-foreground"
                          : "text-ash hover:bg-surface-1 hover:text-foreground"
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-foreground" />}
                        <item.icon className="h-4 w-4 shrink-0" />
                        <span className="truncate">{item.label}</span>
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
      </aside>
    </div>
  );
}

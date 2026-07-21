import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, KanbanSquare, Users, Building2, FolderKanban, CheckSquare,
  DollarSign, Receipt, FileText, FileSignature, LifeBuoy, BookOpen, Lock,
  FolderOpen, Zap, BarChart3, Settings, ChevronsLeft, ChevronsRight, StickyNote, HelpCircle, CalendarDays, Sparkles, Mail, Link2, Bot, Database, Cpu, ScanSearch, Send, Megaphone, Inbox, MailCheck, ChevronDown, Gauge,
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
    // Everything AI-driven lives together, whatever it is used for.
    //
    // One agent's pages are one collapsible group. That is the whole reason
    // for the nesting: a second and third agent would otherwise turn this
    // section into thirty flat links where nothing indicates which pages
    // belong to which agent. Adding an agent means adding a group here, not
    // rethinking the navigation.
    label: "AI Agents",
    items: [
      // The way in - every capability in the app, not just one agent's.
      { to: "/ai-agents", label: "All Agents", icon: Cpu, testId: "nav-ai-agents" },
    ],
    groups: [
      {
        key: "leadgen",
        label: "Lead Gen Agent",
        icon: Bot,
        items: [
          { to: "/ai-sdr", module: "ai_sdr", label: "Control", icon: Gauge, testId: "nav-ai-sdr" },
          { to: "/ai-sdr/leads", module: "ai_sdr", label: "Lead Database", icon: Database, testId: "nav-sdr-leads" },
          { to: "/lead-finder", module: "crm", label: "Manual Finder", icon: Sparkles, testId: "nav-lead-finder" },
          { to: "/ai-sdr/campaigns", module: "ai_sdr", label: "Campaigns", icon: Megaphone, testId: "nav-sdr-campaigns" },
          // Outreach is the approval queue (outbound), so the inbox icon
          // belongs to the actual inbox sitting next to it.
          { to: "/ai-sdr/outreach", module: "ai_sdr", label: "Outreach", icon: MailCheck, testId: "nav-sdr-outreach" },
          { to: "/ai-sdr/inbox", module: "ai_sdr", label: "Inbox", icon: Inbox, testId: "nav-sdr-inbox" },
          { to: "/ai-sdr/audits", module: "ai_sdr", label: "Website Audits", icon: ScanSearch, testId: "nav-sdr-audits" },
          { to: "/ai-sdr/deliverability", module: "ai_sdr", label: "Deliverability", icon: Send, testId: "nav-sdr-deliverability" },
        ],
      },
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

/** Sections and agent groups the current user may see.
 *
 *  Shared by the desktop sidebar and the mobile drawer - the filtering was
 *  previously written out twice, which is one edit away from the two menus
 *  disagreeing about what a team member can open.
 */
export function visibleSections(user) {
  const perms = user?.role === "team_member" ? (user?.permissions || []) : [];
  const canSee = (item) => !item.module || perms.length === 0 || perms.includes(item.module);
  return NAV_SECTIONS
    .map((section) => ({
      ...section,
      items: (section.items || []).filter(canSee),
      groups: (section.groups || [])
        .map((group) => ({ ...group, items: group.items.filter(canSee) }))
        .filter((group) => group.items.length > 0),
    }))
    .filter((section) => section.items.length > 0 || section.groups.length > 0);
}

/** One nav link. Kept in one place so the active treatment cannot drift
 *  between the sidebar, its collapsed state, and the mobile drawer. */
function NavItem({ item, collapsed = false, indented = false, onNavigate }) {
  return (
    <NavLink
      to={item.to}
      data-testid={item.testId}
      onClick={onNavigate}
      title={collapsed ? item.label : undefined}
      className={({ isActive }) =>
        cn(
          "group flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm relative",
          "transition-colors duration-150",
          indented && !collapsed && "ml-3",
          isActive
            ? "bg-surface-2 text-foreground"
            : "text-ash hover:bg-surface-1 hover:text-foreground"
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-foreground" />
          )}
          <item.icon className="h-4 w-4 shrink-0" />
          {!collapsed && <span className="truncate">{item.label}</span>}
        </>
      )}
    </NavLink>
  );
}

/** One agent's pages, collapsible.
 *
 *  Open by default and remembered per agent, because the common case is
 *  working inside one agent all day; the collapse exists for when there are
 *  several and the list would otherwise be unreadable.
 */
function AgentGroup({ group, collapsed, onNavigate }) {
  const storageKey = `nav-group-${group.key}`;
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem(storageKey) !== "0"; } catch { return true; }
  });

  const toggle = () => {
    setOpen((next) => {
      const value = !next;
      try { localStorage.setItem(storageKey, value ? "1" : "0"); } catch { /* private mode */ }
      return value;
    });
  };

  // Collapsed rail: no room for a group header, so the pages stand alone.
  if (collapsed) {
    return (
      <div className="space-y-0.5">
        {group.items.map((item) => (
          <NavItem key={item.to} item={item} collapsed onNavigate={onNavigate} />
        ))}
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={toggle}
        data-testid={`nav-group-${group.key}`}
        aria-expanded={open}
        className="w-full flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs
                   text-graphite hover:text-foreground transition-colors duration-150"
      >
        <group.icon className="h-3.5 w-3.5 shrink-0" />
        <span className="flex-1 text-left font-medium tracking-tight">{group.label}</span>
        <ChevronDown
          className={cn("h-3.5 w-3.5 shrink-0 transition-transform duration-200",
                        open ? "" : "-rotate-90")}
        />
      </button>
      {open && (
        <div className="mt-0.5 space-y-0.5 border-l border-white/10 ml-3.5 pl-1">
          {group.items.map((item) => (
            <NavItem key={item.to} item={item} onNavigate={onNavigate} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const { user } = useAuth();
  const sections = visibleSections(user);

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
                <NavItem key={item.to} item={item} collapsed={collapsed} />
              ))}
              {(section.groups || []).map((group) => (
                <div key={group.key} className={collapsed ? "" : "pt-1.5"}>
                  <AgentGroup group={group} collapsed={collapsed} />
                </div>
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

  const sections = visibleSections(user);

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
                  <NavItem key={item.to} item={item} onNavigate={close} />
                ))}
                {(section.groups || []).map((group) => (
                  <div key={group.key} className="pt-1.5">
                    <AgentGroup group={group} collapsed={false} onNavigate={close} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </nav>
      </aside>
    </div>
  );
}

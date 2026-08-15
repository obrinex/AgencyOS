import { NavLink } from "react-router-dom";
import {
  BarChart3, BookOpen, Gem, Building2, CalendarDays, CheckSquare, ChevronsLeft, ChevronsRight, DollarSign, FileSignature, FileText, FolderKanban, FolderOpen, HelpCircle, KanbanSquare, LayoutDashboard, LifeBuoy, Link2, Lock, Mail, MessageSquare, Receipt, Settings, Sparkles, StickyNote, Users, Zap,
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
    label: "Sales",
    items: [
      { to: "/crm", module: "crm", label: "Pipeline", icon: KanbanSquare, testId: "nav-crm" },
      { to: "/contacts", module: "crm", label: "Contacts", icon: Users, testId: "nav-contacts" },
      // Moved up from the deleted "AI Agents" section, which is where it
      // used to be nested. The Lead Finder is not an agent - it is a
      // one-shot search - and losing the link with the group it happened to
      // sit in would have hidden a working feature.
      { to: "/lead-finder", module: "crm", label: "Lead Finder", icon: Sparkles, testId: "nav-lead-finder" },
      { to: "/emails", module: "emails", label: "Emails", icon: Mail, testId: "nav-emails" },
      { to: "/proposals", module: "documents", label: "Proposals", icon: FileText, testId: "nav-proposals" },
    ],
  },
  {
    // Its own section rather than a link under Sales. Ten seats and a private
    // room is not a pipeline stage, and burying it in a list of eight made it
    // read like one.
    label: "Founding Circle",
    items: [
      { to: "/founding", module: "crm", label: "Applications", icon: FileText, testId: "nav-founding" },
      { to: "/founding/members", module: "crm", label: "Members", icon: Gem, testId: "nav-founding-members" },
      { to: "/founding/community", module: "crm", label: "Community", icon: MessageSquare, testId: "nav-founding-community" },
    ],
  },
  {
    label: "Delivery",
    items: [
      { to: "/clients", module: "clients", label: "Clients", icon: Building2, testId: "nav-clients" },
      { to: "/projects", module: "projects", label: "Projects", icon: FolderKanban, testId: "nav-projects" },
      { to: "/tasks", module: "projects", label: "Tasks", icon: CheckSquare, testId: "nav-tasks" },
      { to: "/chat", module: "clients", label: "Client Chat", icon: MessageSquare, testId: "nav-chat" },
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
      { to: "/policies", label: "Legal & Policies", icon: FileText, testId: "nav-policies" },
      { to: "/help", label: "Help", icon: HelpCircle, testId: "nav-help" },
    ],
  },
];

/** Sections the current user may see.
 *
 *  Shared by the desktop sidebar and the mobile drawer - the filtering was
 *  previously written out twice, which is one edit away from the two menus
 *  disagreeing about what a team member can open.
 *
 *  Sections used to be able to carry collapsible sub-groups, one per AI agent.
 *  With the agents removed nothing declared one, so the grouping went too.
 */
export function visibleSections(user) {
  const perms = user?.role === "team_member" ? (user?.permissions || []) : [];
  const canSee = (item) => !item.module || perms.length === 0 || perms.includes(item.module);
  return NAV_SECTIONS
    .map((section) => ({ ...section, items: (section.items || []).filter(canSee) }))
    .filter((section) => section.items.length > 0);
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
          "group relative flex items-center gap-3 overflow-hidden rounded-lg px-2.5 py-2 text-sm",
          // Transform as well as colour: the label shifts a couple of pixels
          // toward the pointer, which is the sidebar's version of the site's
          // magnetic controls — enough to feel responsive, far too little to
          // make anything move under your cursor.
          "transition-[color,background-color] duration-200",
          indented && !collapsed && "ml-3",
          isActive
            ? "bg-surface-2 text-foreground"
            : "text-ash hover:bg-surface-1 hover:text-foreground",
        )
      }
    >
      {({ isActive }) => (
        <>
          {/* The active marker grows from the centre rather than appearing.
              scaleY on a positioned hairline animates on the compositor, so
              this costs nothing even with thirty links mounted. */}
          <span
            aria-hidden
            className={cn(
              "absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full bg-foreground",
              "origin-center transition-transform duration-300 ease-out",
              isActive ? "scale-y-100" : "scale-y-0",
            )}
          />
          {/* A very faint wash that sweeps in from the left on hover. This is
              the one place the site's gradient language survives in the tool. */}
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-white/[0.06] to-transparent transition-transform duration-500 ease-out group-hover:translate-x-0"
          />
          <item.icon
            className={cn(
              "relative h-4 w-4 shrink-0 transition-transform duration-300 ease-out",
              "group-hover:scale-110",
              isActive && "text-foreground",
            )}
          />
          {!collapsed && (
            <span className="relative truncate transition-transform duration-300 ease-out group-hover:translate-x-0.5">
              {item.label}
            </span>
          )}
        </>
      )}
    </NavLink>
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
      {/* The mark spins slowly on hover — the same rotating O the website uses
          in OBR<em>I</em>NEX and BO<em>O</em>K A CALL. One shared gesture, and
          the only decorative motion in the whole sidebar. */}
      <div className="group flex h-16 items-center gap-2 px-4 border-b border-white/10">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-foreground font-display text-sm font-bold text-background transition-transform duration-[1200ms] ease-out group-hover:rotate-[360deg]">
          O
        </div>
        {!collapsed && (
          <div className="flex flex-col overflow-hidden leading-none">
            <span className="font-display text-sm font-bold tracking-tight">AgencyOS</span>
            <span className="font-mono text-[10px] tracking-[0.18em] text-graphite">OBRINEX</span>
          </div>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto scrollbar-thin py-4 px-2 space-y-5">
        {sections.map((section) => (
          <div key={section.label}>
            {!collapsed && (
              // Section labels sit against a hairline rather than floating.
              // It is the ledger-rule device from the site's Circle section,
              // and it turns seven loose groups into a structured list.
              <div className="mb-2 flex items-center gap-2 px-2.5">
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
                  {section.label}
                </p>
                <span aria-hidden className="h-px flex-1 bg-white/[0.07]" />
              </div>
            )}
            <div className="space-y-0.5">
              {section.items.map((item) => (
                <NavItem key={item.to} item={item} collapsed={collapsed} />
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
              </div>
            </div>
          ))}
        </nav>
      </aside>
    </div>
  );
}

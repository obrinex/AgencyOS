import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, KanbanSquare, Users, Building2, FolderKanban, CheckSquare,
  DollarSign, Receipt, FileText, FileSignature, LifeBuoy, BookOpen, Lock,
  FolderOpen, Zap, BarChart3, Settings, ChevronsLeft, ChevronsRight, StickyNote, HelpCircle, CalendarDays,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

const NAV_SECTIONS = [
  {
    label: "Overview",
    items: [{ to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, testId: "nav-dashboard" }],
  },
  {
    label: "Sales",
    items: [
      { to: "/crm", label: "Pipeline", icon: KanbanSquare, testId: "nav-crm" },
      { to: "/contacts", label: "Contacts", icon: Users, testId: "nav-contacts" },
      { to: "/proposals", label: "Proposals", icon: FileText, testId: "nav-proposals" },
    ],
  },
  {
    label: "Delivery",
    items: [
      { to: "/clients", label: "Clients", icon: Building2, testId: "nav-clients" },
      { to: "/projects", label: "Projects", icon: FolderKanban, testId: "nav-projects" },
      { to: "/tasks", label: "Tasks", icon: CheckSquare, testId: "nav-tasks" },
      { to: "/support", label: "Support Desk", icon: LifeBuoy, testId: "nav-support" },
      { to: "/meetings", label: "Meetings", icon: CalendarDays, testId: "nav-meetings" },
    ],
  },
  {
    label: "Finance",
    items: [
      { to: "/finance", label: "Finance", icon: DollarSign, testId: "nav-finance" },
      { to: "/invoices", label: "Invoices", icon: Receipt, testId: "nav-invoices" },
      { to: "/contracts", label: "Contracts", icon: FileSignature, testId: "nav-contracts" },
    ],
  },
  {
    label: "Resources",
    items: [
      { to: "/knowledge-base", label: "Knowledge Base", icon: BookOpen, testId: "nav-kb" },
      { to: "/vault", label: "Password Vault", icon: Lock, testId: "nav-vault" },
      { to: "/files", label: "Files", icon: FolderOpen, testId: "nav-files" },
      { to: "/notes", label: "Notes", icon: StickyNote, testId: "nav-notes" },
    ],
  },
  {
    label: "System",
    items: [
      { to: "/automations", label: "Automations", icon: Zap, testId: "nav-automations" },
      { to: "/analytics", label: "Analytics", icon: BarChart3, testId: "nav-analytics" },
      { to: "/settings", label: "Settings", icon: Settings, testId: "nav-settings" },
      { to: "/help", label: "Help", icon: HelpCircle, testId: "nav-help" },
    ],
  },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

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
        {NAV_SECTIONS.map((section) => (
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

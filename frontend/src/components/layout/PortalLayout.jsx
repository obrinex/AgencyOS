import { NavLink, Outlet } from "react-router-dom";
import { LayoutDashboard, FolderKanban, Receipt, FolderOpen, LifeBuoy, FileSignature, LogOut } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/portal", label: "Overview", icon: LayoutDashboard, testId: "portal-nav-overview" },
  { to: "/portal/projects", label: "Projects", icon: FolderKanban, testId: "portal-nav-projects" },
  { to: "/portal/invoices", label: "Invoices", icon: Receipt, testId: "portal-nav-invoices" },
  { to: "/portal/contracts", label: "Contracts", icon: FileSignature, testId: "portal-nav-contracts" },
  { to: "/portal/files", label: "Files", icon: FolderOpen, testId: "portal-nav-files" },
  { to: "/portal/support", label: "Support", icon: LifeBuoy, testId: "portal-nav-support" },
];

export default function PortalLayout() {
  const { user, logout } = useAuth();
  const initials = (user?.name || user?.email || "?").slice(0, 2).toUpperCase();

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background" data-testid="portal-layout">
      <aside className="hidden md:flex w-[220px] flex-col shrink-0 border-r border-white/10">
        <div className="flex h-16 items-center gap-2 px-4 border-b border-white/10">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-foreground text-background font-display font-bold text-sm">O</div>
          <div className="flex flex-col leading-none">
            <span className="font-display font-bold text-sm">Client Portal</span>
            <span className="font-mono text-[10px] text-graphite">OBRINEX</span>
          </div>
        </div>
        <nav className="flex-1 py-4 px-2 space-y-0.5">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/portal"}
              data-testid={item.testId}
              className={({ isActive }) =>
                cn("flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors",
                  isActive ? "bg-surface-2 text-foreground" : "text-ash hover:bg-surface-1 hover:text-foreground")
              }
            >
              <item.icon className="h-4 w-4" /> {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-white/10 flex items-center gap-2">
          <Avatar className="h-8 w-8"><AvatarFallback className="bg-surface-2 text-xs font-mono">{initials}</AvatarFallback></Avatar>
          <div className="flex-1 overflow-hidden">
            <p className="text-xs font-medium truncate">{user?.name}</p>
            <p className="text-[10px] text-graphite truncate">{user?.email}</p>
          </div>
          <button data-testid="portal-logout-btn" onClick={logout} className="text-graphite hover:text-foreground">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto scrollbar-thin">
        <Outlet />
      </main>
    </div>
  );
}

import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { LayoutDashboard, FolderKanban, Receipt, FolderOpen, LifeBuoy, FileSignature, LogOut, Menu, X } from "lucide-react";
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

const linkClass = ({ isActive }) =>
  cn(
    "flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors",
    isActive ? "bg-surface-2 text-foreground" : "text-ash hover:bg-surface-1 hover:text-foreground"
  );

function Brand() {
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-foreground text-background font-display font-bold text-sm">
        O
      </div>
      <div className="flex flex-col leading-none">
        <span className="font-display font-bold text-sm">Client Portal</span>
        <span className="font-mono text-[10px] text-graphite">OBRINEX</span>
      </div>
    </div>
  );
}

function NavItems({ onNavigate }) {
  return (
    <>
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/portal"}
          data-testid={item.testId}
          onClick={onNavigate}
          className={linkClass}
        >
          <item.icon className="h-4 w-4" /> {item.label}
        </NavLink>
      ))}
    </>
  );
}

function UserFooter({ user, initials, logout, testId }) {
  return (
    <div className="p-3 border-t border-white/10 flex items-center gap-2">
      <Avatar className="h-8 w-8">
        <AvatarFallback className="bg-surface-2 text-xs font-mono">{initials}</AvatarFallback>
      </Avatar>
      <div className="flex-1 overflow-hidden">
        <p className="text-xs font-medium truncate">{user?.name}</p>
        <p className="text-[10px] text-graphite truncate">{user?.email}</p>
      </div>
      <button
        data-testid={testId}
        onClick={logout}
        aria-label="Sign out"
        className="text-graphite hover:text-foreground"
      >
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  );
}

export default function PortalLayout() {
  const { user, logout } = useAuth();
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();
  const initials = (user?.name || user?.email || "?").slice(0, 2).toUpperCase();

  // Close on navigation, so tapping a link does not leave the drawer covering
  // the page it just opened.
  useEffect(() => setNavOpen(false), [location.pathname]);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e) => e.key === "Escape" && setNavOpen(false);
    window.addEventListener("keydown", onKey);
    // Stop the page behind the drawer scrolling under the finger.
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [navOpen]);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background" data-testid="portal-layout">
      {/* Desktop sidebar - unchanged */}
      <aside className="hidden md:flex w-[220px] flex-col shrink-0 border-r border-white/10">
        <div className="flex h-16 items-center gap-2 px-4 border-b border-white/10">
          <Brand />
        </div>
        <nav className="flex-1 py-4 px-2 space-y-0.5">
          <NavItems />
        </nav>
        <UserFooter user={user} initials={initials} logout={logout} testId="portal-logout-btn" />
      </aside>

      {/* Mobile drawer. Without this the portal has no navigation at all below
          the md breakpoint: the sidebar is display:none and nothing replaced
          it, stranding clients on whichever page they landed on with no way
          to reach invoices, files or support - and no way to sign out. */}
      <div
        data-testid="portal-mobile-nav"
        aria-hidden={!navOpen}
        className={cn(
          "fixed inset-0 z-50 md:hidden transition pointer-events-none",
          navOpen && "pointer-events-auto"
        )}
      >
        <button
          type="button"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
          className={cn(
            "absolute inset-0 bg-black/70 transition-opacity",
            navOpen ? "opacity-100" : "opacity-0"
          )}
        />
        <aside
          className={cn(
            "absolute left-0 top-0 flex h-full w-[82vw] max-w-[300px] flex-col border-r border-white/10 bg-background transition-transform duration-200",
            navOpen ? "translate-x-0" : "-translate-x-full"
          )}
        >
          <div className="flex h-14 items-center justify-between gap-2 px-4 border-b border-white/10">
            <Brand />
            <button
              type="button"
              onClick={() => setNavOpen(false)}
              aria-label="Close navigation"
              className="flex h-9 w-9 items-center justify-center rounded-lg text-graphite hover:bg-surface-1 hover:text-foreground"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <nav className="flex-1 overflow-y-auto scrollbar-thin py-4 px-3 space-y-0.5">
            <NavItems onNavigate={() => setNavOpen(false)} />
          </nav>
          <UserFooter
            user={user}
            initials={initials}
            logout={logout}
            testId="portal-mobile-logout-btn"
          />
        </aside>
      </div>

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile header - the only route to navigation on a phone */}
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-white/10 px-4 md:hidden">
          <button
            type="button"
            data-testid="portal-mobile-menu-trigger"
            onClick={() => setNavOpen(true)}
            aria-label="Open navigation"
            aria-expanded={navOpen}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-surface-1 transition-colors hover:bg-surface-2"
          >
            <Menu className="h-5 w-5" />
          </button>
          <Brand />
        </header>

        <main className="flex-1 overflow-y-auto scrollbar-thin">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

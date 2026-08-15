import { useCallback, useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, FolderKanban, Receipt, FolderOpen, LifeBuoy,
  FileSignature, LogOut, MessageSquare, FileText,
  Sparkles, Compass, Menu, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { usePortal } from "@/contexts/PortalContext";
import ClientTwoFAPrompt from "@/components/ClientTwoFAPrompt";
import NotificationBell from "@/components/NotificationBell";
import { useUnreadCounts } from "@/lib/useNotifications";
import { NavRail } from "@/components/portal/PortalNav";
import OnboardingGate from "@/components/portal/OnboardingGate";
import PortalTour from "@/components/portal/PortalTour";
import { PageTransition, SwapUp } from "@/components/motion";

/** The client portal's shell.
 *
 *  `PageTransition` was used here without ever being imported, which threw a
 *  ReferenceError on every render of every portal route. It is imported now.
 *
 *  Navigation shares its components with the members' portal — same travelling
 *  marker, same rail, same tab bar — so the two products feel like one studio
 *  built both. The routes differ; the vocabulary does not.
 *
 *  The interview gates the portal, and the guide sits over it once, in that
 *  order. Both are driven by `PortalContext`, which fails open: if the context
 *  request errors, the portal renders normally rather than locking a client out
 *  of their own account over a dropped packet.
 */

const NAV = [
  { key: "/portal", label: "Overview", short: "Home", icon: LayoutDashboard, testId: "portal-nav-overview" },
  { key: "/portal/projects", label: "Projects", short: "Work", icon: FolderKanban, testId: "portal-nav-projects" },
  { key: "/portal/chat", label: "Messages", short: "Chat", icon: MessageSquare, testId: "portal-nav-chat", badgeKey: "chat" },
  { key: "/portal/assistant", label: "Assistant", short: "Ask", icon: Sparkles, testId: "portal-nav-assistant" },
  { key: "/portal/invoices", label: "Invoices", icon: Receipt, testId: "portal-nav-invoices" },
  { key: "/portal/support", label: "Support", icon: LifeBuoy, testId: "portal-nav-support", badgeKey: "support" },
  { key: "/portal/contracts", label: "Contracts", icon: FileSignature, testId: "portal-nav-contracts" },
  { key: "/portal/files", label: "Files", icon: FolderOpen, testId: "portal-nav-files" },
  { key: "/portal/policies", label: "Policies", icon: FileText, testId: "portal-nav-policies" },
];

const TOUR = [
  {
    icon: LayoutDashboard,
    title: "Everything about your account, in one place",
    body: "Overview is the short version — what's active, what's owed, what's open. Every figure on it is a link to the page it came from, so you're never hunting for the detail behind a number.",
  },
  {
    icon: FolderKanban,
    title: "Watch the work, not the inbox",
    body: "Projects shows real progress and the tasks under each one, updated by the team as they go. You don't have to ask for a status update — this is the status update.",
  },
  {
    icon: MessageSquare,
    title: "One thread to your team",
    body: "Messages goes straight to the people working on your account, with files attached if you need. No ticket number, no queue. Support is for anything that needs tracking to a resolution.",
  },
  {
    icon: Sparkles,
    title: "An assistant that knows your account",
    body: "It can see your projects, invoices, tickets and contracts — so ask it what's outstanding, what an invoice is for, or where a project stands. It can't change anything; it'll tell you which page does.",
  },
  {
    icon: Receipt,
    title: "Invoices and contracts live here",
    body: "Pay from Invoices, review and e-sign from Contracts, and find every deliverable under Files. Anything waiting on you keeps an accent edge until it's done.",
  },
];

function hueOf(text = "") {
  let h = 0;
  for (let i = 0; i < text.length; i += 1) h = (h * 31 + text.charCodeAt(i)) % 360;
  return h;
}

function Brand({ compact }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <div className="obx-holo obx-glass relative flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-xl">
        <span className="relative z-10 font-display text-sm font-bold">O</span>
      </div>
      {!compact && (
        <div className="min-w-0 leading-none">
          <p className="truncate font-display text-sm font-bold tracking-tight">Client Portal</p>
          <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.22em] text-graphite">
            Obrinex
          </p>
        </div>
      )}
    </div>
  );
}

function UserFooter({ user, logout, onReplayTour }) {
  const name = user?.name || user?.email || "?";
  const hue = hueOf(name);
  const initials = name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

  return (
    <div className="border-t border-white/[0.07] p-3">
      <button
        onClick={onReplayTour}
        data-testid="portal-replay-tour"
        className="mb-2 flex w-full items-center gap-2 rounded-lg px-1 py-1 text-[11px] text-carbon transition-colors hover:text-primary"
      >
        <Compass className="h-3 w-3" /> Replay the guide
      </button>
      <div className="flex items-center gap-2.5">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl font-mono text-[11px] font-semibold"
          style={{
            background: `linear-gradient(140deg, hsl(${hue} 62% 55% / 0.24), hsl(${(hue + 40) % 360} 62% 50% / 0.10))`,
            color: `hsl(${hue} 72% 80%)`,
            boxShadow: `inset 0 0 0 1px hsl(${hue} 60% 62% / 0.3)`,
          }}
        >
          {initials}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium">{user?.name}</p>
          <p className="truncate text-[10px] text-graphite">{user?.email}</p>
        </div>
        <button
          data-testid="portal-logout-btn"
          onClick={logout}
          aria-label="Sign out"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-graphite transition-colors hover:bg-white/[0.06] hover:text-foreground"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export default function PortalLayout() {
  const { user, logout } = useAuth();
  const { ready, blocked, showGuide, replayGuide } = usePortal();
  const location = useLocation();
  const navigate = useNavigate();
  const [navOpen, setNavOpen] = useState(false);

  const { counts, reload } = useUnreadCounts("/portal/unread", { enabled: ready && !blocked });

  // The longest matching route, so /portal/support/123 lights Support rather
  // than Overview — a prefix match on "/portal" alone matches everything.
  const activeKey =
    NAV.map((n) => n.key)
      .filter((key) => location.pathname === key || location.pathname.startsWith(`${key}/`))
      .sort((a, b) => b.length - a.length)[0] || "/portal";

  const go = useCallback(
    (key) => {
      setNavOpen(false);
      navigate(key);
    },
    [navigate]
  );

  useEffect(() => {
    setNavOpen(false);
    reload();
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  // Escape closes it, and the page behind must not scroll under a finger
  // meant for the drawer.
  useEffect(() => {
    if (!navOpen) return undefined;
    const onKey = (e) => e.key === "Escape" && setNavOpen(false);
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [navOpen]);

  const withBadges = (list) =>
    list.map((n) => ({ ...n, badge: n.badgeKey ? counts?.[n.badgeKey] || 0 : 0 }));

  if (!ready) return <div className="min-h-[100dvh] bg-black" />;
  if (blocked) return <OnboardingGate />;

  return (
    <div className="relative flex h-[100dvh] w-full overflow-hidden" data-testid="portal-layout">
      <aside className="hidden w-[248px] shrink-0 flex-col border-r border-white/[0.07] md:flex">
        <div className="obx-aurora relative flex h-16 items-center border-b border-white/[0.07] px-4">
          <div className="relative z-10">
            <Brand />
          </div>
        </div>
        <NavRail
          items={withBadges(NAV)}
          activeKey={activeKey}
          onSelect={go}
          groupId="client-rail"
        />
        <UserFooter user={user} logout={logout} onReplayTour={replayGuide} />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="obx-aurora flex h-14 shrink-0 items-center gap-3 border-b border-white/[0.07] px-4 md:h-16 md:px-6">
          <button
            type="button"
            onClick={() => setNavOpen(true)}
            aria-label="Open navigation"
            aria-expanded={navOpen}
            data-testid="portal-mobile-menu-trigger"
            className="obx-glass obx-lift relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl md:hidden"
          >
            <Menu className="h-4 w-4" />
          </button>
          <div className="relative z-10 md:hidden">
            <Brand compact />
          </div>
          <div className="relative z-10 hidden min-w-0 md:block">
            <SwapUp swapKey={activeKey} distance={6} duration={0.3}>
              <p className="truncate font-display text-lg font-bold tracking-tight">
                {NAV.find((n) => n.key === activeKey)?.label}
              </p>
            </SwapUp>
          </div>
          <div className="relative z-10 ml-auto flex shrink-0 items-center gap-2">
            <NotificationBell testId="portal-notifications" onNavigate={reload} />
            <button
              onClick={logout}
              data-testid="portal-mobile-logout-btn"
              aria-label="Sign out"
              className="obx-glass obx-lift flex h-9 w-9 items-center justify-center rounded-xl md:hidden"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>

        <main className="scrollbar-thin flex-1 overflow-y-auto">
          <PageTransition routeKey={location.pathname}>
            <Outlet />
          </PageTransition>
        </main>
      </div>

      {/* The phone drawer. There used to be a fixed tab bar across the foot of
          every screen: it ate 64px of a 812px phone permanently, and its
          overflow menu could not reach four of the nine sections without a
          second tap. A drawer costs one tap, carries all nine, and gives the
          screen back. */}
      <div
        data-testid="portal-mobile-nav"
        aria-hidden={!navOpen}
        className={cn(
          "pointer-events-none fixed inset-0 z-50 transition md:hidden",
          navOpen && "pointer-events-auto"
        )}
      >
        <button
          type="button"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
          className={cn(
            "absolute inset-0 bg-black/70 backdrop-blur-sm transition-opacity duration-300",
            navOpen ? "opacity-100" : "opacity-0"
          )}
        />
        <aside
          className={cn(
            "absolute left-0 top-0 flex h-full w-[84vw] max-w-[320px] flex-col border-r border-white/10 bg-black/90 backdrop-blur-2xl transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
            navOpen ? "translate-x-0" : "-translate-x-full"
          )}
        >
          <div className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-white/[0.07] px-4">
            <Brand />
            <button
              type="button"
              onClick={() => setNavOpen(false)}
              aria-label="Close navigation"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-graphite transition-colors hover:bg-white/[0.06] hover:text-foreground"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <NavRail
            items={withBadges(NAV)}
            activeKey={activeKey}
            onSelect={go}
            groupId="client-drawer"
          />

          <UserFooter user={user} logout={logout} onReplayTour={replayGuide} />
        </aside>
      </div>

      {showGuide && <PortalTour steps={TOUR} title="Client Portal · Guide" />}
      {/* Held back while the guide is up. A Radix modal makes the rest of the
          document inert, which left every button on the tour unclickable. */}
      <ClientTwoFAPrompt suspended={showGuide} />
    </div>
  );
}

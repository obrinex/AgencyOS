import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { SwapUp } from "@/components/motion";
import {
  MessageSquare, Sparkles, LogOut, FolderKanban, Users, UserPlus,
  BookOpen, HelpCircle, IdCard, Menu, X, ShieldCheck, Compass,
  PanelLeftClose, PanelLeftOpen,
} from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { usePortal } from "@/contexts/PortalContext";
import NotificationBell from "@/components/NotificationBell";
import { useUnreadCounts } from "@/lib/useNotifications";
import { NavRail, useNavShortcuts } from "@/components/portal/PortalNav";
import OnboardingGate from "@/components/portal/OnboardingGate";
import PortalTour from "@/components/portal/PortalTour";
import PortalAssistant from "@/components/portal/PortalAssistant";
import MemberGreeting from "@/components/founding/MemberGreeting";
import MembershipPassport from "@/components/founding/MembershipPassport";
import CommunityRoom from "@/components/founding/CommunityRoom";
import MemberDirectory from "@/components/founding/MemberDirectory";
import CircleProjects from "@/components/founding/CircleProjects";
import ReferralDesk from "@/components/founding/ReferralDesk";
import MemberProfile from "@/components/founding/MemberProfile";
import { Guidelines, Help } from "@/components/founding/CircleReading";

/** The Founding Circle's own portal.
 *
 *  Deliberately not the client portal. A member has their own role, so the
 *  client routes are unreachable from here and these are unreachable from
 *  there — the separation is enforced by the API, not by hiding links.
 *
 *  ## Three gates, in order
 *
 *  The interview, then the guide, then the portal. A member who has answered
 *  nothing sees only the interview; one who has answered everything but never
 *  been here sees the guide over the portal; everyone else sees the portal.
 *  Rendering them in this order is what keeps a half-set-up account from
 *  hitting a tour that references sections it is describing for the first time.
 *
 *  ## Navigation
 *
 *  Nine sections do not fit one control, so there are three shapes and the
 *  handover points are chosen by what actually fits:
 *
 *  - **≥ md** — the rail, grouped into You / The circle / Help, expanded or
 *    collapsed to icons. Collapsing is what earns a tablet a rail at all; it
 *    used to fall below `lg` to the phone's tab bar and put five of nine
 *    sections behind More on a screen with room for all nine.
 *  - **< md** — the four most-opened sections as a tab bar, the rest in a sheet.
 *  - **Keys 1–9** jump straight to a section, which is what the numerals down
 *    the left of the rail are for. Printing an index and giving it no meaning
 *    is decoration.
 *
 *  ## The tab lives in the URL
 *
 *  `?tab=chat`, so a notification can link to the room rather than to the front
 *  door, and so a reload lands where the member was.
 */

/** Nine sections, in three groups.
 *
 *  Flat, they were a pile you re-read top to bottom every time you wanted one.
 *  Grouped, the rail answers "is this about me, about the circle, or about
 *  getting help" before you read a single label — and the order within each
 *  group is by how often it is opened, not by how important it sounds.
 *
 *  The group a section belongs to is also what decides whether it earns a place
 *  on the phone's tab bar: the four `primary` ones are one per group plus the
 *  room, which is the only section people open more than once a day.
 */
const TABS = [
  { key: "membership", label: "Membership", short: "Card", icon: ShieldCheck, group: "You", primary: true },
  { key: "profile", label: "Profile", icon: IdCard, group: "You" },

  { key: "chat", label: "Community", short: "Room", icon: MessageSquare, group: "The circle", primary: true, badgeKey: "community" },
  { key: "directory", label: "Members", short: "Circle", icon: Users, group: "The circle", primary: true },
  { key: "projects", label: "Projects", icon: FolderKanban, group: "The circle" },
  { key: "refer", label: "Refer", icon: UserPlus, group: "The circle" },

  { key: "assistant", label: "Assistant", short: "Ask", icon: Sparkles, group: "Help", primary: true },
  { key: "guidelines", label: "Guidelines", icon: BookOpen, group: "Help" },
  { key: "help", label: "Help", icon: HelpCircle, group: "Help" },
];

const KEYS = TABS.map((t) => t.key);

//: Where the collapsed-rail preference is kept.
const RAIL_KEY = "obx-founding-rail";

const TOUR = [
  {
    icon: ShieldCheck,
    title: "This is your membership",
    body: "Your passport carries your member number, the seat you took and the day you were admitted. Stamps fill in as you use the circle — you can save the card as an image any time.",
  },
  {
    icon: MessageSquare,
    title: "One room, everyone in it",
    body: "There are no channels and no threads to keep up with. Everyone in the circle is in Community, including us — we post as Obrinex so you always know who you're hearing from.",
  },
  {
    icon: Sparkles,
    title: "Your assistant knows you",
    body: "It has the answers you just gave and your live membership — stamps, invitations, where you are in the intake. Ask it about the circle, about Obrinex, or about the thing you're actually stuck on.",
  },
  {
    icon: Users,
    title: "The circle is private",
    body: "Members and Projects show you who's here and what they're building. Contact details are opt-in per person — set yours under Profile, and nothing is shared until you switch it on.",
  },
  {
    icon: UserPlus,
    title: "You can bring someone",
    body: "Refer mints a link you send yourself. They answer the same eleven questions and are scored the same way — a referral is read sooner, never accepted sooner. We never email them; the introduction is yours.",
  },
];

export default function FoundingPortal() {
  const { user, logout } = useAuth();
  const { ready, blocked, showGuide, replayGuide } = usePortal();
  const [me, setMe] = useState(null);
  const [params, setParams] = useSearchParams();
  const [navOpen, setNavOpen] = useState(false);

  // Remembered, because a member who narrowed the rail meant it — re-expanding
  // on every visit is the setting quietly not working.
  const [railCollapsed, setRailCollapsed] = useState(() => {
    try { return window.localStorage.getItem(RAIL_KEY) === "1"; } catch { return false; }
  });
  const toggleRail = useCallback(() => {
    setRailCollapsed((was) => {
      const next = !was;
      try { window.localStorage.setItem(RAIL_KEY, next ? "1" : "0"); } catch { /* private mode */ }
      return next;
    });
  }, []);

  const requested = params.get("tab");
  const tab = KEYS.includes(requested) ? requested : "membership";

  const { counts, reload: reloadCounts, clear } = useUnreadCounts("/founding/unread", {
    enabled: ready && !blocked,
  });

  const setTab = useCallback(
    (key) => {
      setParams(key === "membership" ? {} : { tab: key }, { replace: true });
      setNavOpen(false);
    },
    [setParams]
  );

  useEffect(() => {
    if (blocked) return;
    api.get("/founding/me").then(({ data }) => setMe(data)).catch(() => setMe(false));
  }, [blocked]);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e) => e.key === "Escape" && setNavOpen(false);
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [navOpen]);

  const onRoomRead = useCallback(() => clear("community"), [clear]);
  const withBadges = (list) =>
    list.map((t) => ({ ...t, badge: t.badgeKey ? counts[t.badgeKey] || 0 : 0 }));

  // Number keys jump between sections, matching the numerals printed in the
  // rail. Off while either overlay is up — the gate and the tour own the
  // keyboard, and a member typing an answer must not be thrown to section 4.
  useNavShortcuts(TABS, setTab, { enabled: !blocked && !showGuide && !navOpen });

  const active = TABS.find((t) => t.key === tab);

  // Nothing renders until we know whether the interview is done. A flash of the
  // portal before the gate drops would show a member the room they have not
  // been let into yet.
  if (!ready) return <div className="min-h-[100dvh] bg-black" />;
  if (blocked) return <OnboardingGate />;

  return (
    <div className="relative flex min-h-[100dvh] text-foreground" data-testid="founding-portal">
      {/* The rail now starts at `md` in its collapsed form rather than vanishing
          below `lg`. A tablet had been getting the phone's tab bar with five of
          nine sections behind More, on a screen with room for all nine. */}
      {/* Width is a CSS transition. It measured as "frozen at 248px" while I
          was testing, which sent me chasing a framer-motion bug that did not
          exist — the automated browser pane never composites, so it reports
          document.hidden and requestAnimationFrame never fires there. No
          frames, no animation, on any engine. Verified: 0 rAF callbacks per
          second in that pane. In a real browser this simply animates. */}
      <aside
        style={{ width: railCollapsed ? 68 : 248 }}
        className="sticky top-0 hidden h-[100dvh] shrink-0 flex-col border-r border-white/[0.07] transition-[width] duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] md:flex"
      >
        <div
          className={`obx-aurora relative flex h-16 items-center border-b border-white/[0.07] ${
            railCollapsed ? "justify-center px-2" : "gap-2.5 px-4"
          }`}
        >
          <div className="obx-holo obx-glass relative z-10 flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-xl">
            <span className="relative z-10 font-display text-sm font-bold">O</span>
          </div>
          <AnimatePresence initial={false}>
            {!railCollapsed && (
              <motion.div
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -6 }}
                transition={{ duration: 0.16 }}
                className="relative z-10 min-w-0 leading-none"
              >
                <p className="truncate font-display text-sm font-bold tracking-tight">
                  Founding Circle
                </p>
                <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.22em] text-graphite">
                  Obrinex
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <NavRail
          items={withBadges(TABS)}
          activeKey={tab}
          onSelect={setTab}
          groupId="founding-rail"
          collapsed={railCollapsed}
        />

        <div className="border-t border-white/[0.07] p-2.5">
          <button
            onClick={toggleRail}
            data-testid="founding-rail-toggle"
            aria-label={railCollapsed ? "Expand the sidebar" : "Collapse the sidebar"}
            className={`group flex w-full items-center rounded-lg py-2 text-[11px] text-carbon transition-colors hover:text-foreground ${
              railCollapsed ? "justify-center" : "gap-2 px-1"
            }`}
          >
            {railCollapsed ? (
              <PanelLeftOpen className="h-4 w-4" />
            ) : (
              <>
                <PanelLeftClose className="h-4 w-4 shrink-0" /> Collapse
              </>
            )}
          </button>

          {!railCollapsed && (
            <>
              <button
                onClick={replayGuide}
                data-testid="founding-replay-tour"
                className="flex w-full items-center gap-2 rounded-lg px-1 py-1 text-[11px] text-carbon transition-colors hover:text-primary"
              >
                <Compass className="h-3 w-3" /> Replay the guide
              </button>
              <p className="mt-2 flex items-center gap-1.5 px-1 font-mono text-[9px] uppercase tracking-[0.18em] text-carbon">
                <kbd className="rounded border border-white/12 bg-white/[0.05] px-1">1</kbd>–
                <kbd className="rounded border border-white/12 bg-white/[0.05] px-1">9</kbd>
                jumps
              </p>
              <p className="obx-figure mt-1.5 px-1 font-mono text-[10px] uppercase tracking-[0.18em] text-carbon">
                {me ? `${me.members} member${me.members === 1 ? "" : "s"}` : " "}
              </p>
            </>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="obx-aurora sticky top-0 z-40 border-b border-white/[0.07] bg-black/60 backdrop-blur-xl">
          <div className="relative z-10 mx-auto flex max-w-5xl items-center gap-3 px-4 py-3 sm:px-6">
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              aria-label="Open navigation"
              aria-expanded={navOpen}
              data-testid="founding-menu-trigger"
              className="obx-glass obx-lift flex h-9 w-9 shrink-0 items-center justify-center rounded-xl md:hidden"
            >
              <Menu className="h-4 w-4" />
            </button>
            <div className="min-w-0">
              <SwapUp swapKey={tab} distance={6} duration={0.3}>
                <h1 className="truncate font-display text-base font-bold tracking-tight sm:text-lg">
                  <span className="md:hidden">Founding Circle</span>
                  <span className="hidden md:inline">{active?.label}</span>
                </h1>
              </SwapUp>
              <p className="truncate font-mono text-[9px] uppercase tracking-[0.2em] text-graphite md:hidden">
                {me ? `${me.members} member${me.members === 1 ? "" : "s"}` : " "}
              </p>
            </div>

            <div className="ml-auto flex shrink-0 items-center gap-2">
              <span className="hidden max-w-[14ch] truncate text-sm text-graphite sm:block">
                {user?.name}
              </span>
              <MemberGreeting />
              <NotificationBell testId="founding-notifications" onNavigate={reloadCounts} />
              <button
                onClick={logout}
                data-testid="founding-logout"
                aria-label="Sign out"
                className="obx-glass obx-lift flex h-9 w-9 items-center justify-center rounded-xl"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-10 pt-5 sm:px-6 sm:pt-6">
          <SwapUp swapKey={tab} distance={14} duration={0.44}>
            <div>
              {tab === "membership" && <MembershipPassport />}
              {tab === "chat" && <CommunityRoom onRead={onRoomRead} />}
              {tab === "assistant" && <PortalAssistant audience="member" />}
              {tab === "directory" && <MemberDirectory />}
              {tab === "projects" && <CircleProjects />}
              {tab === "refer" && <ReferralDesk />}
              {tab === "profile" && <MemberProfile />}
              {tab === "guidelines" && <Guidelines />}
              {tab === "help" && <Help onReplayTour={replayGuide} />}
            </div>
          </SwapUp>
        </main>
      </div>

      {/* The phone drawer. A fixed tab bar across the foot took 64px of an
          812px phone permanently and still hid five of the nine sections
          behind More. One tap opens this, all nine are in it, and the screen
          is the member's again. */}
      <div
        data-testid="founding-mobile-nav"
        aria-hidden={!navOpen}
        className={`pointer-events-none fixed inset-0 z-50 transition md:hidden ${
          navOpen ? "pointer-events-auto" : ""
        }`}
      >
        <button
          type="button"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
          className={`absolute inset-0 bg-black/70 backdrop-blur-sm transition-opacity duration-300 ${
            navOpen ? "opacity-100" : "opacity-0"
          }`}
        />
        <aside
          className={`absolute left-0 top-0 flex h-full w-[84vw] max-w-[320px] flex-col border-r border-white/10 bg-black/90 backdrop-blur-2xl transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] ${
            navOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-white/[0.07] px-4">
            <div className="flex items-center gap-2.5">
              <div className="obx-holo obx-glass relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-xl">
                <span className="relative z-10 font-display text-sm font-bold">O</span>
              </div>
              <div className="leading-none">
                <p className="font-display text-sm font-bold tracking-tight">Founding Circle</p>
                <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.22em] text-graphite">
                  Obrinex
                </p>
              </div>
            </div>
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
            items={withBadges(TABS)}
            activeKey={tab}
            onSelect={setTab}
            groupId="founding-drawer"
          />

          <div className="shrink-0 space-y-2 border-t border-white/[0.07] p-3">
            <button
              onClick={() => { setNavOpen(false); replayGuide(); }}
              data-testid="founding-drawer-replay"
              className="flex w-full items-center gap-2 rounded-lg px-1 py-1.5 text-[11px] text-graphite transition-colors hover:text-primary"
            >
              <Compass className="h-3 w-3" /> Replay the guide
            </button>
            <div className="flex items-center gap-2 border-t border-white/[0.07] pt-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium">{user?.name}</p>
                <p className="obx-figure truncate font-mono text-[10px] uppercase tracking-[0.16em] text-carbon">
                  {me ? `${me.members} member${me.members === 1 ? "" : "s"}` : " "}
                </p>
              </div>
              <button
                onClick={logout}
                data-testid="founding-drawer-logout"
                aria-label="Sign out"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-graphite transition-colors hover:bg-white/[0.06] hover:text-foreground"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </aside>
      </div>

      {showGuide && <PortalTour steps={TOUR} title="Founding Circle · Guide" />}
    </div>
  );
}

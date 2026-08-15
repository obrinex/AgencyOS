import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageSquare, Sparkles, LogOut, FolderKanban, Users, UserPlus,
  BookOpen, HelpCircle, IdCard, MoreHorizontal, ShieldCheck, Compass,
  PanelLeftClose, PanelLeftOpen,
} from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { usePortal } from "@/contexts/PortalContext";
import NotificationBell from "@/components/NotificationBell";
import { useUnreadCounts } from "@/lib/useNotifications";
import { NavRail, TabBar, MoreSheet, useNavShortcuts } from "@/components/portal/PortalNav";
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
const PRIMARY = TABS.filter((t) => t.primary);
const OVERFLOW = TABS.filter((t) => !t.primary);

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
  const [moreOpen, setMoreOpen] = useState(false);

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
      setMoreOpen(false);
    },
    [setParams]
  );

  useEffect(() => {
    if (blocked) return;
    api.get("/founding/me").then(({ data }) => setMe(data)).catch(() => setMe(false));
  }, [blocked]);

  useEffect(() => {
    if (!moreOpen) return;
    const onKey = (e) => e.key === "Escape" && setMoreOpen(false);
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [moreOpen]);

  const onRoomRead = useCallback(() => clear("community"), [clear]);
  const withBadges = (list) =>
    list.map((t) => ({ ...t, badge: t.badgeKey ? counts[t.badgeKey] || 0 : 0 }));

  // Number keys jump between sections, matching the numerals printed in the
  // rail. Off while either overlay is up — the gate and the tour own the
  // keyboard, and a member typing an answer must not be thrown to section 4.
  useNavShortcuts(TABS, setTab, { enabled: !blocked && !showGuide && !moreOpen });

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
      {/* The width changes instantly, on purpose — twice burned trying to
          animate it.

          As a framer `animate` value it wrote `width: 248px` on mount and never
          updated again. As a CSS `transition-[width]` it froze at the start
          value: inline style read `width: 68px` while `offsetWidth` stayed 248
          indefinitely, and setting `transition-property: none` snapped it to 68
          at once. Verified in the browser both times.

          So the rail resizes in one frame and the *contents* carry the motion —
          the label block fades and slides out under AnimatePresence, which is
          what the eye actually follows. A snap that always works beats a
          smooth animation that never runs. */}
      <aside
        style={{ width: railCollapsed ? 68 : 248 }}
        className="sticky top-0 hidden h-[100dvh] shrink-0 flex-col border-r border-white/[0.07] md:flex"
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
            <div className="min-w-0">
              <AnimatePresence mode="wait">
                <motion.h1
                  key={tab}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
                  className="truncate font-display text-base font-bold tracking-tight sm:text-lg"
                >
                  <span className="md:hidden">Founding Circle</span>
                  <span className="hidden md:inline">{active?.label}</span>
                </motion.h1>
              </AnimatePresence>
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

        <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-24 pt-5 sm:px-6 sm:pt-6 md:pb-10">
          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
            >
              {tab === "membership" && <MembershipPassport />}
              {tab === "chat" && <CommunityRoom onRead={onRoomRead} />}
              {tab === "assistant" && <PortalAssistant audience="member" />}
              {tab === "directory" && <MemberDirectory />}
              {tab === "projects" && <CircleProjects />}
              {tab === "refer" && <ReferralDesk />}
              {tab === "profile" && <MemberProfile />}
              {tab === "guidelines" && <Guidelines />}
              {tab === "help" && <Help onReplayTour={replayGuide} />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      <TabBar
        items={[
          ...withBadges(PRIMARY),
          {
            key: "__more",
            label: "More",
            short: "More",
            icon: MoreHorizontal,
            badge: 0,
            testId: "founding-tabbar-more",
          },
        ]}
        activeKey={OVERFLOW.some((t) => t.key === tab) ? "__more" : tab}
        onSelect={(key) => (key === "__more" ? setMoreOpen(true) : setTab(key))}
        groupId="founding-tabs"
        testId="founding-tabbar"
        hideFrom="md"
      />

      <MoreSheet
        open={moreOpen}
        items={withBadges(OVERFLOW)}
        activeKey={tab}
        onSelect={setTab}
        onClose={() => setMoreOpen(false)}
        hideFrom="md"
      />

      {showGuide && <PortalTour steps={TOUR} title="Founding Circle · Guide" />}
    </div>
  );
}

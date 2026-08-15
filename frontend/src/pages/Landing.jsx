import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useSmoothScroll, useScrolledPast, AnimatedTextIn, Rise } from "@/components/site/SiteMotion";
import HalftoneTrail from "@/components/site/HalftoneTrail";
import {
  ArrowRight, LayoutDashboard, Users, Receipt, FolderKanban, FileSignature,
  MessageSquare, LifeBuoy, Sparkles, Mail, Gem, Briefcase,
  BarChart3, Workflow, Menu, X,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

/** The public front page for Obrinex CRM.
 *
 *  `/` used to redirect straight to `/login`, so the product had no address of
 *  its own — nothing to send anyone, and a client following a link from an
 *  invoice met a password box with no explanation of what it belonged to.
 *
 *  ## It is set in the website's type, not the app's
 *
 *  Measured off the live obrinex.space rather than guessed: **Instrument Sans**
 *  700 at -0.03em for display, **Inter** for running text, **IBM Plex Mono** at
 *  0.1em for labels, on a #FFF / #C6C6C6 / #808080 neutral ramp. The app behind
 *  this page keeps Space Grotesk; scoped through `.obx-site*` so the two type
 *  systems never meet.
 *
 *  ## It stands on the app's own ground
 *
 *  No background of its own. `DarkGradientBg fixed accent="cyan"` is mounted
 *  once at the root of App.js, outside the Router, so it is already behind this
 *  route — and the front page of a tool should be standing on the same floor as
 *  the tool. Two earlier passes got this wrong: one poured a gradient into the
 *  letterforms, the next painted a second navy ground on top of the app's.
 *  Text uses the CRM's neutral ramp (ash / graphite / carbon) for the same
 *  reason.
 *
 *  ## The pace is deliberate
 *
 *  Lenis drives scrolling at 1.6s to settle, headings assemble a word at a
 *  time, and reveals run 1.25s starting 12% inside the viewport. An earlier
 *  pass fired 0.55s pops 80px early, which read as things snapping past you.
 *
 *  ## The lockup opens the page
 *
 *  The brandmark is the first thing rendered and is sized to fit inside one
 *  screen with the copy under it. An earlier cut put an eyebrow, a heading, a
 *  paragraph, a button row and a trust line in the hero, which pushed OBRINEX
 *  below the fold on a laptop — the one thing that must never be scrolled to.
 */

const EASE = [0.16, 1, 0.3, 1];

const NAV = [
  { id: "what", label: "What it does" },
  { id: "modules", label: "Modules" },
  { id: "portals", label: "Portals" },
  { id: "why", label: "Why" },
];

const PILLARS = [
  {
    icon: Workflow,
    title: "The whole engagement, one system",
    body: "A lead becomes a proposal, the proposal becomes a signed contract, the contract becomes a project, and the project becomes an invoice — without anything being retyped or lost between four tools.",
  },
  {
    icon: Users,
    title: "Your clients get a door, not an inbox",
    body: "Every client has their own portal: live project progress, invoices they can pay, contracts they can sign, files, and a direct thread to your team. Fewer status emails, because the status is already there.",
  },
  {
    icon: Sparkles,
    title: "An assistant that knows the account",
    body: "Not a chatbot bolted on. It reads the actual projects, invoices and tickets belonging to whoever is asking — and it cannot see anyone else's.",
  },
];

const MODULES = [
  { icon: LayoutDashboard, name: "Dashboard", note: "Revenue, pipeline, today" },
  { icon: BarChart3, name: "CRM & pipeline", note: "Leads, stages, follow-ups" },
  { icon: FolderKanban, name: "Projects & tasks", note: "Progress and visibility" },
  { icon: Receipt, name: "Invoicing & finance", note: "Multi-currency, card, UPI, crypto" },
  { icon: FileSignature, name: "Proposals & contracts", note: "Share, track, e-sign" },
  { icon: MessageSquare, name: "Client messaging", note: "One thread per client" },
  { icon: LifeBuoy, name: "Support desk", note: "Tickets and replies" },
  { icon: Mail, name: "Branded email", note: "Every send in your brand" },
];

const PORTALS = [
  {
    icon: Briefcase,
    kicker: "For your clients",
    title: "Client portal",
    points: [
      "Live project progress and tasks",
      "Invoices, paid in a click",
      "Contracts reviewed and e-signed",
      "Files, both directions",
      "A direct thread to the team",
      "An assistant that knows their account",
    ],
    cta: { label: "Client sign-in", to: "/login?as=client" },
  },
  {
    icon: Gem,
    kicker: "For the Founding Circle",
    title: "Members' portal",
    points: [
      "A membership passport and stamps",
      "One shared room for the circle",
      "A private member directory",
      "What everyone is building",
      "Invitations you send yourself",
      "Your own private assistant",
    ],
    cta: { label: "Member sign-in", to: "/login?as=member" },
  },
];

const DIFFERENCES = [
  "Built to run one agency properly, then made general enough to run yours.",
  "Scoped by the server, not the interface — a client cannot reach another client's anything.",
  "Every email leaves in your brand, down to the button radius.",
  "Multi-currency finance with real FX, not a currency label on a dollar amount.",
  "Runs on your own database. No per-seat pricing, no vendor between you and your clients.",
];

/* ── Shared shells ─────────────────────────────────────────────────────────
   One container, one gutter, one vertical rhythm. Every section uses these,
   which is the whole of "aligned": nothing sets its own width or padding. */

const SHELL = "mx-auto w-full max-w-[1180px] px-6 sm:px-10";

function Section({ id, children, className = "" }) {
  return (
    <section id={id} className={`${SHELL} py-24 sm:py-36 ${className}`}>
      {children}
    </section>
  );
}

//: `Rise` and the text animations live in components/site/SiteMotion.jsx.
const Reveal = Rise;

function Eyebrow({ children }) {
  return (
    <p className="obx-site-mono obx-site-muted text-[10px] sm:text-[11px]">{children}</p>
  );
}

/** Plain text, moved by the surrounding `Reveal`.
 *
 *  This used to split into words and animate each one on `whileInView`, nested
 *  inside a `Reveal` that was doing the same thing. Every section heading came
 *  out invisible: the words sat at y:110% inside their overflow-hidden spans
 *  and never played, leaving a hole where the heading should be. Two
 *  scroll-triggered animations on the same text is one too many — the outer
 *  reveal already carries it, and a heading that is reliably there beats a
 *  heading that is sometimes beautiful. */
function Heading({ children, className = "" }) {
  return (
    <h2 className={`obx-site-display mt-5 text-[clamp(1.9rem,4.4vw,3.4rem)] text-white ${className}`}>
      {children}
    </h2>
  );
}

export default function Landing() {
  const { user } = useAuth();
  const signedIn = user && user !== false;
  const home =
    user?.role === "client" ? "/portal"
      : user?.role === "founding" ? "/founding-portal"
        : "/dashboard";

  const [menuOpen, setMenuOpen] = useState(false);
  // Not a window listener: Lenis swallows those while it is driving.
  const scrolled = useScrolledPast(8);

  // Inertial scrolling for this page only. Torn down on unmount, so the CRM
  // routes behind it keep their ordinary instant scroll.
  useSmoothScroll();

  useEffect(() => {
    if (!menuOpen) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [menuOpen]);

  const go = (id) => {
    setMenuOpen(false);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="obx-site relative min-h-[100dvh] overflow-x-clip text-foreground" data-testid="landing-page">

      {/* ── Nav ──────────────────────────────────────────────────────────── */}
      <header
        className={`fixed inset-x-0 top-0 z-50 transition-colors duration-500 ${
          scrolled
            // A black fill reads *darker* than the page it sits on: the app's
            // ground carries a corner light, so the top of the screen is not
            // black to begin with. A faint white tint plus blur takes on
            // whatever is behind it, which is the same glass every card uses.
            ? "border-b border-white/[0.07] bg-white/[0.025] backdrop-blur-xl"
            : ""
        }`}
      >
        <div className={`${SHELL} flex h-[68px] items-center gap-4`}>
          <Link to="/" className="obx-site-display text-[15px] tracking-[-0.02em] text-white">
            OBRINEX
          </Link>
          <span className="obx-site-mono obx-site-muted hidden text-[10px] sm:block">CRM</span>

          <nav className="ml-auto hidden items-center gap-8 lg:flex">
            {NAV.map((n) => (
              <button
                key={n.id}
                onClick={() => go(n.id)}
                className="obx-site-mono text-[10px] text-graphite transition-colors duration-300 hover:text-white"
              >
                {n.label}
              </button>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3 lg:ml-8">
            <Link
              to={signedIn ? home : "/login"}
              data-testid="landing-login"
              className="obx-site-mono rounded-full border border-white/25 px-5 py-2.5 text-[10px] text-white transition-colors duration-500 hover:border-white/60 hover:text-white"
            >
              {signedIn ? "Open portal" : "Sign in"}
            </Link>
            <button
              onClick={() => setMenuOpen((o) => !o)}
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              className="flex h-9 w-9 items-center justify-center rounded-full border border-white/15 lg:hidden"
            >
              {menuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {menuOpen && (
          <nav className="border-t border-white/[0.07] bg-white/[0.04] px-6 py-4 backdrop-blur-2xl lg:hidden">
            {NAV.map((n) => (
              <button
                key={n.id}
                onClick={() => go(n.id)}
                className="obx-site-mono block w-full py-3 text-left text-[11px] text-ash"
              >
                {n.label}
              </button>
            ))}
          </nav>
        )}
      </header>

      {/* ── Hero ─────────────────────────────────────────────────────────────
          The lockup opens the page: it is the first thing in the flow and the
          section is exactly one screen tall, so it is never scrolled to. */}
      <section className="relative flex min-h-[100svh] flex-col items-center justify-center overflow-hidden px-6 text-center">
        {/* The halftone trail from obrinex.space/join: a dot grid that lights
            under the cursor and decays behind it. Replaces a dot globe that was
            not what was being asked for. */}
        <HalftoneTrail />

        <motion.div
          aria-hidden
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.4, ease: EASE }}
          className="obx-site-display text-white"
          style={{ fontSize: "clamp(3.2rem, 15.2vw, 12.5rem)" }}
        >
          <span className="obx-wheel">O</span>BRINEX
        </motion.div>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.2, delay: 0.5, ease: EASE }}
          className="obx-site-mono obx-site-muted mt-8 text-[10px] sm:text-[11px]"
        >
          The agency operating system
        </motion.p>

        <AnimatedTextIn
          as="h1"
          text="From first contact to final invoice — pipeline, proposals, contracts, projects, billing and support — with a portal of their own for every client."
          className="mt-6 max-w-[46ch] text-[15px] leading-[1.75] text-ash sm:text-[17px]"
          delay={0.7}
          stagger={0.028}
          duration={0.9}
        />

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.2, delay: 0.86, ease: EASE }}
          className="mt-10 flex flex-wrap items-center justify-center gap-3"
        >
          <Link
            to={signedIn ? home : "/login"}
            data-testid="landing-hero-cta"
            className="obx-site-mono rounded-full bg-white px-8 py-4 text-[10px] text-background transition-opacity duration-500 hover:opacity-85"
          >
            {signedIn ? "Open your portal" : "Sign in"}
          </Link>
          <button
            onClick={() => go("what")}
            className="obx-site-mono rounded-full border border-white/25 px-8 py-4 text-[10px] text-white transition-colors duration-500 hover:border-white/60 hover:text-white"
          >
            What it does
          </button>
        </motion.div>

        {/* The horizon arc is gone. A 26rem x 150vw ellipse across the foot
            of the hero read as a giant dark dome cutting the section in half,
            with the buttons sitting on its edge. The app's ground already
            supplies the light down here. */}

      </section>

      {/* ── What it does ─────────────────────────────────────────────────── */}
      <Section id="what">
        <Reveal><Eyebrow>What it does</Eyebrow></Reveal>
        <Reveal delay={0.08}><Heading>Three problems, solved properly.</Heading></Reveal>

        <div className="mt-16 grid gap-x-10 gap-y-14 md:grid-cols-3">
          {PILLARS.map((p, i) => (
            <Reveal key={p.title} delay={0.12 + i * 0.12}>
              <article className="obx-glass obx-lift obx-sheen h-full rounded-2xl p-7">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/25">
                  <p.icon className="h-5 w-5" strokeWidth={1.4} />
                </span>
                <h3 className="obx-site-display mt-6 text-[19px] leading-snug text-white">
                  {p.title}
                </h3>
                <p className="mt-3 text-[14px] leading-[1.75] text-graphite">{p.body}</p>
              </article>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* ── Modules ──────────────────────────────────────────────────────── */}
      <Section id="modules">
        <Reveal><Eyebrow>Modules</Eyebrow></Reveal>
        <Reveal delay={0.08}><Heading>Everything an agency runs on.</Heading></Reveal>

        <div className="mt-16 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {MODULES.map((m, i) => (
            <Reveal key={m.name} delay={0.05 + (i % 4) * 0.08}>
              <div className="obx-glass obx-lift obx-sheen group h-full rounded-2xl p-5">
                <m.icon className="h-4 w-4 text-primary transition-transform duration-500 group-hover:scale-110" strokeWidth={1.5} />
                <p className="mt-5 text-[15px] text-white">{m.name}</p>
                <p className="mt-1.5 text-[13px] leading-relaxed text-graphite">{m.note}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* ── Portals ──────────────────────────────────────────────────────── */}
      <Section id="portals">
        <Reveal><Eyebrow>Two portals</Eyebrow></Reveal>
        <Reveal delay={0.08}><Heading>Everyone gets their own front door.</Heading></Reveal>

        <div className="mt-16 grid gap-x-10 gap-y-16 md:grid-cols-2">
          {PORTALS.map((p, i) => (
            <Reveal key={p.title} delay={0.12 + i * 0.14}>
              <article className="obx-glass obx-sheen relative flex h-full flex-col overflow-hidden rounded-2xl p-7 sm:p-9">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/25">
                  <p.icon className="h-5 w-5" strokeWidth={1.4} />
                </span>
                <p className="obx-site-mono obx-site-muted mt-6 text-[10px]">{p.kicker}</p>
                <h3 className="obx-site-display mt-2 text-[26px] text-white">{p.title}</h3>

                <ul className="mt-7 space-y-3.5">
                  {p.points.map((pt) => (
                    <li key={pt} className="flex items-baseline gap-4 text-[14px] leading-relaxed text-ash">
                      <span className="h-px w-4 shrink-0 translate-y-[-4px] bg-gradient-to-r from-[#2f7bff] to-[#00d0ff]" />
                      {pt}
                    </li>
                  ))}
                </ul>

                <Link
                  to={p.cta.to}
                  data-testid={`landing-cta-${p.cta.to.split("=")[1]}`}
                  className="obx-site-mono group mt-9 inline-flex w-fit items-center gap-2.5 border-b border-white/25 pb-1.5 text-[10px] text-white transition-colors duration-300 hover:border-white"
                >
                  {p.cta.label}
                  <ArrowRight className="h-3 w-3 transition-transform duration-500 group-hover:translate-x-1" />
                </Link>
              </article>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* ── Why ──────────────────────────────────────────────────────────── */}
      <Section id="why">
        <div className="grid gap-x-16 gap-y-12 md:grid-cols-[0.9fr_1.1fr]">
          <div className="md:sticky md:top-28 md:self-start">
            <Reveal><Eyebrow>Why</Eyebrow></Reveal>
            <Reveal delay={0.08}>
              <Heading className="max-w-[14ch]">Not another CRM with your logo on it.</Heading>
            </Reveal>
            <Reveal delay={0.16}>
              <p className="mt-6 max-w-[38ch] text-[15px] leading-[1.8] text-graphite">
                It was built to run one agency properly, then made general enough to run
                yours. That is why the finance is real, the permissions are enforced by
                the API rather than by hiding buttons, and the emails look like they came
                from you rather than from a template vendor.
              </p>
            </Reveal>
            <Reveal delay={0.24}>
              <p className="obx-site-mono mt-8 text-[10px] leading-[2] text-carbon">
                Five things it does differently &rarr;
              </p>
            </Reveal>
          </div>

          <ul className="md:pt-16">
            {DIFFERENCES.map((d, i) => (
              <Reveal key={d} delay={0.1 + i * 0.1}>
                <li className="obx-glass obx-lift mb-2.5 flex items-baseline gap-5 rounded-xl px-5 py-4 text-[14px] leading-[1.75] text-ash">
                  <span className="obx-site-mono obx-figure shrink-0 text-[10px] text-primary/70">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  {d}
                </li>
              </Reveal>
            ))}
          </ul>
        </div>
      </Section>

      {/* ── Close ────────────────────────────────────────────────────────── */}
      <Section>
        <div className="obx-glass obx-sheen relative overflow-hidden rounded-3xl px-6 py-14 text-center sm:px-12 sm:py-16">
        <Reveal>
          <Eyebrow>Get started</Eyebrow>
        </Reveal>
        <Reveal delay={0.06}>
          <Heading className="mx-auto max-w-[22ch] text-center">
            Your clients are already asking for a status update.
          </Heading>
        </Reveal>
        <Reveal delay={0.12}>
          <p className="mx-auto mt-5 max-w-[46ch] text-[15px] leading-[1.8] text-graphite">
            Give them somewhere to look instead — live project progress, invoices they
            can pay, contracts they can sign, and a direct line to you.
          </p>
        </Reveal>
        <Reveal delay={0.22}>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/login?as=client"
              className="obx-site-mono rounded-full bg-white px-8 py-4 text-[10px] text-background transition-opacity duration-500 hover:opacity-85"
            >
              Client sign-in
            </Link>
            <Link
              to="/login?as=member"
              className="obx-site-mono rounded-full border border-white/25 px-8 py-4 text-[10px] text-white transition-colors duration-500 hover:border-white/60 hover:text-white"
            >
              Founding Circle sign-in
            </Link>
          </div>
        </Reveal>
        <Reveal delay={0.3}>
          <p className="obx-site-mono mt-8 text-[10px] leading-[2] text-carbon">
            Already inside? Both doors take you to your own portal.
          </p>
        </Reveal>
        </div>
      </Section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer className="border-t border-white/[0.07]">
        <div className={`${SHELL} flex flex-col items-center justify-between gap-5 py-10 sm:flex-row`}>
          <p className="obx-site-mono obx-site-muted text-[10px]">Obrinex CRM · Est. 2026</p>
          <div className="obx-site-mono flex items-center gap-8 text-[10px] text-graphite">
            <a href="https://obrinex.space" target="_blank" rel="noopener noreferrer"
               className="transition-colors duration-300 hover:text-white">obrinex.space</a>
            <Link to="/login" className="transition-colors duration-300 hover:text-white">Sign in</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

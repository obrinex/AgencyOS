import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight, LayoutDashboard, Users, Receipt, FolderKanban, FileSignature,
  MessageSquare, LifeBuoy, Sparkles, ShieldCheck, Mail, Gem, Briefcase,
  BarChart3, Workflow, Check, Menu, X,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

/** The public front page for Obrinex CRM.
 *
 *  `/` used to redirect straight to `/login`, so the product had no address of
 *  its own — nothing to send anyone, and a client following a link from an
 *  invoice met a password box with no explanation of what it belonged to.
 *
 *  One page, no router: the nav scrolls to sections on the same page. A
 *  marketing site with five routes is five things to keep consistent, and there
 *  is not five pages' worth to say.
 *
 *  Everything here is public and static. It never calls the API — the only
 *  thing it reads is whether someone is already signed in, so the button can
 *  say "Open your portal" instead of "Sign in".
 */

const EASE = [0.16, 1, 0.3, 1];

const NAV = [
  { id: "what", label: "What it does" },
  { id: "modules", label: "Modules" },
  { id: "portals", label: "Portals" },
  { id: "why", label: "Why it's different" },
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
  { icon: LayoutDashboard, name: "Dashboard", note: "Revenue, pipeline, what needs attention today" },
  { icon: BarChart3, name: "CRM & pipeline", note: "Leads, stages, follow-ups, lead finder" },
  { icon: FolderKanban, name: "Projects & tasks", note: "Progress, timelines, per-client visibility" },
  { icon: Receipt, name: "Invoicing & finance", note: "Multi-currency, card, UPI, crypto, overdue chasing" },
  { icon: FileSignature, name: "Proposals & contracts", note: "Share, track, e-sign, PDF" },
  { icon: MessageSquare, name: "Client messaging", note: "One thread per client, files attached" },
  { icon: LifeBuoy, name: "Support desk", note: "Tickets, priorities, replies both ways" },
  { icon: Mail, name: "Branded email", note: "Every send in your colours, fonts and logo" },
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
      "Files both directions",
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
      "One shared room for the whole circle",
      "A private member directory",
      "What everyone is building",
      "Invitations you send yourself",
      "Your own private assistant",
    ],
    cta: { label: "Member sign-in", to: "/login?as=member" },
  },
];

const DIFFERENCES = [
  "Built for one agency, so nothing is a generic field with a generic name.",
  "Scoped by the server, not the interface — a client cannot reach another client's anything.",
  "Every email leaves in your brand, down to the button radius.",
  "Multi-currency finance with real FX, not a currency label on a dollar amount.",
  "Runs on your own database. No per-seat pricing, no vendor between you and your clients.",
];

function Section({ id, children, className = "" }) {
  return (
    <section id={id} className={`mx-auto w-full max-w-6xl px-5 sm:px-8 ${className}`}>
      {children}
    </section>
  );
}

function Reveal({ children, delay = 0, className = "" }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 26 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.9, delay, ease: EASE }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function Eyebrow({ children }) {
  return (
    <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-primary/80">{children}</p>
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
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

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
    <div className="min-h-[100dvh] text-foreground" data-testid="landing-page">
      {/* ── Nav ──────────────────────────────────────────────────────────── */}
      <header
        className={`sticky top-0 z-50 border-b transition-colors duration-300 ${
          scrolled ? "border-white/[0.08] bg-black/70 backdrop-blur-xl" : "border-transparent"
        }`}
      >
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-5 sm:px-8">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="obx-holo obx-glass relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-xl">
              <span className="relative z-10 font-display text-sm font-bold">O</span>
            </div>
            <div className="leading-none">
              <p className="font-display text-sm font-bold tracking-tight">Obrinex CRM</p>
              <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.22em] text-graphite">
                Agency OS
              </p>
            </div>
          </Link>

          <nav className="ml-6 hidden items-center gap-1 lg:flex">
            {NAV.map((n) => (
              <button
                key={n.id}
                onClick={() => go(n.id)}
                className="rounded-lg px-3 py-1.5 text-sm text-ash transition-colors hover:bg-white/[0.05] hover:text-foreground"
              >
                {n.label}
              </button>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            {signedIn ? (
              <Link
                to={home}
                data-testid="landing-open-portal"
                className="flex items-center gap-1.5 rounded-xl bg-primary px-3.5 py-2 text-sm font-medium text-background"
              >
                Open your portal <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            ) : (
              <Link
                to="/login"
                data-testid="landing-login"
                className="obx-glass obx-lift flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm"
              >
                Sign in <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            )}
            <button
              onClick={() => setMenuOpen((o) => !o)}
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              className="obx-glass flex h-9 w-9 items-center justify-center rounded-xl lg:hidden"
            >
              {menuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {menuOpen && (
          <motion.nav
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="border-t border-white/[0.08] bg-black/90 px-5 py-3 backdrop-blur-xl lg:hidden"
          >
            {NAV.map((n) => (
              <button
                key={n.id}
                onClick={() => go(n.id)}
                className="block w-full rounded-lg px-2 py-2.5 text-left text-sm text-ash hover:text-foreground"
              >
                {n.label}
              </button>
            ))}
          </motion.nav>
        )}
      </header>

      {/* ── Hero ─────────────────────────────────────────────────────────
          The same opening as obrinex.space: the grid field, the giant OBRINEX
          lockup with the "O" turning like a wheel, and the horizon arc beneath
          it. The marketing site and the product now start the same way, which
          is most of what makes them read as one company rather than two. */}
      <section className="relative overflow-hidden px-5 sm:px-8">
        <div aria-hidden className="obx-grid-field pointer-events-none absolute inset-x-0 top-0 z-0 h-[62vh] opacity-40" />
        <div className="obx-aurora pointer-events-none absolute inset-x-0 top-0 z-0 h-[70vh]" />

        <div className="relative z-10 mx-auto flex min-h-[92svh] max-w-6xl flex-col items-center justify-center py-24 text-center">
          <motion.button
            onClick={() => go("what")}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, delay: 0.1, ease: EASE }}
            className="group flex items-center gap-2 rounded-full border border-white/12 bg-white/[0.04] px-5 py-2 font-mono text-[10px] uppercase tracking-[0.2em] text-graphite backdrop-blur-sm transition-colors hover:text-foreground"
          >
            The agency operating system
            <ArrowRight className="h-3 w-3 transition-transform duration-500 group-hover:translate-x-1" />
          </motion.button>

          {/* The lockup. `aria-hidden` because it is a brandmark — the real
              heading for screen readers and search is the h1 below it. */}
          <motion.div
            aria-hidden
            initial={{ opacity: 0, y: 26 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1.1, delay: 0.24, ease: EASE }}
            className="mt-8 font-display font-bold leading-[0.82] tracking-tight"
            style={{ fontSize: "clamp(2.8rem, 14vw, 13rem)" }}
          >
            <span className="obx-wheel">O</span>BRINEX
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, delay: 0.42, ease: EASE }}
            className="mt-8 max-w-2xl font-display text-xl font-semibold leading-snug tracking-tight sm:text-3xl"
          >
            Run the whole agency <span className="obx-gradient-text">in one place.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, delay: 0.56, ease: EASE }}
            className="mt-5 max-w-xl text-sm leading-relaxed text-ash sm:text-base"
          >
            From first contact to final invoice — pipeline, proposals, contracts, projects,
            billing and support — with a portal of their own for every client.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, delay: 0.7, ease: EASE }}
            className="mt-10 flex flex-wrap items-center justify-center gap-3"
          >
            <Link
              to={signedIn ? home : "/login"}
              data-testid="landing-hero-cta"
              className="flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-medium text-background transition-transform duration-500 hover:-translate-y-0.5"
            >
              {signedIn ? "Open your portal" : "Sign in"} <ArrowRight className="h-4 w-4" />
            </Link>
            <button
              onClick={() => go("modules")}
              className="obx-glass obx-lift obx-sheen rounded-xl px-5 py-3 text-sm"
            >
              See what&apos;s inside
            </button>
          </motion.div>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1.2, delay: 0.9, ease: EASE }}
            className="mt-8 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 font-mono text-[10px] uppercase tracking-[0.18em] text-carbon"
          >
            <span className="flex items-center gap-1.5"><ShieldCheck className="h-3 w-3" /> Role-scoped access</span>
            <span className="flex items-center gap-1.5"><Receipt className="h-3 w-3" /> Multi-currency</span>
            <span className="flex items-center gap-1.5"><Mail className="h-3 w-3" /> Fully branded email</span>
          </motion.p>
        </div>

        <div
          aria-hidden
          className="obx-horizon pointer-events-none absolute left-1/2 top-[calc(100%-7rem)] z-0 h-[30rem] w-[130vw] -translate-x-1/2 rounded-[100%] border border-white/15"
        />
      </section>

      {/* ── What it does ─────────────────────────────────────────────────── */}
      <Section id="what" className="py-16 sm:py-24">
        <Reveal><Eyebrow>What it does</Eyebrow></Reveal>
        <Reveal delay={0.05}>
          <h2 className="mt-3 max-w-2xl font-display text-2xl font-bold tracking-tight sm:text-4xl">
            Three problems, solved properly.
          </h2>
        </Reveal>
        <div className="mt-10 grid gap-3 md:grid-cols-3">
          {PILLARS.map((p, i) => (
            <Reveal key={p.title} delay={0.06 * i}>
              <article className="obx-glass obx-lift obx-sheen h-full rounded-2xl p-6">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/12 text-primary ring-1 ring-primary/25">
                  <p.icon className="h-5 w-5" />
                </span>
                <h3 className="mt-4 font-display text-lg font-semibold tracking-tight">{p.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-graphite">{p.body}</p>
              </article>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* ── Modules ──────────────────────────────────────────────────────── */}
      <Section id="modules" className="py-16 sm:py-24">
        <Reveal><Eyebrow>Modules</Eyebrow></Reveal>
        <Reveal delay={0.05}>
          <h2 className="mt-3 max-w-2xl font-display text-2xl font-bold tracking-tight sm:text-4xl">
            Everything an agency actually runs on.
          </h2>
        </Reveal>
        <div className="mt-10 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          {MODULES.map((m, i) => (
            <Reveal key={m.name} delay={0.03 * i}>
              <div className="obx-glass obx-lift h-full rounded-2xl p-5">
                <m.icon className="h-4 w-4 text-primary" />
                <p className="mt-3 text-sm font-medium">{m.name}</p>
                <p className="mt-1 text-xs leading-snug text-graphite">{m.note}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* ── Portals ──────────────────────────────────────────────────────── */}
      <Section id="portals" className="py-16 sm:py-24">
        <Reveal><Eyebrow>Two portals</Eyebrow></Reveal>
        <Reveal delay={0.05}>
          <h2 className="mt-3 max-w-2xl font-display text-2xl font-bold tracking-tight sm:text-4xl">
            Everyone gets their own front door.
          </h2>
        </Reveal>
        <div className="mt-10 grid gap-3 md:grid-cols-2">
          {PORTALS.map((p, i) => (
            <Reveal key={p.title} delay={0.07 * i}>
              <article className="obx-glass obx-lift obx-sheen relative h-full overflow-hidden rounded-2xl p-6 sm:p-8">
                <div className="obx-aurora pointer-events-none absolute inset-0" />
                <div className="relative z-10">
                  <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/12 text-primary ring-1 ring-primary/25">
                    <p.icon className="h-5 w-5" />
                  </span>
                  <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">
                    {p.kicker}
                  </p>
                  <h3 className="mt-1 font-display text-xl font-bold tracking-tight">{p.title}</h3>
                  <ul className="mt-5 space-y-2">
                    {p.points.map((pt) => (
                      <li key={pt} className="flex items-start gap-2.5 text-sm text-ash">
                        <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                        {pt}
                      </li>
                    ))}
                  </ul>
                  <Link
                    to={p.cta.to}
                    data-testid={`landing-cta-${p.cta.to.split("=")[1]}`}
                    className="obx-glass obx-lift mt-6 inline-flex items-center gap-1.5 rounded-xl px-4 py-2.5 text-sm"
                  >
                    {p.cta.label} <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </div>
              </article>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* ── Why ──────────────────────────────────────────────────────────── */}
      <Section id="why" className="py-16 sm:py-24">
        <div className="grid gap-10 md:grid-cols-2 md:items-center">
          <div>
            <Reveal><Eyebrow>Why it's different</Eyebrow></Reveal>
            <Reveal delay={0.05}>
              <h2 className="mt-3 font-display text-2xl font-bold tracking-tight sm:text-4xl">
                Not another CRM with your logo on it.
              </h2>
            </Reveal>
            <Reveal delay={0.1}>
              <p className="mt-4 text-sm leading-relaxed text-graphite sm:text-base">
                It was built to run one agency properly, then made general enough to run
                yours. That's why the finance is real, the permissions are enforced by the
                API rather than by hiding buttons, and the emails look like they came from
                you rather than from a template vendor.
              </p>
            </Reveal>
          </div>
          <Reveal delay={0.1}>
            <ul className="obx-glass space-y-3 rounded-2xl p-6">
              {DIFFERENCES.map((d) => (
                <li key={d} className="flex items-start gap-3 text-sm leading-relaxed text-ash">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  {d}
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </Section>

      {/* ── Close ────────────────────────────────────────────────────────── */}
      <Section className="pb-24">
        <Reveal>
          <div className="obx-glass obx-sheen relative overflow-hidden rounded-3xl px-6 py-14 text-center sm:px-12 sm:py-20">
            <div className="obx-aurora pointer-events-none absolute inset-0" />
            <div className="relative z-10">
              <h2 className="mx-auto max-w-2xl font-display text-2xl font-bold tracking-tight sm:text-4xl">
                Your clients are already asking for a status update.
              </h2>
              <p className="mx-auto mt-4 max-w-xl text-sm leading-relaxed text-graphite sm:text-base">
                Give them somewhere to look instead.
              </p>
              <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
                <Link
                  to="/login?as=client"
                  className="flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-medium text-background"
                >
                  Client sign-in <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  to="/login?as=member"
                  className="obx-glass obx-lift rounded-xl px-5 py-3 text-sm"
                >
                  Founding Circle sign-in
                </Link>
              </div>
            </div>
          </div>
        </Reveal>
      </Section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer className="border-t border-white/[0.07]">
        <Section className="flex flex-col items-center justify-between gap-4 py-8 sm:flex-row">
          <div className="flex items-center gap-2.5">
            <div className="obx-glass flex h-8 w-8 items-center justify-center rounded-lg">
              <span className="font-display text-xs font-bold">O</span>
            </div>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
              Obrinex CRM · Est. 2026
            </p>
          </div>
          <div className="flex items-center gap-5 text-xs text-carbon">
            <a href="https://obrinex.space" target="_blank" rel="noopener noreferrer"
               className="transition-colors hover:text-foreground">obrinex.space</a>
            <Link to="/login" className="transition-colors hover:text-foreground">Sign in</Link>
          </div>
        </Section>
      </footer>
    </div>
  );
}

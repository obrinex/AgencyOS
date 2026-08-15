import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { Rise } from "@/components/site/SiteMotion";
import { prefersReducedMotion } from "@/components/motion";

/** obrinex.space's footer, ported.
 *
 *  A direct port of `components/ui/motion-footer.tsx` from the website repo,
 *  not an approximation: the same aurora, the same 72px grid, the same diagonal
 *  marquee, the same magnetic mail pill and social discs, the same masked
 *  wordmark with the spinning "I", the same legal pills and the same closing
 *  rule. Copy comes from that repo's `data/site.ts`, so the address, the
 *  tagline, the founder and the year are the values the site itself renders.
 *
 *  ## Where it deviates, and why
 *
 *  1. **No GSAP.** The original drives the curtain parallax and the wordmark's
 *     clip reveal through ScrollTrigger. This app has no GSAP and adding it for
 *     one footer is not worth the weight, so the reveal is framer's — and the
 *     wordmark is never hidden behind an animation that might not fire. A
 *     heading that only exists once an observer resolves is exactly the bug
 *     that made this page's section titles invisible.
 *  2. **One extra legal pill.** The site links three. The full eleven live at
 *     `/policies`, so an "All policies" pill points there rather than leaving
 *     eight documents with no route in.
 *  3. **Greys are one step lighter.** The site sets these on #808080; at 10px
 *     with wide tracking that is the text that vanished here, so they sit on
 *     the CRM's `graphite` instead.
 */

const SITE = {
  legalName: "Obrinex Agency",
  founder: "Jagjot Singh Makkar",
  est: "2026",
  email: "info@obrinex.space",
  supportEmail: "support@obrinex.space",
  tagline: "We build the systems. You run the business.",
};

const SOCIALS = [
  { label: "LinkedIn", href: "https://www.linkedin.com/in/obrinex-agency-3b1080420/" },
  { label: "Instagram", href: "https://www.instagram.com/obrinex.ai" },
  { label: "Discord", href: "https://discord.gg/NcNhke89gU" },
  { label: "X", href: "https://x.com/obrinexagency" },
];

/* The brand marks as paths, exactly as the site draws them — lucide dropped its
   brand icons, so importing them renders nothing. `currentColor` so they
   inherit the link's hover state. */
const ICON = {
  LinkedIn: (
    <path d="M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5ZM3 9h4v12H3V9Zm7 0h3.8v1.65h.05A4.17 4.17 0 0 1 17.6 8.7c4 0 4.75 2.5 4.75 5.76V21h-4v-5.75c0-1.37-.03-3.14-1.96-3.14-1.96 0-2.26 1.5-2.26 3.04V21h-3.96V9Z" />
  ),
  Instagram: (
    <path d="M12 2.16c3.2 0 3.58.01 4.85.07 1.17.05 1.8.25 2.23.41.56.22.96.48 1.38.9.42.42.68.82.9 1.38.16.42.36 1.06.41 2.23.06 1.27.07 1.65.07 4.85s-.01 3.58-.07 4.85c-.05 1.17-.25 1.8-.41 2.23-.22.56-.48.96-.9 1.38-.42.42-.82.68-1.38.9-.42.16-1.06.36-2.23.41-1.27.06-1.65.07-4.85.07s-3.58-.01-4.85-.07c-1.17-.05-1.8-.25-2.23-.41a3.8 3.8 0 0 1-1.38-.9 3.8 3.8 0 0 1-.9-1.38c-.16-.42-.36-1.06-.41-2.23C2.17 15.58 2.16 15.2 2.16 12s.01-3.58.07-4.85c.05-1.17.25-1.8.41-2.23.22-.56.48-.96.9-1.38.42-.42.82-.68 1.38-.9.42-.16 1.06-.36 2.23-.41C8.42 2.17 8.8 2.16 12 2.16Zm0 1.98c-3.14 0-3.5.01-4.74.07-1.15.05-1.77.24-2.18.4-.55.22-.94.47-1.35.88-.41.41-.66.8-.88 1.35-.16.41-.35 1.03-.4 2.18-.06 1.24-.07 1.6-.07 4.74s.01 3.5.07 4.74c.05 1.15.24 1.77.4 2.18.22.55.47.94.88 1.35.41.41.8.66 1.35.88.41.16 1.03.35 2.18.4 1.24.06 1.6.07 4.74.07s3.5-.01 4.74-.07c1.15-.05 1.77-.24 2.18-.4.55-.22.94-.47 1.35-.88.41-.41.66-.8.88-1.35.16-.41.35-1.03.4-2.18.06-1.24.07-1.6.07-4.74s-.01-3.5-.07-4.74c-.05-1.15-.24-1.77-.4-2.18a3.6 3.6 0 0 0-.88-1.35 3.6 3.6 0 0 0-1.35-.88c-.41-.16-1.03-.35-2.18-.4-1.24-.06-1.6-.07-4.74-.07Zm0 3.37a4.49 4.49 0 1 1 0 8.98 4.49 4.49 0 0 1 0-8.98Zm0 7.4a2.91 2.91 0 1 0 0-5.82 2.91 2.91 0 0 0 0 5.82Zm5.72-7.6a1.05 1.05 0 1 1-2.1 0 1.05 1.05 0 0 1 2.1 0Z" />
  ),
  X: (
    <path d="M17.53 3h3.02l-6.6 7.55L21.75 21h-5.9l-4.62-6.04L5.94 21H2.92l7.06-8.07L2.5 3h6.05l4.18 5.52L17.53 3Zm-1.06 16.2h1.67L7.62 4.7H5.83l10.64 14.5Z" />
  ),
};

function SocialMark({ label }) {
  if (label === "Discord") {
    return (
      <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M7.5 7.6a14 14 0 0 1 9 0" />
        <path d="M6.6 17.5c-1.5-.5-2.7-1.2-3.6-2.1.1-3.4 1-6.3 2.9-8.8A15 15 0 0 1 9 5.4l.7 1.4" />
        <path d="M17.4 17.5c1.5-.5 2.7-1.2 3.6-2.1-.1-3.4-1-6.3-2.9-8.8A15 15 0 0 0 15 5.4l-.7 1.4" />
        <path d="M8.2 16.8c2.5 1.1 5.1 1.1 7.6 0" />
        <path d="M9 12.4h.01" />
        <path d="M15 12.4h.01" />
      </svg>
    );
  }
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      {ICON[label]}
    </svg>
  );
}

/** Pulls gently toward the pointer while hovered, springs back on leave. */
function Magnetic({ strength = 0.25, className = "", children }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return undefined;
    if (window.matchMedia("(pointer: coarse)").matches) return undefined;

    const onMove = (e) => {
      const r = el.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2);
      const dy = e.clientY - (r.top + r.height / 2);
      el.style.transform = `translate3d(${dx * strength}px, ${dy * strength}px, 0)`;
    };
    const onLeave = () => { el.style.transform = "translate3d(0,0,0)"; };
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [strength]);
  return (
    <div ref={ref} className={`inline-block transition-transform duration-500 ease-out ${className}`}>
      {children}
    </div>
  );
}

/** Infinite horizontal marquee: a duplicated track translated on rAF, with the
 *  "O" glyph between phrases and a slow-down on hover. */
function Marquee({ text, speed = 0.6, className = "" }) {
  const track = useRef(null);
  const hovering = useRef(false);

  useEffect(() => {
    const el = track.current;
    if (!el || prefersReducedMotion()) return undefined;
    let x = 0;
    let raf = 0;
    let half = el.scrollWidth / 2;
    const measure = () => { half = el.scrollWidth / 2; };
    measure();
    window.addEventListener("resize", measure);

    const tick = () => {
      x -= speed * (hovering.current ? 0.15 : 1);
      if (half > 0) {
        if (x <= -half) x += half;
        if (x > 0) x -= half;
      }
      el.style.transform = `translate3d(${x}px,0,0)`;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", measure);
    };
  }, [speed]);

  const unit = (
    <div className="flex shrink-0 items-center leading-none">
      <span className="whitespace-nowrap">{text}</span>
      <span className="obx-site-display mx-8 inline-block opacity-70">O</span>
    </div>
  );

  return (
    <div
      className="overflow-hidden"
      onMouseEnter={() => { hovering.current = true; }}
      onMouseLeave={() => { hovering.current = false; }}
    >
      <div ref={track} className={`flex w-max will-change-transform ${className}`}>
        {unit}{unit}{unit}{unit}{unit}{unit}
      </div>
    </div>
  );
}

const LEGAL = [
  { label: "Terms of Service", to: "/policies/terms" },
  { label: "Support", href: `mailto:${SITE.supportEmail}?subject=Support`, cursor: "Mail" },
  { label: "Privacy Policy", to: "/policies/privacy" },
  { label: "All policies", to: "/policies" },
];

const PILL =
  "obx-site-mono inline-flex items-center rounded-full border border-white/12 bg-white/[0.04] px-4 py-2.5 text-[10px] text-graphite backdrop-blur-sm transition-colors duration-500 hover:border-white/35 hover:bg-white/[0.08] hover:text-white";

export default function SiteFooter() {
  const toTop = () => window.scrollTo({ top: 0, behavior: "smooth" });

  return (
    <footer className="relative overflow-hidden bg-transparent pt-24 text-foreground"
            data-testid="site-footer">
      {/* Aurora glow, behind the grid. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[70%] opacity-70"
        style={{
          background:
            "radial-gradient(70% 55% at 50% 0%, rgba(255,255,255,0.13) 0%, rgba(255,255,255,0.05) 38%, rgba(0,0,0,0) 72%)",
        }}
      />
      {/* The footer's own grid, faded out towards the foot so it never fights
          the wordmark. 72px here, against the page's 84px. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(255,255,255,0.055) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.055) 1px, transparent 1px)",
          backgroundSize: "72px 72px",
          maskImage:
            "linear-gradient(to bottom, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.35) 55%, rgba(0,0,0,0) 88%)",
          WebkitMaskImage:
            "linear-gradient(to bottom, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.35) 55%, rgba(0,0,0,0) 88%)",
        }}
      />

      <div className="relative z-10">
        {/* Diagonal marquee — the tilt is what stops the footer reading as
            another stack of horizontal rules. */}
        <div
          aria-hidden
          className="pointer-events-none relative left-1/2 w-[128vw] -translate-x-1/2 -rotate-[2.5deg] border-y border-white/12 py-5"
        >
          <Marquee
            text="LET'S BUILD SOMETHING INTELLIGENT"
            className="obx-site-display text-[clamp(1.4rem,3vw,2.4rem)] text-white"
          />
        </div>

        {/* Contact + follow. */}
        <div className="mx-auto grid max-w-[1180px] items-start gap-x-12 gap-y-12 px-6 py-24 sm:px-10 md:grid-cols-12">
          <div className="md:col-span-7">
            <p className="obx-site-mono text-[10px] text-graphite">{SITE.tagline}</p>
            <div className="mt-7">
              <Magnetic strength={0.25}>
                <a
                  href={`mailto:${SITE.email}`}
                  data-cursor="Mail"
                  data-testid="footer-email"
                  className="group/mail inline-flex items-center gap-5 rounded-full border border-white/12 bg-white/[0.05] py-4 pl-7 pr-4 backdrop-blur-md transition-colors duration-500 hover:border-white/40 hover:bg-white/[0.09]"
                >
                  <span className="obx-site-display text-[clamp(1.1rem,2.2vw,1.5rem)] font-semibold leading-none text-white">
                    {SITE.email}
                  </span>
                  <span
                    aria-hidden
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/12 text-graphite transition-all duration-500 group-hover/mail:border-white group-hover/mail:bg-white group-hover/mail:text-black"
                  >
                    <ArrowUpRight size={17} strokeWidth={1.6} />
                  </span>
                </a>
              </Magnetic>
            </div>
          </div>

          <div className="md:col-span-5 md:justify-self-end">
            <p className="obx-site-mono mb-5 text-[10px] text-graphite md:text-right">Follow</p>
            <ul className="flex flex-wrap gap-3 md:justify-end">
              {SOCIALS.map((s) => (
                <li key={s.label}>
                  <Magnetic strength={0.3}>
                    <a
                      href={s.href}
                      target="_blank"
                      rel="noreferrer noopener"
                      aria-label={s.label}
                      data-cursor={s.label}
                      className="flex h-14 w-14 items-center justify-center rounded-full border border-white/12 bg-white/[0.05] text-graphite backdrop-blur-md transition-colors duration-500 hover:border-white/40 hover:bg-white/[0.10] hover:text-white"
                    >
                      <SocialMark label={s.label} />
                    </a>
                  </Magnetic>
                </li>
              ))}
            </ul>

            <div className="mt-8 md:text-right">
              <button
                onClick={toTop}
                data-cursor="Top"
                data-testid="footer-to-top"
                className="obx-site-mono -m-3 p-3 text-[11px] text-graphite transition-colors duration-300 hover:text-white"
              >
                Back to top &uarr;
              </button>
            </div>
          </div>
        </div>

        {/* The wordmark. Deliberately not hidden behind a clip reveal — it is
            the largest thing on the page and must never depend on an
            observer firing. */}
        <div className="overflow-hidden border-t border-white/12">
          <Rise y={24} duration={1.1}>
            <h2 className="obx-site-display select-none whitespace-nowrap px-6 py-8 text-center leading-none text-white sm:px-10"
                style={{ fontSize: "clamp(4rem, 22vw, 20rem)" }}>
              OBR<span className="obx-wheel">I</span>NEX
            </h2>
          </Rise>
        </div>

        {/* Legal + support. */}
        <div className="mx-auto max-w-[1180px] px-6 pb-10 pt-2 sm:px-10">
          <ul className="flex flex-wrap gap-2.5">
            {LEGAL.map((l) => (
              <li key={l.label}>
                {l.href ? (
                  <a href={l.href} data-cursor={l.cursor || "Read"} className={PILL}>{l.label}</a>
                ) : (
                  <Link to={l.to} data-cursor="Read" className={PILL}>{l.label}</Link>
                )}
              </li>
            ))}
          </ul>

          <div className="mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-white/12 pt-6">
            <p className="obx-site-mono text-[10px] text-graphite">
              &copy; {SITE.est} {SITE.legalName}
            </p>
            <p className="obx-site-mono text-[10px] text-graphite">
              Founded by {SITE.founder}
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}

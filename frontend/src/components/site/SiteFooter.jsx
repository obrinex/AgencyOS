import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUp, Mail } from "lucide-react";
import api from "@/lib/api";

/** The website's footer, on the CRM's front page.
 *
 *  Contents taken from the live obrinex.space footer rather than invented: the
 *  same address, the same four social accounts, the same closing lines.
 *
 *  ## The policies are fetched, not hardcoded
 *
 *  There are eleven of them and the list lives in `backend/routers/policies.py`.
 *  Typing them out here would mean a footer that quietly goes stale the first
 *  time one is added or renamed — and legal links that 404 are worse than no
 *  legal links. It reads the public endpoint and falls back to the two the
 *  website itself links if that request fails, so the footer is never empty.
 */

const EMAIL = "info@obrinex.space";
const SUPPORT = "support@obrinex.space";

const SOCIALS = [
  { label: "LinkedIn", href: "https://www.linkedin.com/in/obrinex-agency-3b1080420/" },
  { label: "Instagram", href: "https://www.instagram.com/obrinex.ai" },
  { label: "Discord", href: "https://discord.gg/NcNhke89gU" },
  { label: "X", href: "https://x.com/obrinexagency" },
];

//: What the site links today, used if the API cannot be reached.
const FALLBACK_POLICIES = [
  { slug: "terms", title: "Terms & Conditions" },
  { slug: "privacy", title: "Privacy Policy" },
];

export default function SiteFooter() {
  const [policies, setPolicies] = useState(FALLBACK_POLICIES);

  useEffect(() => {
    api.get("/public/policies")
      .then(({ data }) => { if (Array.isArray(data) && data.length) setPolicies(data); })
      .catch(() => { /* keep the fallback */ });
  }, []);

  const toTop = () => window.scrollTo({ top: 0, behavior: "smooth" });

  return (
    <footer className="relative border-t border-white/[0.09]" data-testid="site-footer">
      <div className="mx-auto w-full max-w-[1180px] px-6 sm:px-10">
        {/* ── The line ──────────────────────────────────────────────────── */}
        <div className="flex flex-col gap-6 py-16 sm:flex-row sm:items-end sm:justify-between sm:py-20">
          <div>
            <p className="obx-site-display text-[clamp(1.6rem,3.4vw,2.6rem)] leading-[1.1] text-white">
              Let&apos;s build something intelligent.
            </p>
            <p className="obx-site-mono mt-4 text-[10px] text-graphite">
              We build the systems. You run the business.
            </p>
          </div>
          <button
            onClick={toTop}
            data-cursor="Top"
            data-testid="footer-to-top"
            className="obx-site-mono group flex shrink-0 items-center gap-2 rounded-full border border-white/20 px-5 py-3 text-[10px] text-white transition-colors duration-500 hover:border-white/60"
          >
            Back to top
            <ArrowUp className="h-3 w-3 transition-transform duration-500 group-hover:-translate-y-0.5" />
          </button>
        </div>

        {/* ── The columns ───────────────────────────────────────────────── */}
        <div className="grid gap-10 border-t border-white/[0.07] py-14 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="obx-site-mono text-[10px] text-carbon">Contact</p>
            <a
              href={`mailto:${EMAIL}`}
              data-cursor="Email"
              className="mt-4 flex items-center gap-2 text-[14px] text-ash transition-colors duration-300 hover:text-white"
            >
              <Mail className="h-3.5 w-3.5 shrink-0" /> {EMAIL}
            </a>
            <a
              href={`mailto:${SUPPORT}?subject=Support`}
              className="mt-2 block text-[14px] text-ash transition-colors duration-300 hover:text-white"
            >
              {SUPPORT}
            </a>
          </div>

          <div>
            <p className="obx-site-mono text-[10px] text-carbon">Follow</p>
            <ul className="mt-4 space-y-2">
              {SOCIALS.map((sN) => (
                <li key={sN.label}>
                  <a
                    href={sN.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-cursor={sN.label}
                    className="text-[14px] text-ash transition-colors duration-300 hover:text-white"
                  >
                    {sN.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div className="sm:col-span-2">
            <p className="obx-site-mono text-[10px] text-carbon">Legal</p>
            <ul className="mt-4 grid gap-x-8 gap-y-2 sm:grid-cols-2">
              {policies.map((p) => (
                <li key={p.slug}>
                  <Link
                    to={`/policies/${p.slug}`}
                    className="text-[14px] text-ash transition-colors duration-300 hover:text-white"
                  >
                    {p.title}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* ── The rule ──────────────────────────────────────────────────── */}
        <div className="flex flex-col gap-3 border-t border-white/[0.07] py-8 sm:flex-row sm:items-center sm:justify-between">
          <p className="obx-site-mono text-[10px] text-carbon">
            &copy; {new Date().getFullYear()} Obrinex Agency
          </p>
          <div className="obx-site-mono flex flex-wrap items-center gap-6 text-[10px] text-carbon">
            <a
              href="https://obrinex.space"
              target="_blank"
              rel="noopener noreferrer"
              className="transition-colors duration-300 hover:text-white"
            >
              obrinex.space
            </a>
            <Link to="/login" className="transition-colors duration-300 hover:text-white">
              Sign in
            </Link>
            <span>Founded by Jagjot Singh Makkar</span>
          </div>
        </div>
      </div>
    </footer>
  );
}

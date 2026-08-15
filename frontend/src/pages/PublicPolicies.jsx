import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, FileText } from "lucide-react";
import api from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import SiteFooter from "@/components/site/SiteFooter";
import SiteCursor, { CursorField } from "@/components/site/SiteCursor";
import { useSmoothScroll, useScrolledPast, Rise } from "@/components/site/SiteMotion";

/** The legal documents, readable without an account.
 *
 *  They were only reachable from inside the portal, which is the wrong audience
 *  entirely: the people who need to read the terms are the ones deciding
 *  whether to sign up, and they do not have a login yet. The footer links all
 *  eleven, so all eleven have to resolve to something.
 *
 *  Set in the site's type rather than the app's, because this is part of the
 *  public front rather than part of the product.
 */

/** Minimal markdown. The documents are headings, paragraphs, lists and the
 *  occasional bold run — a full parser would be a dependency to keep patched
 *  for four constructs. */
function Markdown({ text }) {
  const blocks = String(text || "").split(/\n{2,}/);
  return blocks.map((block, i) => {
    const b = block.trim();
    if (!b) return null;

    const heading = b.match(/^(#{1,4})\s+(.*)$/s);
    if (heading) {
      const level = heading[1].length;
      const size = level === 1 ? "text-[26px]" : level === 2 ? "text-[20px]" : "text-[16px]";
      return (
        <h2 key={i} className={`obx-site-display mt-10 first:mt-0 ${size} text-white`}>
          {inline(heading[2])}
        </h2>
      );
    }

    const lines = b.split("\n");
    if (lines.every((l) => /^\s*[-*]\s+/.test(l))) {
      return (
        <ul key={i} className="mt-4 space-y-2">
          {lines.map((l, n) => (
            <li key={n} className="flex gap-3 text-[15px] leading-[1.85] text-ash">
              <span className="mt-[11px] h-px w-3 shrink-0 bg-white/30" />
              <span>{inline(l.replace(/^\s*[-*]\s+/, ""))}</span>
            </li>
          ))}
        </ul>
      );
    }

    return (
      <p key={i} className="mt-4 text-[15px] leading-[1.85] text-ash">
        {inline(b)}
      </p>
    );
  });
}

function inline(text) {
  return String(text).split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    /^\*\*[^*]+\*\*$/.test(part)
      ? <strong key={i} className="font-semibold text-white">{part.slice(2, -2)}</strong>
      : part
  );
}

export default function PublicPolicies() {
  const { slug } = useParams();
  const [index, setIndex] = useState(null);
  const [doc, setDoc] = useState(null);

  // The same layer the front page runs on: inertial scroll, the cursor and
  // its field. A legal page that scrolls and feels like a different product
  // is a legal page that looks like it was bolted on.
  useSmoothScroll();
  const scrolled = useScrolledPast(8);

  useEffect(() => {
    api.get("/public/policies").then(({ data }) => setIndex(data)).catch(() => setIndex([]));
  }, []);

  useEffect(() => {
    if (!slug) { setDoc(null); return; }
    setDoc(undefined);
    api.get(`/public/policies/${slug}`).then(({ data }) => setDoc(data)).catch(() => setDoc(false));
  }, [slug]);

  return (
    <div className="obx-site relative min-h-[100dvh] text-foreground" data-testid="public-policies">
      <div aria-hidden className="obx-grid" />
      <SiteCursor />
      <CursorField />

      <header
        className={`sticky top-0 z-50 transition-colors duration-500 ${
          scrolled ? "border-b border-white/[0.07] bg-white/[0.025] backdrop-blur-xl" : ""
        }`}
      >
        <div className="mx-auto flex h-[68px] w-full max-w-[1180px] items-center gap-4 px-6 sm:px-10">
          <Link to="/" className="obx-site-display text-[15px] tracking-[-0.02em] text-white">
            OBRINEX
          </Link>
          <span className="obx-site-mono hidden text-[10px] text-graphite sm:block">CRM</span>
          <Link
            to="/login"
            className="obx-site-mono ml-auto rounded-full border border-white/25 px-5 py-2.5 text-[10px] text-white transition-colors duration-500 hover:border-white/60"
          >
            Sign in
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1180px] px-6 py-16 sm:px-10 sm:py-24">
        {!slug ? (
          <>
            <Rise><p className="obx-site-mono text-[10px] text-graphite">Legal</p></Rise>
            <Rise delay={0.08}>
              <h1 className="obx-site-display mt-4 text-[clamp(1.9rem,4.4vw,3.4rem)] text-white">
                Policies
              </h1>
            </Rise>
            <Rise delay={0.16}>
              <p className="mt-5 max-w-[52ch] text-[15px] leading-[1.8] text-ash">
                Everything that governs working with Obrinex, in full and without an account.
              </p>
            </Rise>

            {index === null ? (
              <Skeleton className="mt-12 h-64 w-full rounded-2xl bg-surface-1" />
            ) : (
              <div className="mt-12 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                {index.map((p, i) => (
                  <Rise key={p.slug} delay={0.05 + (i % 3) * 0.08}>
                    <Link
                      to={`/policies/${p.slug}`}
                      data-cursor="Read"
                      className="obx-glass obx-lift obx-sheen flex h-full items-center gap-3 rounded-2xl p-5"
                    >
                      <FileText className="h-4 w-4 shrink-0 text-primary" strokeWidth={1.5} />
                      <span className="text-[15px] text-white">{p.title}</span>
                    </Link>
                  </Rise>
                ))}
              </div>
            )}
          </>
        ) : (
          <>
            <Link
              to="/policies"
              className="obx-site-mono flex w-fit items-center gap-2 text-[10px] text-graphite transition-colors duration-300 hover:text-white"
            >
              <ArrowLeft className="h-3 w-3" /> All policies
            </Link>

            {doc === undefined && <Skeleton className="mt-10 h-96 w-full rounded-2xl bg-surface-1" />}
            {doc === false && (
              <p className="mt-10 text-[15px] text-graphite">
                That policy could not be found. <Link to="/policies" className="text-primary underline">See all policies</Link>.
              </p>
            )}
            {doc && (
              <article className="mt-8 max-w-[70ch]">
                <Rise>
                  <h1 className="obx-site-display text-[clamp(1.9rem,4.4vw,3rem)] text-white">
                    {doc.title}
                  </h1>
                </Rise>
                <Rise delay={0.1}>
                  <div className="mt-10">
                    <Markdown text={doc.content} />
                  </div>
                </Rise>
              </article>
            )}
          </>
        )}
      </main>

      <SiteFooter />
    </div>
  );
}

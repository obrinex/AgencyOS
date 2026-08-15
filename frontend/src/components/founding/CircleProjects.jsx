import { useEffect, useState } from "react";
import { FolderKanban, ArrowUpRight } from "lucide-react";
import api from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

/** What the circle is building — every member's listed work, in one place.
 *
 *  Reads as a board rather than a feed. The owner's name is the smaller line
 *  because the question this page answers is "what exists", and the directory
 *  is one tap away for "who".
 */

function hueOf(text = "") {
  let h = 0;
  for (let i = 0; i < text.length; i += 1) h = (h * 31 + text.charCodeAt(i)) % 360;
  return h;
}

export default function CircleProjects() {
  const [rows, setRows] = useState(null);

  useEffect(() => {
    api.get("/founding/projects").then(({ data }) => setRows(data)).catch(() => setRows([]));
  }, []);

  if (!rows) return <Skeleton className="h-64 w-full rounded-2xl bg-surface-1" />;

  if (rows.length === 0) {
    return (
      <div className="obx-glass rounded-2xl px-6 py-14 text-center" data-testid="founding-projects">
        <div className="obx-holo obx-glass relative mx-auto flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl">
          <FolderKanban className="relative z-10 h-5 w-5 text-primary" />
        </div>
        <p className="mt-4 text-sm">Nothing listed yet.</p>
        <p className="mx-auto mt-1 max-w-xs text-xs text-graphite">
          Add what you&apos;re building under Profile and it appears here for the
          rest of the circle.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="founding-projects">
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
        What the circle is building · {rows.length}
      </p>

      <div className="grid gap-3 md:grid-cols-2">
        {rows.map((p, i) => {
          const hue = hueOf(p.title || "");
          return (
            <article
              key={`${p.owner_id}-${i}`}
              style={{ animationDelay: `${i * 45}ms` }}
              data-testid={`founding-project-${i}`}
              className="obx-glass obx-lift obx-sheen obx-reveal group relative overflow-hidden rounded-2xl p-4 sm:p-5"
            >
              {/* A coloured edge derived from the title, so a board of a dozen
                  projects is scannable without anyone picking colours. */}
              <span
                className="absolute inset-y-0 left-0 w-[2px]"
                style={{ background: `linear-gradient(hsl(${hue} 70% 60% / 0.9), transparent)` }}
              />

              <div className="flex items-start justify-between gap-3">
                <h3 className="font-display text-base font-semibold leading-snug tracking-tight">
                  {p.title}
                </h3>
                {p.status && (
                  <span className="shrink-0 rounded-full border border-white/12 bg-white/[0.04] px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em] text-ash">
                    {p.status}
                  </span>
                )}
              </div>

              {p.summary && (
                <p className="mt-2 text-sm leading-relaxed text-graphite">{p.summary}</p>
              )}

              <div className="mt-4 flex items-center gap-2 border-t border-white/[0.07] pt-3 text-[11px]">
                <span className="truncate text-ash">{p.owner}</span>
                {p.owner_company && (
                  <span className="truncate text-carbon">· {p.owner_company}</span>
                )}
                {p.link && (
                  <a
                    href={p.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-auto flex shrink-0 items-center gap-1 text-primary transition-transform hover:translate-x-0.5"
                  >
                    Open <ArrowUpRight className="h-3 w-3" />
                  </a>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

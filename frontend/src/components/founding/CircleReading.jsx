import { useState } from "react";
import { ChevronDown, BookOpen, Compass } from "lucide-react";
import { GUIDELINES, FAQ } from "@/pages/founding/foundingContent";

/** The two text-only sections: how the room works, and what people ask.
 *
 *  Kept together because they are the same object — prose a member reads once
 *  and returns to rarely — and because a numbered guideline reads better beside
 *  a numbered guideline than beside a chat box.
 */

export function Guidelines() {
  return (
    <div className="space-y-3" data-testid="founding-guidelines">
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
        How this room works
      </p>
      {GUIDELINES.map((g, i) => (
        <article
          key={g.title}
          style={{ animationDelay: `${i * 50}ms` }}
          className="obx-glass obx-sheen obx-reveal relative overflow-hidden rounded-2xl p-4 sm:p-5"
        >
          <span className="obx-figure absolute right-4 top-3 font-mono text-3xl font-bold text-white/[0.045] sm:text-4xl">
            {String(i + 1).padStart(2, "0")}
          </span>
          <h3 className="relative font-display font-semibold tracking-tight">{g.title}</h3>
          <p className="relative mt-2 max-w-prose text-sm leading-relaxed text-ash">{g.body}</p>
        </article>
      ))}
    </div>
  );
}

function Question({ q, a, index }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      style={{ animationDelay: `${index * 40}ms` }}
      className="obx-glass obx-reveal overflow-hidden rounded-2xl"
    >
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-white/[0.03]"
      >
        <span className="flex-1 text-sm font-medium">{q}</span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-carbon transition-transform duration-200 ${open ? "rotate-180 text-primary" : ""}`}
        />
      </button>
      {/* Grid-rows rather than max-height, so the animation is exactly as long
          as the answer is and never clips a long one. */}
      <div
        className="grid transition-[grid-template-rows] duration-300 ease-out"
        style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
      >
        <div className="overflow-hidden">
          <p className="max-w-prose px-4 pb-4 text-sm leading-relaxed text-ash">{a}</p>
        </div>
      </div>
    </div>
  );
}

export function Help({ onReplayTour }) {
  return (
    <div className="space-y-2.5" data-testid="founding-help">
      <div className="flex items-center gap-2">
        <BookOpen className="h-3.5 w-3.5 text-primary" />
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
          Questions people actually ask
        </p>
      </div>
      {FAQ.map((f, i) => (
        <Question key={f.q} q={f.q} a={f.a} index={i} />
      ))}

      {/* The tour is one tap from here rather than gone forever. Someone who
          skimmed it on their first visit should not have to clear site data. */}
      {onReplayTour && (
        <button
          onClick={onReplayTour}
          data-testid="founding-help-replay-tour"
          className="obx-glass obx-lift obx-sheen flex w-full items-center gap-2.5 rounded-2xl px-4 py-3.5 text-left"
        >
          <Compass className="h-4 w-4 shrink-0 text-primary" />
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium">Show me around again</span>
            <span className="mt-0.5 block text-xs text-graphite">
              Replays the five-card guide you saw on your first visit.
            </span>
          </span>
        </button>
      )}
    </div>
  );
}

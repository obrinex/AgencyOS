import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Swap } from "@/components/motion";
import { ArrowRight, ArrowLeft, X } from "lucide-react";
import { usePortal } from "@/contexts/PortalContext";

/** The guide, shown once the first time someone opens their portal.
 *
 *  A card sequence rather than spotlights cut out of the live page. Spotlight
 *  tours have to find and measure a real element on every step, which breaks
 *  the moment a nav item is behind a phone tab bar, inside a drawer, or simply
 *  not rendered at the current breakpoint — and this portal has three different
 *  navigation shapes. A sequence explains the same thing and cannot point at
 *  something that isn't there.
 *
 *  Dismissable at any point, and replayable from Help afterwards, because a
 *  tour you cannot get back is a tour people skip nervously rather than read.
 */

const EASE = [0.16, 1, 0.3, 1];

export default function PortalTour({ steps, title }) {
  const { markGuideSeen } = usePortal();
  const [index, setIndex] = useState(0);
  const [direction, setDirection] = useState(1);

  const step = steps[index];
  const last = index === steps.length - 1;

  // Both move by a functional update, so neither closes over a stale index and
  // the key handler below can be bound once for the life of the tour.
  const next = () => {
    setDirection(1);
    setIndex((i) => (i >= steps.length - 1 ? (markGuideSeen(), i) : i + 1));
  };
  const back = () => {
    setDirection(-1);
    setIndex((i) => Math.max(0, i - 1));
  };

  // The page behind must not scroll under a finger meant for the card.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") markGuideSeen();
      if (e.key === "ArrowRight") next();
      if (e.key === "ArrowLeft") back();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="fixed inset-0 z-[90] flex items-end justify-center sm:items-center" data-testid="portal-tour">
      <motion.button
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        aria-label="Close the guide"
        onClick={markGuideSeen}
        className="absolute inset-0 bg-black/80 backdrop-blur-md"
      />

      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.45, ease: EASE }}
        className="obx-glass pb-safe relative z-10 w-full max-w-lg overflow-hidden rounded-t-3xl sm:rounded-3xl"
      >
        <div className="obx-aurora pointer-events-none absolute inset-0" />

        <div className="relative z-10 p-5 sm:p-7">
          <div className="mb-5 flex items-center gap-3">
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
              {title}
            </p>
            <span className="obx-figure ml-auto font-mono text-[11px] text-carbon">
              {String(index + 1).padStart(2, "0")} / {String(steps.length).padStart(2, "0")}
            </span>
            <button
              onClick={markGuideSeen}
              aria-label="Close the guide"
              data-testid="portal-tour-close"
              className="flex h-7 w-7 items-center justify-center rounded-lg text-carbon transition-colors hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="min-h-[13rem] sm:min-h-[11rem]">
            <Swap swapKey={index} direction={direction} duration={0.46}>
              <div>
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/12 text-primary ring-1 ring-primary/30">
                  <step.icon className="h-5 w-5" />
                </div>
                <h2 className="mt-4 font-display text-xl font-bold leading-tight tracking-tight sm:text-2xl">
                  {step.title}
                </h2>
                <p className="mt-2 max-w-prose text-sm leading-relaxed text-ash">{step.body}</p>
              </div>
            </Swap>
          </div>

          <div className="mt-6 flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              {steps.map((_, i) => (
                <button
                  key={i}
                  aria-label={`Step ${i + 1}`}
                  onClick={() => { setDirection(i > index ? 1 : -1); setIndex(i); }}
                  className="p-1"
                >
                  <motion.span
                    className="block h-1.5 rounded-full"
                    initial={false}
                    animate={{
                      width: i === index ? 18 : 6,
                      backgroundColor:
                        i === index ? "hsl(190 100% 50%)" : "rgba(255,255,255,0.16)",
                    }}
                    transition={{ duration: 0.3, ease: EASE }}
                  />
                </button>
              ))}
            </div>

            <button
              onClick={back}
              disabled={index === 0}
              className="ml-auto flex items-center gap-1.5 rounded-xl px-2.5 py-2 text-sm text-graphite transition-colors hover:text-foreground disabled:pointer-events-none disabled:opacity-30"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Back
            </button>
            <button
              onClick={next}
              data-testid="portal-tour-next"
              className="flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-background"
            >
              {last ? "Start using it" : "Next"}
              {!last && <ArrowRight className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

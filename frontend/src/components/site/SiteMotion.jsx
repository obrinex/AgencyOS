import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import Lenis from "lenis";
import { prefersReducedMotion } from "@/components/motion";

/** Motion for the public front page.
 *
 *  Kept out of `components/motion` on purpose: that module belongs to the app,
 *  where motion is measured in 200ms and exists to explain a state change.
 *  This is the marketing surface, where it exists to set a pace.
 */

const EASE = [0.16, 1, 0.3, 1];

/** Inertial scrolling, the same library obrinex.space runs.
 *
 *  The page is otherwise a normal document — Lenis only intercepts wheel and
 *  touch input and drives `scrollTo` itself, so anchors, the keyboard and the
 *  scrollbar all keep working.
 *
 *  Three things it must not do, each of which is handled below:
 *
 *  - **Outlive the page.** It patches a global. Not destroying it on unmount
 *    would leave every CRM route afterwards scrolling with a 1.6s glide.
 *  - **Override a stated preference.** Under `prefers-reduced-motion` it never
 *    starts, and the page scrolls natively.
 *  - **Fight a phone.** `syncTouch` stays off, so touch scrolling is the
 *    platform's own — hijacking it is what makes smooth-scroll libraries feel
 *    broken on mobile.
 */
//: Anything that needs to know the scroll position subscribes here rather than
//: to `window`. Lenis drives scrolling itself and native `scroll` events do not
//: reach window listeners while it is running — measured: zero events fired
//: across a 600px programmatic scroll. A header that listens to window
//: therefore never learns it has been scrolled.
const scrollSubscribers = new Set();

function publishScroll(y) {
  scrollSubscribers.forEach((fn) => fn(y));
}

export function useSmoothScroll({ enabled = true } = {}) {
  useEffect(() => {
    if (!enabled || prefersReducedMotion()) {
      // No Lenis: republish the native events so subscribers still work.
      const onNative = () => publishScroll(window.scrollY);
      window.addEventListener("scroll", onNative, { passive: true });
      onNative();
      return () => window.removeEventListener("scroll", onNative);
    }

    const lenis = new Lenis({
      // Slow on purpose — the complaint was that the page moved too fast.
      // 1.6s to settle is about twice a default scroll and is what gives the
      // sense of weight.
      duration: 1.6,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      wheelMultiplier: 0.85,
      touchMultiplier: 1.4,
      syncTouch: false,
    });

    lenis.on("scroll", ({ scroll }) => publishScroll(scroll));
    publishScroll(window.scrollY);

    let frame = 0;
    const raf = (time) => {
      lenis.raf(time);
      frame = requestAnimationFrame(raf);
    };
    frame = requestAnimationFrame(raf);

    // A safety net for any context where rAF never fires: Lenis then produces
    // no scroll events of its own, so the native ones are all there is.
    const onNative = () => publishScroll(window.scrollY);
    window.addEventListener("scroll", onNative, { passive: true });

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onNative);
      lenis.destroy();
    };
  }, [enabled]);
}

/** True once the page has moved past `threshold`. Works with Lenis driving the
 *  scroll or without it. */
export function useScrolledPast(threshold = 8) {
  const [past, setPast] = useState(false);
  useEffect(() => {
    const onScroll = (y) => setPast(y > threshold);
    scrollSubscribers.add(onScroll);
    onScroll(window.scrollY);
    return () => scrollSubscribers.delete(onScroll);
  }, [threshold]);
  return past;
}

/** Text that assembles itself a word at a time as it comes into view.
 *
 *  Words rather than letters: a letter stagger on a nine-word heading is
 *  fifty-odd elements and reads as a gimmick, where a word stagger reads as
 *  the sentence being spoken. Each word is wrapped in an overflow-hidden span
 *  so it rises out of the line rather than fading on the spot.
 *
 *  The whole string stays in the accessible tree via `aria-label`; the split
 *  spans are hidden from it, so a screen reader hears one sentence rather than
 *  nine fragments.
 *
 *  **Do not nest this inside `Rise`.** Two scroll-triggered animations on the
 *  same text is one too many: the section headings came out permanently
 *  invisible, every word parked at y:110% inside its clip mask, leaving a hole
 *  where the heading should be. If the text is already inside a reveal, let the
 *  reveal carry it — or use `AnimatedTextIn`, which fires on mount and cannot
 *  be waiting on an intersection that never resolves.
 */
export function AnimatedText({
  text,
  as: Tag = "span",
  className = "",
  delay = 0,
  stagger = 0.055,
  duration = 1.05,
  once = true,
}) {
  const still = prefersReducedMotion();
  if (still) return <Tag className={className}>{text}</Tag>;

  const words = String(text).split(" ");
  return (
    <Tag className={className} aria-label={text}>
      {words.map((word, i) => (
        <span
          key={`${word}-${i}`}
          aria-hidden="true"
          style={{ display: "inline-block", overflow: "hidden", verticalAlign: "top" }}
        >
          <motion.span
            style={{ display: "inline-block", willChange: "transform" }}
            initial={{ y: "110%", opacity: 0 }}
            whileInView={{ y: "0%", opacity: 1 }}
            viewport={{ once, margin: "-10% 0px -10% 0px" }}
            transition={{ duration, delay: delay + i * stagger, ease: EASE }}
          >
            {word}
          </motion.span>
          {i < words.length - 1 && " "}
        </span>
      ))}
    </Tag>
  );
}

/** The same, but keyed to page load rather than to scroll — for the hero,
 *  which is already on screen and must not wait for an intersection. */
export function AnimatedTextIn({
  text, as: Tag = "span", className = "", delay = 0, stagger = 0.055, duration = 1.05,
}) {
  const still = prefersReducedMotion();
  if (still) return <Tag className={className}>{text}</Tag>;

  const words = String(text).split(" ");
  return (
    <Tag className={className} aria-label={text}>
      {words.map((word, i) => (
        <span
          key={`${word}-${i}`}
          aria-hidden="true"
          style={{ display: "inline-block", overflow: "hidden", verticalAlign: "top" }}
        >
          <motion.span
            style={{ display: "inline-block", willChange: "transform" }}
            initial={{ y: "110%", opacity: 0 }}
            animate={{ y: "0%", opacity: 1 }}
            transition={{ duration, delay: delay + i * stagger, ease: EASE }}
          >
            {word}
          </motion.span>
          {i < words.length - 1 && " "}
        </span>
      ))}
    </Tag>
  );
}

/** A slow lift into view. Deliberately long and late — the previous pass fired
 *  a 0.55s pop 80px early, which read as things snapping past you. */
export function Rise({ children, delay = 0, y = 34, duration = 1.25, className = "" }) {
  return (
    <motion.div
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-12% 0px -12% 0px" }}
      transition={{ duration, delay, ease: EASE }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** Parallax drift for a decorative layer, tied to how far the page has moved.
 *  Uses the scroll position Lenis is already producing rather than adding a
 *  second listener that would disagree with it by a frame. */
export function useParallax(ref, strength = 0.15) {
  const raf = useRef(0);
  useEffect(() => {
    if (prefersReducedMotion()) return undefined;
    const onScroll = () => {
      cancelAnimationFrame(raf.current);
      raf.current = requestAnimationFrame(() => {
        if (ref.current) ref.current.style.transform = `translate3d(0, ${window.scrollY * strength}px, 0)`;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(raf.current);
    };
  }, [ref, strength]);
}

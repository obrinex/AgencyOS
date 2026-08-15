import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * The motion vocabulary shared with obrinex.space, translated for a tool.
 *
 * The website's toolkit — smooth scroll, scroll choreography, full-viewport
 * canvases, a preloader — is deliberately absent. All of it is delightful once
 * and an obstacle by the fortieth time you open the same page to check an
 * invoice. What carries the identity without costing anything is smaller:
 * things arrive rather than blink, numbers count rather than jump, and controls
 * acknowledge the pointer.
 *
 * House rule for everything here: nothing exceeds ~400ms, nothing blocks input,
 * and every effect has a still final state so `prefers-reduced-motion` can turn
 * it off without leaving the page broken.
 */

/** Someone who asked their OS for less motion means it. */
export function prefersReducedMotion() {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Fade-and-rise on first paint, or when the element scrolls into view.
 *
 * `delay` is in milliseconds and meant to be small — a list of eight cards
 * staggered 30ms apart reads as arriving in order; staggered 150ms apart reads
 * as a slideshow you have to wait for.
 */
export function Reveal({
  children,
  delay = 0,
  as: Tag = "div",
  className,
  onView = false,
  ...rest
}) {
  const ref = useRef(null);
  const [shown, setShown] = useState(!onView);

  useEffect(() => {
    if (!onView || shown) return;
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -10% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [onView, shown]);

  return (
    <Tag
      ref={ref}
      className={cn(shown && "obx-reveal", className)}
      style={shown && delay ? { animationDelay: `${delay}ms` } : undefined}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/**
 * A number that counts to its value instead of snapping to it.
 *
 * Only worth it on figures someone is meant to register — revenue, seats,
 * overdue totals. On a table cell it is noise, and on anything that updates
 * every few seconds it never settles.
 *
 * Counts on change as well as on mount, so a dashboard refresh shows the
 * movement rather than silently swapping one number for another.
 */
export function CountUp({ value, duration = 650, format, className }) {
  const [shown, setShown] = useState(value);
  const fromRef = useRef(value);
  const rafRef = useRef(0);

  useEffect(() => {
    const target = Number(value) || 0;
    const from = Number(fromRef.current) || 0;
    fromRef.current = target;

    if (prefersReducedMotion() || from === target) {
      setShown(target);
      return;
    }

    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      // Ease-out cubic: fast enough to feel responsive, settled enough at the
      // end that the final digit doesn't appear to hesitate.
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(from + (target - from) * eased);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [value, duration]);

  const rounded = Math.round(shown);
  return (
    <span className={className}>{format ? format(rounded) : rounded.toLocaleString()}</span>
  );
}

/**
 * A control that leans very slightly toward the pointer.
 *
 * Ported from the site's magnetic buttons at about a third of the pull. On a
 * hero it can move 12px and feel alive; on a toolbar it would mean the button
 * is never quite where you aimed, so it moves barely enough to notice and
 * snaps back the moment you leave.
 *
 * Disabled entirely on coarse pointers — there is no hover on a touchscreen,
 * and the transform would only fight the tap.
 */
export function Magnetic({ children, strength = 4, className, ...rest }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (prefersReducedMotion()) return;
    if (window.matchMedia("(hover: none), (pointer: coarse)").matches) return;

    const onMove = (e) => {
      const r = el.getBoundingClientRect();
      const x = (e.clientX - (r.left + r.width / 2)) / (r.width / 2);
      const y = (e.clientY - (r.top + r.height / 2)) / (r.height / 2);
      el.style.transform = `translate3d(${x * strength}px, ${y * strength}px, 0)`;
    };
    const onLeave = () => {
      el.style.transform = "";
    };

    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [strength]);

  return (
    <span
      ref={ref}
      className={cn("inline-block transition-transform duration-300 ease-out", className)}
      {...rest}
    >
      {children}
    </span>
  );
}

/**
 * The page-change transition: a short fade-and-rise keyed on the route.
 *
 * Deliberately 180ms. Long enough that a navigation reads as a change of place
 * rather than a repaint; short enough that someone moving quickly through the
 * app never waits for it. Anything longer and the app feels slower than it is,
 * which is the usual failure of page transitions in tools.
 */
export function PageTransition({ routeKey, children }) {
  return (
    <div key={routeKey} className="obx-page-in">
      {children}
    </div>
  );
}

/** Swap one panel for another, without AnimatePresence.
 *
 *  Changing `swapKey` remounts the child, which animates in; the outgoing one
 *  simply unmounts. There is no exit animation, so nothing has to coordinate
 *  and nothing can be left half-transitioned — the panel is either the old one
 *  or the new one, never a stalled blend of both.
 *
 *  Chosen over `AnimatePresence mode="wait"` for robustness rather than
 *  because that was broken: exits there are driven by requestAnimationFrame,
 *  which does not fire in a page the browser never composites (a headless or
 *  hidden tab). Under those conditions `mode="wait"` holds the outgoing child
 *  forever and the incoming one never mounts, which makes a tour or a tab
 *  switch look completely dead. This pattern degrades to an instant, correct
 *  swap instead — worth the loss of an exit animation nobody watches.
 *
 *  `direction` (-1 | 1) slides the entrance from the correct side, so Back
 *  still reads as going back.
 */
export function Swap({ swapKey, direction = 1, distance = 24, duration = 0.42, className, children }) {
  const still = prefersReducedMotion();
  return (
    <motion.div
      key={swapKey}
      initial={still ? false : { opacity: 0, x: direction * distance }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: still ? 0 : duration, ease: [0.16, 1, 0.3, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** The same idea on the vertical axis, for content that replaces itself in
 *  place rather than sliding through a sequence. */
export function SwapUp({ swapKey, distance = 12, duration = 0.4, className, children }) {
  const still = prefersReducedMotion();
  return (
    <motion.div
      key={swapKey}
      initial={still ? false : { opacity: 0, y: distance }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: still ? 0 : duration, ease: [0.16, 1, 0.3, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

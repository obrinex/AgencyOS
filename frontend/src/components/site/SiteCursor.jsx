import { useEffect, useRef, useState } from "react";

/** The website's cursor, ported.
 *
 *  An opaque blob drawn through `mix-blend-difference`: over dark ground it
 *  reads white, and over anything light it inverts what is under it, so it is
 *  visible everywhere without needing to know what it is over. It swells on
 *  anything interactive and surfaces that element's `data-cursor` label.
 *
 *  ## Why the native cursor is hidden, and when it comes back
 *
 *  `cursor: none` on the document, restored on unmount. That restore matters
 *  more than it looks: this only mounts on the public front page, and leaving
 *  the app with no visible cursor because a marketing page forgot to clean up
 *  after itself would be the worst bug on this list.
 *
 *  Nothing mounts on touch (there is no cursor to replace) or under
 *  `prefers-reduced-motion` — a blob that lags behind the pointer is exactly
 *  the sort of motion that setting is asking not to see.
 */

const lerp = (a, b, t) => a + (b - a) * t;

export default function SiteCursor() {
  const blob = useRef(null);
  const [label, setLabel] = useState("");
  const [grow, setGrow] = useState(false);
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    const touch = window.matchMedia("(hover: none), (pointer: coarse)").matches;
    if (touch || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return undefined;
    }
    setEnabled(true);
    const previousCursor = document.documentElement.style.cursor;
    document.documentElement.style.cursor = "none";

    const target = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
    const pos = { ...target };
    let raf = 0;

    const onMove = (e) => {
      target.x = e.clientX;
      target.y = e.clientY;
      const el = e.target?.closest?.("[data-cursor], a, button, [role='button']");
      if (el) {
        setLabel(el.getAttribute("data-cursor") ?? "");
        setGrow(true);
      } else {
        setLabel("");
        setGrow(false);
      }
    };

    const render = () => {
      // Snappy enough to feel precise, soft enough to feel alive.
      pos.x = lerp(pos.x, target.x, 0.35);
      pos.y = lerp(pos.y, target.y, 0.35);
      if (blob.current) {
        blob.current.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0)`;
      }
      raf = requestAnimationFrame(render);
    };
    raf = requestAnimationFrame(render);
    window.addEventListener("mousemove", onMove);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("mousemove", onMove);
      document.documentElement.style.cursor = previousCursor;
    };
  }, []);

  if (!enabled) return null;

  const size = grow ? (label ? 108 : 84) : 16;

  return (
    <div
      aria-hidden="true"
      data-testid="site-cursor"
      className="pointer-events-none fixed inset-0 z-[110] mix-blend-difference"
    >
      <div
        ref={blob}
        className="absolute left-0 top-0 flex items-center justify-center rounded-full bg-white text-black transition-[width,height,margin] duration-300 ease-out will-change-transform"
        style={{ width: size, height: size, marginLeft: -size / 2, marginTop: -size / 2 }}
      >
        {label && grow && (
          <span className="obx-site-mono select-none text-center text-[10px] font-normal leading-tight text-black">
            {label}
          </span>
        )}
      </div>
    </div>
  );
}

/** The soft field that trails the pointer, well behind the content.
 *
 *  The site's `BackgroundGradientAnimation` in its interactive mode: one large
 *  radial blob chasing the pointer at a deliberately low 0.06 lerp, so it
 *  arrives about a second late. That lag is the whole effect — matched to the
 *  cursor it would just be a glow stuck to the pointer, where lagging it reads
 *  as light moving through the room.
 *
 *  Sits at `-z-10`, above the app's ground and below everything else.
 */
export function CursorField({ color = "0, 207, 255", opacity = 0.5 }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    if (window.matchMedia("(hover: none), (pointer: coarse)").matches) return undefined;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;

    let tgX = window.innerWidth / 2;
    let tgY = window.innerHeight / 2;
    let curX = tgX;
    let curY = tgY;
    let raf = 0;

    const onMove = (e) => { tgX = e.clientX; tgY = e.clientY; };
    const render = () => {
      curX += (tgX - curX) * 0.06;
      curY += (tgY - curY) * 0.06;
      el.style.transform = `translate3d(${Math.round(curX)}px, ${Math.round(curY)}px, 0)`;
      raf = requestAnimationFrame(render);
    };
    raf = requestAnimationFrame(render);
    window.addEventListener("mousemove", onMove, { passive: true });

    // One placement immediately, so the field is where the pointer is before
    // the first frame — and is placed at all in contexts with no frames.
    el.style.transform = `translate3d(${Math.round(curX)}px, ${Math.round(curY)}px, 0)`;

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("mousemove", onMove);
    };
  }, []);

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div
        ref={ref}
        data-testid="cursor-field"
        className="absolute -left-1/2 -top-1/2 h-full w-full will-change-transform"
        style={{
          opacity,
          background: `radial-gradient(circle at center, rgba(${color}, 0.42) 0, rgba(${color}, 0) 50%) no-repeat`,
        }}
      />
    </div>
  );
}

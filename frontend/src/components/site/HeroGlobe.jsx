import { useEffect, useRef } from "react";
import { prefersReducedMotion } from "@/components/motion";

/** A slowly turning globe of points, behind the hero lockup.
 *
 *  Canvas rather than SVG or DOM: this is ~1,500 dots redrawn every frame, and
 *  1,500 elements with transforms would spend the whole budget on layout. One
 *  canvas costs one composite.
 *
 *  No dependency. A globe is a sphere, a rotation and an orthographic
 *  projection — three lines of trigonometry — and pulling in a WebGL library
 *  for that would be 200KB to draw dots.
 *
 *  ## How the points are placed
 *
 *  A Fibonacci sphere. Stepping latitude and longitude uniformly bunches points
 *  at the poles and leaves the equator sparse, which reads as a wireframe globe
 *  with a bald middle. The golden-angle spiral spaces them evenly over the
 *  surface, so the density you see is the density everywhere.
 *
 *  ## What it must not do
 *
 *  - **Outshout the words.** It sits behind the lockup at low alpha and fades
 *    at the edges; it is light in the room, not a diagram.
 *  - **Run when nobody is looking.** The loop stops when the tab is hidden and
 *    when the hero scrolls out of view — a globe spinning behind three screens
 *    of copy is a laptop fan for nothing.
 *  - **Move when asked not to.** Under `prefers-reduced-motion` it draws one
 *    still frame and never starts the loop.
 */

const POINTS = 1500;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

export default function HeroGlobe({ className = "" }) {
  const canvasRef = useRef(null);
  const wrapRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return undefined;
    const ctx = canvas.getContext("2d");
    const still = prefersReducedMotion();

    // Unit sphere, built once.
    const pts = new Array(POINTS);
    for (let i = 0; i < POINTS; i += 1) {
      const y = 1 - (i / (POINTS - 1)) * 2;
      const radius = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = GOLDEN_ANGLE * i;
      pts[i] = { x: Math.cos(theta) * radius, y, z: Math.sin(theta) * radius };
    }

    let width = 0;
    let height = 0;
    let dpr = 1;

    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = rect.width;
      height = rect.height;
      canvas.width = Math.max(1, Math.floor(width * dpr));
      canvas.height = Math.max(1, Math.floor(height * dpr));
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();

    const draw = (angle) => {
      ctx.clearRect(0, 0, width, height);
      if (!width || !height) return;

      const cx = width / 2;
      const cy = height / 2;
      const r = Math.min(width, height) * 0.42;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      // A slight tilt, so it reads as a globe seen from just above the equator
      // rather than as a flat ring of dots.
      const tilt = -0.42;
      const cosT = Math.cos(tilt);
      const sinT = Math.sin(tilt);

      for (let i = 0; i < POINTS; i += 1) {
        const p = pts[i];
        // Spin about Y, then tilt about X.
        const x1 = p.x * cos - p.z * sin;
        const z1 = p.x * sin + p.z * cos;
        const y2 = p.y * cosT - z1 * sinT;
        const z2 = p.y * sinT + z1 * cosT;

        // Orthographic: z only decides depth cueing, never position, which is
        // what keeps the silhouette a clean circle.
        const sx = cx + x1 * r;
        const sy = cy + y2 * r;

        // Front hemisphere bright, back hemisphere barely there.
        const depth = (z2 + 1) / 2;
        const alpha = 0.06 + depth * depth * 0.5;
        const size = 0.5 + depth * 1.25;

        ctx.beginPath();
        ctx.arc(sx, sy, size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(0, 207, 255, ${alpha.toFixed(3)})`;
        ctx.fill();
      }
    };

    if (still) {
      draw(0.6);
      const onResize = () => { resize(); draw(0.6); };
      window.addEventListener("resize", onResize);
      return () => window.removeEventListener("resize", onResize);
    }

    let frame = 0;
    let angle = 0.6;
    let last = 0;
    let visible = true;
    let onScreen = true;

    const loop = (time) => {
      const dt = last ? Math.min(time - last, 64) : 16;
      last = time;
      // ~24 seconds a revolution. Slow enough that you notice it only if you
      // look, which is the point.
      angle += (dt / 1000) * ((Math.PI * 2) / 24);
      draw(angle);
      frame = requestAnimationFrame(loop);
    };

    const start = () => {
      if (frame || !visible || !onScreen) return;
      last = 0;
      frame = requestAnimationFrame(loop);
    };
    const stop = () => {
      cancelAnimationFrame(frame);
      frame = 0;
    };

    const observer = new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting;
      if (onScreen) start(); else stop();
    }, { threshold: 0 });
    observer.observe(wrap);

    const onVisibility = () => {
      visible = document.visibilityState === "visible";
      if (visible) start(); else stop();
    };
    document.addEventListener("visibilitychange", onVisibility);

    const onResize = () => resize();
    window.addEventListener("resize", onResize);

    start();
    // One frame immediately, so the globe is there before the first rAF fires
    // — including in contexts where rAF never fires at all.
    draw(angle);

    return () => {
      stop();
      observer.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return (
    <div
      ref={wrapRef}
      aria-hidden="true"
      className={`pointer-events-none absolute ${className}`}
      style={{
        // Fades the globe out before it reaches the edge of the hero, so it
        // never ends on a hard circle against the page.
        WebkitMaskImage: "radial-gradient(circle at 50% 50%, black 42%, transparent 74%)",
        maskImage: "radial-gradient(circle at 50% 50%, black 42%, transparent 74%)",
      }}
    >
      <canvas ref={canvasRef} className="h-full w-full" />
    </div>
  );
}

import { useEffect, useRef } from "react";

/** The halftone dot-trail from obrinex.space, ported to this codebase.
 *
 *  A grid of cells holds an intensity value each. The pointer stamps intensity
 *  into the cells it passes over — a wider, brighter brush the faster it is
 *  moving — and every frame the whole buffer decays. Each cell draws a dot
 *  sized and faded by its own value, so what you see is a wake behind the
 *  cursor rather than a cursor-shaped light.
 *
 *  Ported rather than imported: the original is TSX in a separate Next.js
 *  repo, and this codebase is plain JavaScript by direction. The mechanics and
 *  the prop names are kept identical so the two can be compared side by side.
 *
 *  ## Things it deliberately does not do
 *
 *  - **Run on a phone.** This paints a wake behind a moving pointer, and a
 *    touch device has no pointer — the only movement is a tap or a scroll drag,
 *    so the effect is invisible essentially always. What is not invisible is a
 *    full-screen canvas being cleared sixty times a second to draw nothing.
 *  - **Run when the wake is gone.** When the buffer is empty and the pointer is
 *    elsewhere there is nothing to draw and nothing left to erase, so the frame
 *    is skipped outright. Clearing the canvas is the expensive part.
 *  - **Run when asked not to.** Nothing starts under `prefers-reduced-motion`.
 */
export default function HalftoneTrail({
  className = "",
  cellSize = 12,
  color = "0, 207, 255",
  decay = 0.97,
  brushSize = 0.14,
  hoverBrushSize = 0.05,
  opacity = 0.9,
  hoverOpacity = 0.2,
  speedScale = 30,
}) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;
    if (window.matchMedia("(pointer: coarse)").matches) return undefined;

    let dpr = 1;
    let cols = 0;
    let rows = 0;
    let cell = 0;
    let buffer = new Float32Array(0);

    const setup = () => {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      cell = Math.max(2, cellSize) * dpr;
      cols = Math.ceil(canvas.width / cell);
      rows = Math.ceil(canvas.height / cell);
      buffer = new Float32Array(cols * rows);
    };
    setup();

    const pointer = { x: -1, y: -1, active: false };
    let lastX = -1;
    let lastY = -1;
    let hasLast = false;

    const onMove = (e) => {
      const rect = canvas.getBoundingClientRect();
      const inside =
        e.clientX >= rect.left && e.clientX <= rect.right &&
        e.clientY >= rect.top && e.clientY <= rect.bottom;
      if (!inside) { pointer.active = false; hasLast = false; return; }
      pointer.x = (e.clientX - rect.left) * dpr;
      pointer.y = (e.clientY - rect.top) * dpr;
      pointer.active = true;
      if (!hasLast) { lastX = pointer.x; lastY = pointer.y; hasLast = true; }
    };
    const onLeave = () => { pointer.active = false; hasLast = false; };

    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerout", onLeave, { passive: true });

    /** Paint the pointer's travel since the last frame into the buffer.
     *  Stepped along the segment rather than stamped once at the new position,
     *  or a fast flick leaves a dotted line instead of a stroke. */
    const stamp = () => {
      if (!pointer.active || !hasLast) return;
      const md = Math.min(canvas.width, canvas.height);
      const dx = pointer.x - lastX;
      const dy = pointer.y - lastY;
      const speed = Math.hypot(dx, dy);
      const speedNorm = Math.min(1, (speed * speedScale) / md);
      const radius = (hoverBrushSize + (brushSize - hoverBrushSize) * speedNorm) * md;
      const value = hoverOpacity + (opacity - hoverOpacity) * speedNorm;
      const steps = Math.max(1, Math.ceil(speed / cell));

      for (let s = 0; s <= steps; s += 1) {
        const t = s / steps;
        const sx = lastX + dx * t;
        const sy = lastY + dy * t;
        const c0 = Math.max(0, Math.floor((sx - radius) / cell));
        const c1 = Math.min(cols - 1, Math.floor((sx + radius) / cell));
        const r0 = Math.max(0, Math.floor((sy - radius) / cell));
        const r1 = Math.min(rows - 1, Math.floor((sy + radius) / cell));
        for (let cy = r0; cy <= r1; cy += 1) {
          for (let cx = c0; cx <= c1; cx += 1) {
            const d = Math.hypot(cx * cell + cell / 2 - sx, cy * cell + cell / 2 - sy);
            if (d > radius) continue;
            const fall = 1 - d / radius;
            const add = value * fall * fall;
            const idx = cy * cols + cx;
            if (add > buffer[idx]) buffer[idx] = add;
          }
        }
      }
      lastX = pointer.x;
      lastY = pointer.y;
    };

    let raf = 0;
    let dirty = false;

    const render = () => {
      raf = requestAnimationFrame(render);
      stamp();

      let live = false;
      for (let i = 0; i < buffer.length; i += 1) {
        if (buffer[i] > 0.002) { buffer[i] *= decay; live = true; }
        else if (buffer[i] !== 0) buffer[i] = 0;
      }
      if (!live && !dirty) return;

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      dirty = false;

      const max = cell * 0.46;
      for (let cy = 0; cy < rows; cy += 1) {
        for (let cx = 0; cx < cols; cx += 1) {
          const v = buffer[cy * cols + cx];
          if (v <= 0.002) continue;
          const r = max * Math.min(1, v);
          ctx.beginPath();
          ctx.arc(cx * cell + cell / 2, cy * cell + cell / 2, r, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(${color}, ${Math.min(1, v).toFixed(3)})`;
          ctx.fill();
          dirty = true;
        }
      }
    };
    raf = requestAnimationFrame(render);

    const onResize = () => setup();
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerout", onLeave);
      window.removeEventListener("resize", onResize);
    };
  }, [cellSize, color, decay, brushSize, hoverBrushSize, opacity, hoverOpacity, speedScale]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 h-full w-full ${className}`}
    />
  );
}

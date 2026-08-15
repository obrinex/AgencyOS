/** Ten seats, drawn.
 *
 *  A number ("7 of 10") states the scarcity; ten marks in a row makes you feel
 *  it. That is the whole job of this component and the reason it is a rail
 *  rather than a progress bar — a bar reads as completion, and a filling bar
 *  says "nearly done" where this needs to say "nearly gone".
 */
export default function SeatRail({ taken = 0, total = 10, className = "" }) {
  const filled = Math.max(0, Math.min(taken, total));
  const open = total - filled;

  return (
    <div className={`rounded-xl border border-white/10 bg-surface-1 p-5 ${className}`}
         data-testid="founding-seat-rail">
      <div className="flex items-baseline justify-between gap-4">
        <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-carbon">
          The Circle
        </p>
        <p className="font-mono text-[11px] text-graphite" data-testid="founding-seat-count">
          {filled} taken · {open} open
        </p>
      </div>

      <div className="mt-4 flex items-end gap-1.5" aria-hidden="true">
        {Array.from({ length: total }).map((_, i) => (
          <div
            key={i}
            className={
              i < filled
                ? "h-10 flex-1 rounded-sm bg-foreground"
                : "h-10 flex-1 rounded-sm border border-dashed border-white/15 bg-transparent"
            }
          />
        ))}
      </div>

      <p className="sr-only">{filled} of {total} founding seats taken.</p>

      <p className="mt-3 text-xs text-carbon">
        {open === 0
          ? "Every seat is taken. Returning one frees it for the next round."
          : `${open} ${open === 1 ? "seat remains" : "seats remain"}. Membership is never announced publicly.`}
      </p>
    </div>
  );
}

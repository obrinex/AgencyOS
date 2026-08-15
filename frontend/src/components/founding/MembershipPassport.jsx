import { useEffect, useMemo, useRef, useState } from "react";
import {
  Download, Check, Lock, Ticket, Users, Sparkles, ShieldCheck, Loader2,
} from "lucide-react";
import api from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

/** Your membership: the credential, the journey, and what it entitles you to.
 *
 *  The one place in the product that is an *object* rather than a screen. A
 *  membership that exists only as a row in a table is a subscription; the point
 *  of this page is that a founding member has something they can hold up.
 *
 *  Everything shown here is derived server-side from records that already
 *  existed — nothing about the passport is a second source of truth. See
 *  `GET /api/founding/membership`.
 */

/* ── The sigil ────────────────────────────────────────────────────────────────
   Not a QR code, and deliberately not dressed as one. A QR that scans to
   nothing is a lie told in a font; this is a mark derived from the member
   number itself — the same number always draws the same sigil, and two members
   never share one. Mirrored down the middle so it reads as a crest. */

function hash32(text) {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

const SIGIL_SIZE = 7;

function sigilCells(seed) {
  let state = hash32(seed) || 1;
  const next = () => {
    // xorshift32 — enough randomness for 24 bits of decoration, and it is
    // deterministic across browsers in a way Math.random can never be.
    state ^= state << 13; state >>>= 0;
    state ^= state >>> 17;
    state ^= state << 5; state >>>= 0;
    return state / 0xffffffff;
  };
  const half = Math.ceil(SIGIL_SIZE / 2);
  const grid = [];
  for (let y = 0; y < SIGIL_SIZE; y += 1) {
    const row = new Array(SIGIL_SIZE).fill(false);
    for (let x = 0; x < half; x += 1) {
      const on = next() > 0.45;
      row[x] = on;
      row[SIGIL_SIZE - 1 - x] = on;
    }
    grid.push(row);
  }
  return grid;
}

function Sigil({ seed, className = "" }) {
  const grid = useMemo(() => sigilCells(seed || "OBRINEX"), [seed]);
  return (
    <svg viewBox={`0 0 ${SIGIL_SIZE} ${SIGIL_SIZE}`} className={className} aria-hidden="true">
      {grid.map((row, y) =>
        row.map((on, x) =>
          on ? (
            <rect
              key={`${x}-${y}`}
              x={x + 0.1} y={y + 0.1} width={0.8} height={0.8} rx={0.18}
              fill="currentColor"
              opacity={0.35 + ((x * 7 + y * 3) % 5) * 0.13}
            />
          ) : null
        )
      )}
    </svg>
  );
}

/* ── Tenure ─────────────────────────────────────────────────────────────────── */

function useTenure(joinedAt) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    // Ticks once a second because the card shows seconds. Cheap, and it stops
    // the moment the component unmounts.
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  if (!joinedAt) return null;
  const start = new Date(joinedAt).getTime();
  if (Number.isNaN(start)) return null;
  const elapsed = Math.max(0, now - start);
  const days = Math.floor(elapsed / 86400000);
  const hours = Math.floor((elapsed % 86400000) / 3600000);
  const minutes = Math.floor((elapsed % 3600000) / 60000);
  const seconds = Math.floor((elapsed % 60000) / 1000);
  return { days, hours, minutes, seconds };
}

const DATE_FMT = { day: "2-digit", month: "short", year: "numeric" };

function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleDateString("en-GB", DATE_FMT).toUpperCase();
}

/* ── The card ─────────────────────────────────────────────────────────────── */

function PassportCard({ data, cardRef }) {
  const tenure = useTenure(data.joined_at);
  const [tilt, setTilt] = useState(null);

  // Pointer tilt is a desktop affordance. On a touch screen the finger is on
  // top of the thing it would tilt, so it is simply not wired up there.
  const onMove = (e) => {
    if (!window.matchMedia("(pointer: fine)").matches) return;
    const box = e.currentTarget.getBoundingClientRect();
    const px = (e.clientX - box.left) / box.width - 0.5;
    const py = (e.clientY - box.top) / box.height - 0.5;
    setTilt({ x: -py * 7, y: px * 9, gx: 50 + px * 60, gy: 50 + py * 60 });
  };

  return (
    <div
      style={{ perspective: "1400px" }}
      onMouseMove={onMove}
      onMouseLeave={() => setTilt(null)}
    >
      <div
        ref={cardRef}
        data-testid="founding-passport-card"
        className="obx-holo obx-glass relative aspect-[1.586] w-full overflow-hidden rounded-2xl sm:rounded-[1.4rem]"
        style={{
          transform: tilt
            ? `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg) scale(1.012)`
            : "rotateX(0deg) rotateY(0deg)",
          transformStyle: "preserve-3d",
          transition: tilt ? "transform 90ms linear" : "transform 500ms cubic-bezier(0.16,1,0.3,1)",
        }}
      >
        {/* The specular highlight follows the pointer, which is what makes the
            foil beneath read as a surface catching light rather than a texture. */}
        <div
          className="pointer-events-none absolute inset-0 z-[1]"
          style={{
            background: `radial-gradient(60% 70% at ${tilt?.gx ?? 30}% ${tilt?.gy ?? 20}%, rgba(255,255,255,0.14), transparent 60%)`,
            transition: "background 120ms linear",
          }}
        />

        {/* Security microtext, the way a real credential is printed. Unreadable
            on purpose — it is texture that happens to be words. */}
        <div className="pointer-events-none absolute inset-x-0 top-0 z-[1] overflow-hidden whitespace-nowrap px-4 py-1 font-mono text-[5px] uppercase tracking-[0.3em] text-white/[0.13] sm:text-[6px]">
          {"OBRINEX · FOUNDING CIRCLE · ".repeat(14)}
        </div>

        <div className="relative z-[2] flex h-full flex-col justify-between p-4 sm:p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-mono text-[9px] uppercase tracking-[0.34em] text-primary/85 sm:text-[10px]">
                Founding Circle
              </p>
              <p className="mt-0.5 font-mono text-[8px] uppercase tracking-[0.26em] text-white/35 sm:text-[9px]">
                Obrinex · Member Credential
              </p>
            </div>
            <Sigil
              seed={data.member_number}
              className="h-10 w-10 shrink-0 text-primary sm:h-12 sm:w-12"
            />
          </div>

          <div className="min-w-0">
            <p className="truncate font-display text-lg font-bold leading-tight tracking-tight sm:text-2xl">
              {data.name}
            </p>
            <p className="truncate text-[11px] text-graphite sm:text-sm">
              {data.company || data.headline || "Founding member"}
            </p>
            <p className="obx-figure obx-gradient-text mt-1.5 font-mono text-xs font-semibold sm:mt-2 sm:text-base">
              {data.member_number}
            </p>
          </div>

          <div className="grid grid-cols-3 gap-2 border-t border-white/10 pt-2.5 sm:gap-3 sm:pt-3">
            <Field label="Admitted" value={formatDate(data.joined_at)} />
            <Field label="Seat" value={`${String(data.seat).padStart(2, "0")} / ${data.seats_total}`} />
            <Field label="Intake" value={data.intake} />
          </div>
        </div>
      </div>

      {tenure && (
        <div className="mt-3 flex items-center justify-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-carbon sm:gap-3">
          <span className="text-graphite">Member for</span>
          <TenureUnit value={tenure.days} unit="d" />
          <TenureUnit value={tenure.hours} unit="h" />
          <TenureUnit value={tenure.minutes} unit="m" />
          <TenureUnit value={tenure.seconds} unit="s" />
        </div>
      )}
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div className="min-w-0">
      <p className="font-mono text-[7px] uppercase tracking-[0.2em] text-white/35 sm:text-[8px]">
        {label}
      </p>
      <p className="obx-figure mt-0.5 truncate font-mono text-[10px] font-medium sm:text-xs">
        {value}
      </p>
    </div>
  );
}

function TenureUnit({ value, unit }) {
  return (
    <span className="obx-figure text-foreground">
      {String(value).padStart(2, "0")}
      <span className="text-carbon">{unit}</span>
    </span>
  );
}

/* ── Downloading it ───────────────────────────────────────────────────────────
   Drawn onto a canvas rather than screenshotted out of the DOM. A DOM capture
   would need a library and would still lose the backdrop-filter, so the card is
   redrawn at print resolution with the same geometry — what comes out is
   sharper than what is on screen, not a blurry copy of it. */

function drawPassport(data, scale = 3) {
  const W = 1012;
  const H = Math.round(W / 1.586);
  const canvas = document.createElement("canvas");
  canvas.width = W * scale;
  canvas.height = H * scale;
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);

  const radius = 36;
  const round = (x, y, w, h, r) => {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  };

  round(0, 0, W, H, radius);
  ctx.clip();

  ctx.fillStyle = "#050507";
  ctx.fillRect(0, 0, W, H);

  // The foil, as three overlapping washes. Conic gradients are not portable
  // across canvas implementations, so the animated version's look is
  // approximated with radials placed where its light actually falls.
  const wash = (x, y, r, color) => {
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, color);
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  };
  wash(W * 0.16, H * 0.1, W * 0.72, "rgba(0,224,255,0.20)");
  wash(W * 0.9, H * 0.22, W * 0.6, "rgba(130,100,255,0.17)");
  wash(W * 0.6, H * 1.05, W * 0.8, "rgba(255,90,190,0.09)");
  wash(W * 0.05, H * 0.02, W * 0.4, "rgba(255,255,255,0.10)");

  ctx.strokeStyle = "rgba(255,255,255,0.14)";
  ctx.lineWidth = 2;
  round(1, 1, W - 2, H - 2, radius);
  ctx.stroke();

  const pad = 54;

  ctx.font = '600 15px "JetBrains Mono", ui-monospace, monospace';
  ctx.fillStyle = "rgba(0,224,255,0.9)";
  ctx.letterSpacing = "5px";
  ctx.fillText("FOUNDING CIRCLE", pad, pad + 14);

  ctx.font = '500 12px "JetBrains Mono", ui-monospace, monospace';
  ctx.fillStyle = "rgba(255,255,255,0.36)";
  ctx.letterSpacing = "4px";
  ctx.fillText("OBRINEX · MEMBER CREDENTIAL", pad, pad + 36);

  // Sigil, top right — same generator as the on-screen one, so the download
  // carries the same mark rather than a lookalike.
  const grid = sigilCells(data.member_number || "OBRINEX");
  const cell = 12;
  const sx = W - pad - SIGIL_SIZE * cell;
  const sy = pad - 6;
  grid.forEach((row, y) =>
    row.forEach((on, x) => {
      if (!on) return;
      ctx.fillStyle = `rgba(0,224,255,${0.35 + ((x * 7 + y * 3) % 5) * 0.13})`;
      round(sx + x * cell, sy + y * cell, cell - 2.5, cell - 2.5, 2.5);
      ctx.fill();
    })
  );

  ctx.letterSpacing = "0px";
  ctx.font = '700 46px "Space Grotesk", sans-serif';
  ctx.fillStyle = "#fff";
  ctx.fillText(data.name || "", pad, H - 152);

  ctx.font = '400 19px "Plus Jakarta Sans", sans-serif';
  ctx.fillStyle = "rgba(255,255,255,0.52)";
  ctx.fillText(data.company || data.headline || "Founding member", pad, H - 124);

  ctx.font = '700 26px "JetBrains Mono", ui-monospace, monospace';
  ctx.letterSpacing = "3px";
  const numberGradient = ctx.createLinearGradient(pad, 0, pad + 420, 0);
  numberGradient.addColorStop(0, "#ffffff");
  numberGradient.addColorStop(0.55, "#6fe6ff");
  numberGradient.addColorStop(1, "#ffffff");
  ctx.fillStyle = numberGradient;
  ctx.fillText(data.member_number || "", pad, H - 84);

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad, H - 62);
  ctx.lineTo(W - pad, H - 62);
  ctx.stroke();

  const fields = [
    ["ADMITTED", formatDate(data.joined_at)],
    ["SEAT", `${String(data.seat).padStart(2, "0")} / ${data.seats_total}`],
    ["INTAKE", String(data.intake || "")],
  ];
  fields.forEach(([label, value], i) => {
    const x = pad + i * ((W - pad * 2) / 3);
    ctx.font = '500 11px "JetBrains Mono", ui-monospace, monospace';
    ctx.letterSpacing = "3px";
    ctx.fillStyle = "rgba(255,255,255,0.36)";
    ctx.fillText(label, x, H - 40);
    ctx.font = '500 16px "JetBrains Mono", ui-monospace, monospace';
    ctx.letterSpacing = "2px";
    ctx.fillStyle = "rgba(255,255,255,0.92)";
    ctx.fillText(value, x, H - 18);
  });

  return canvas;
}

/* ── Stamps ───────────────────────────────────────────────────────────────── */

function Stamp({ stamp, index }) {
  const earned = Boolean(stamp.earned_at);
  return (
    <div
      data-testid={`founding-stamp-${stamp.key}`}
      style={{ animationDelay: `${index * 45}ms` }}
      className={`obx-reveal relative overflow-hidden rounded-xl p-3 text-center transition-colors ${
        earned
          ? "obx-glass obx-sheen border-primary/25"
          : "border border-dashed border-white/10 bg-white/[0.012]"
      }`}
    >
      <div
        className={`mx-auto flex h-9 w-9 items-center justify-center rounded-full ${
          earned
            ? "bg-primary/15 text-primary ring-1 ring-primary/40"
            : "bg-white/[0.03] text-carbon ring-1 ring-white/10"
        }`}
      >
        {earned ? <Check className="h-4 w-4" /> : <Lock className="h-3.5 w-3.5" />}
      </div>
      <p className={`mt-2 text-xs font-medium ${earned ? "" : "text-carbon"}`}>{stamp.label}</p>
      <p className="mt-0.5 text-[10px] leading-snug text-graphite">{stamp.note}</p>
      <p className={`obx-figure mt-1.5 font-mono text-[9px] ${earned ? "text-primary/80" : "text-carbon"}`}>
        {earned ? formatDate(stamp.earned_at) : stamp.hint || "Not yet"}
      </p>
    </div>
  );
}

/* ── Perks ────────────────────────────────────────────────────────────────── */

function Meter({ used, total }) {
  const pct = total ? Math.min(100, (used / total) * 100) : 0;
  return (
    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
      <div
        className="h-full rounded-full bg-gradient-to-r from-primary/60 to-primary transition-[width] duration-700"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function Perk({ icon: Icon, label, value, sub, children }) {
  return (
    <div className="obx-glass obx-sheen rounded-xl p-4">
      <div className="flex items-center gap-2 text-graphite">
        <Icon className="h-3.5 w-3.5 text-primary" />
        <p className="font-mono text-[10px] uppercase tracking-[0.18em]">{label}</p>
      </div>
      <p className="obx-figure mt-2 font-display text-2xl font-bold">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-graphite">{sub}</p>}
      {children}
    </div>
  );
}

/* ── The page ─────────────────────────────────────────────────────────────── */

export default function MembershipPassport() {
  const [data, setData] = useState(null);
  const [saving, setSaving] = useState(false);
  const cardRef = useRef(null);

  useEffect(() => {
    api.get("/founding/membership")
      .then(({ data: d }) => setData(d))
      .catch(() => setData(false));
  }, []);

  const download = async () => {
    setSaving(true);
    try {
      // Wait for the two webfonts before drawing, or the canvas falls back to
      // a system face and the download looks like a different product.
      await document.fonts?.ready;
      const canvas = drawPassport(data);
      const url = canvas.toDataURL("image/png");
      const link = document.createElement("a");
      link.href = url;
      link.download = `${data.member_number || "obrinex-membership"}.png`;
      link.click();
      toast.success("Passport saved.");
    } catch {
      toast.error("Could not save the image.");
    } finally {
      setSaving(false);
    }
  };

  if (data === null) {
    return (
      <div className="space-y-4">
        <Skeleton className="aspect-[1.586] w-full rounded-2xl bg-surface-1" />
        <Skeleton className="h-40 w-full bg-surface-1" />
      </div>
    );
  }
  if (data === false) {
    return (
      <div className="obx-glass rounded-xl p-6 text-sm text-graphite">
        Your membership record could not be loaded.
      </div>
    );
  }

  const earned = (data.stamps || []).filter((s) => s.earned_at).length;
  const perks = data.perks || {};

  return (
    <div className="space-y-8" data-testid="founding-membership">
      <section className="mx-auto max-w-lg">
        <PassportCard data={data} cardRef={cardRef} />
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          <button
            onClick={download}
            disabled={saving}
            data-testid="founding-passport-download"
            className="obx-glass obx-lift obx-sheen flex items-center gap-2 rounded-xl px-3.5 py-2 text-sm disabled:opacity-60"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
            Save passport
          </button>
          <span className="flex items-center gap-1.5 rounded-xl border border-success/25 bg-success/10 px-3 py-2 text-xs text-success">
            <ShieldCheck className="h-3.5 w-3.5" /> Active
          </span>
        </div>
      </section>

      <section>
        <header className="mb-3 flex items-baseline justify-between gap-3">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
            Your stamps
          </p>
          <p className="obx-figure font-mono text-[11px] text-carbon">
            {earned} / {(data.stamps || []).length}
          </p>
        </header>
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
          {(data.stamps || []).map((s, i) => (
            <Stamp key={s.key} stamp={s} index={i} />
          ))}
        </div>
      </section>

      <section>
        <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
          What membership carries
        </p>
        <div className="grid gap-2.5 sm:grid-cols-3">
          <Perk
            icon={Ticket}
            label="Invitations"
            value={perks.invites_remaining ?? 0}
            sub={`${perks.invites_used ?? 0} of ${perks.invites_total ?? 0} used`}
          >
            <Meter used={perks.invites_used ?? 0} total={perks.invites_total ?? 1} />
          </Perk>
          <Perk
            icon={Users}
            label="Introductions"
            value={perks.invites_landed ?? 0}
            sub={`${perks.members_admitted ?? 0} admitted to the circle`}
          />
          <Perk
            icon={Sparkles}
            label="The circle"
            value={data.members ?? 0}
            sub={`${data.cohort ?? 0} in your intake · ${data.intake}`}
          />
        </div>
      </section>
    </div>
  );
}

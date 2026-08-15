import { useEffect, useState } from "react";
import { Plus, Loader2, Copy, Check, Trash2, Ticket, CircleDot } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

/** Invitations a member mints and sends themselves.
 *
 *  The link points at the public site, not at this one: a referral is something
 *  you hand to someone outside, so it has to be the address they can actually
 *  reach. We never contact the person — the introduction is the member's to
 *  make, and the interface says so rather than leaving them to assume.
 */
const APPLY_ORIGIN = "https://obrinex.space";
const linkFor = (code) => `${APPLY_ORIGIN}/join?ref=${code}`;

const STATE = {
  approved: { label: "Admitted", tone: "border-success/30 bg-success/10 text-success" },
  rejected: { label: "Not this round", tone: "border-white/12 bg-white/[0.04] text-carbon" },
  pending: { label: "Being read", tone: "border-warning/30 bg-warning/10 text-warning" },
};

export default function ReferralDesk() {
  const [rows, setRows] = useState(null);
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(null);

  const load = async () => {
    const { data } = await api.get("/founding/referrals");
    setRows(data);
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/founding/referrals", { label, note });
      await navigator.clipboard?.writeText(linkFor(data.code)).catch(() => {});
      toast.success("Invitation ready — link copied.");
      setLabel(""); setNote("");
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const revoke = async (id) => {
    try {
      await api.delete(`/founding/referrals/${id}`);
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const copy = async (code) => {
    await navigator.clipboard?.writeText(linkFor(code)).catch(() => {});
    setCopied(code);
    setTimeout(() => setCopied(null), 1600);
  };

  if (!rows) return <Skeleton className="h-64 w-full rounded-2xl bg-surface-1" />;

  const open = rows.filter((r) => !r.used_at).length;

  return (
    <div className="space-y-5" data-testid="founding-referrals">
      <section className="obx-glass obx-sheen relative overflow-hidden rounded-2xl p-4 sm:p-6">
        <div className="obx-aurora pointer-events-none absolute inset-0" />
        <div className="relative z-10">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary ring-1 ring-primary/30">
              <Ticket className="h-4 w-4" />
            </div>
            <div>
              <h2 className="font-display text-lg font-semibold tracking-tight">Invite someone</h2>
              <p className="mt-1 max-w-prose text-sm leading-relaxed text-graphite">
                You get a link to send them yourself. They answer the same eleven
                questions and are scored the same way — a referral is read sooner,
                not accepted sooner.
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
                Who is it for?
              </span>
              <input
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="For your list only"
                data-testid="founding-referral-label"
                className="obx-glass mt-1.5 w-full rounded-xl px-3 py-2 text-sm outline-none focus:border-primary/40 placeholder:text-carbon"
              />
            </label>
            <label className="block">
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
                Why them?
              </span>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="We read this with their application"
                data-testid="founding-referral-note"
                className="obx-glass mt-1.5 w-full rounded-xl px-3 py-2 text-sm outline-none focus:border-primary/40 placeholder:text-carbon"
              />
            </label>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              onClick={create}
              disabled={busy}
              data-testid="founding-referral-create"
              className="flex items-center gap-1.5 rounded-xl bg-primary px-3.5 py-2 text-sm font-medium text-background transition-opacity disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              Create invitation
            </button>
            <p className="text-xs text-carbon">
              We never email the person — the introduction is yours to make.
            </p>
          </div>
        </div>
      </section>

      {rows.length > 0 && (
        <section className="space-y-2">
          <div className="flex items-baseline justify-between">
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
              Your invitations
            </p>
            <p className="obx-figure font-mono text-[11px] text-carbon">
              {open} unused · {rows.length} total
            </p>
          </div>

          {rows.map((r, i) => {
            const state = r.used_at ? STATE[r.status] || STATE.pending : null;
            return (
              <div
                key={r.id}
                style={{ animationDelay: `${i * 35}ms` }}
                className="obx-glass obx-reveal flex items-center gap-3 rounded-xl p-3"
              >
                <CircleDot
                  className={`h-3.5 w-3.5 shrink-0 ${r.used_at ? "text-primary" : "text-carbon"}`}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{r.label || "Unlabelled invitation"}</p>
                  <p className="mt-0.5 truncate text-[11px] text-graphite">
                    {r.used_at
                      ? `Used${r.applicant_name ? ` by ${r.applicant_name}` : ""}`
                      : "Not used yet"}
                  </p>
                </div>

                {state ? (
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] ${state.tone}`}>
                    {state.label}
                  </span>
                ) : (
                  <>
                    <button
                      onClick={() => copy(r.code)}
                      title="Copy link"
                      aria-label="Copy invitation link"
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-carbon transition-colors hover:bg-white/[0.06] hover:text-primary"
                    >
                      {copied === r.code ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
                    </button>
                    <button
                      onClick={() => revoke(r.id)}
                      title="Withdraw"
                      aria-label="Withdraw invitation"
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-carbon transition-colors hover:bg-white/[0.06] hover:text-danger"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </>
                )}
              </div>
            );
          })}
        </section>
      )}
    </div>
  );
}

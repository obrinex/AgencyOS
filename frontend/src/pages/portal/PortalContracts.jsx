import { useEffect, useState } from "react";
import { FileSignature, PenLine, CheckCircle2, Loader2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { format } from "date-fns";
import { toast } from "sonner";

/** Contracts, and signing one.
 *
 *  A signed contract and an unsigned one are different objects here, not the
 *  same card with a different button: one is a record, the other is a task. The
 *  unsigned one keeps the accent edge, because it is the only thing on this
 *  page that is waiting on the client.
 */
export default function PortalContracts() {
  const [contracts, setContracts] = useState(null);
  const [signTarget, setSignTarget] = useState(null);
  const [signatureName, setSignatureName] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/portal/contracts");
      setContracts(data);
    } catch {
      setContracts([]);
    }
  };

  useEffect(() => { load(); }, []);

  const sign = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post(`/portal/contracts/${signTarget.id}/sign`, { signature_name: signatureName });
      toast.success("Contract signed.");
      setSignTarget(null);
      setSignatureName("");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setBusy(false); }
  };

  if (!contracts) {
    return <div className="p-4 sm:p-6"><Skeleton className="h-64 w-full rounded-2xl bg-surface-1" /></div>;
  }

  const waiting = contracts.filter((c) => c.status !== "signed").length;

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6" data-testid="portal-contracts-page">
      <header className="mb-5">
        <h1 className="font-display text-2xl font-bold tracking-tight">Contracts</h1>
        <p className="mt-1 text-sm text-graphite">
          {contracts.length === 0
            ? "Nothing yet."
            : `${contracts.length} in total${waiting ? ` · ${waiting} awaiting your signature` : ""}`}
        </p>
      </header>

      {contracts.length === 0 ? (
        <div className="obx-glass rounded-2xl px-6 py-14 text-center" data-testid="portal-contracts-empty">
          <div className="obx-holo obx-glass relative mx-auto flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl">
            <FileSignature className="relative z-10 h-5 w-5 text-primary" />
          </div>
          <p className="mt-4 text-sm">No contracts yet.</p>
          <p className="mt-1 text-xs text-graphite">Agreements with your agency appear here.</p>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {contracts.map((c, i) => {
            const signed = c.status === "signed";
            return (
              <article
                key={c.id}
                data-testid={`portal-contract-card-${c.id}`}
                style={{ animationDelay: `${i * 45}ms` }}
                className={`obx-glass obx-sheen obx-reveal relative overflow-hidden rounded-2xl p-4 sm:p-5 ${
                  signed ? "" : "obx-lift border-primary/25"
                }`}
              >
                {!signed && <span className="absolute inset-y-0 left-0 w-[2px] bg-primary/70" />}

                <p className="font-display font-semibold leading-snug tracking-tight">{c.title}</p>
                <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
                  {c.status}
                </p>
                {c.renewal_date && (
                  <p className="mt-1 text-xs text-carbon">
                    Renews {format(new Date(c.renewal_date), "d MMM yyyy")}
                  </p>
                )}

                {signed ? (
                  <p className="mt-4 flex items-center gap-1.5 border-t border-white/[0.07] pt-3 text-xs text-success">
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                    Signed by {c.signature_name}
                  </p>
                ) : (
                  <button
                    onClick={() => setSignTarget(c)}
                    data-testid={`portal-sign-contract-${c.id}`}
                    className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-xl bg-primary px-3 py-2 text-sm font-medium text-background"
                  >
                    <PenLine className="h-3.5 w-3.5" /> Review &amp; sign
                  </button>
                )}
              </article>
            );
          })}
        </div>
      )}

      <Dialog open={!!signTarget} onOpenChange={(o) => !o && setSignTarget(null)}>
        <DialogContent
          className="border-white/10 bg-black/85 backdrop-blur-2xl"
          data-testid="portal-sign-contract-dialog"
        >
          <DialogHeader>
            <DialogTitle className="font-display tracking-tight">
              Sign: {signTarget?.title}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={sign} className="space-y-4">
            <p className="text-sm leading-relaxed text-graphite">
              By typing your full name below, you agree this constitutes your
              electronic signature and acceptance of this contract.
            </p>
            <label className="block">
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
                Full name
              </span>
              <input
                required
                value={signatureName}
                onChange={(e) => setSignatureName(e.target.value)}
                placeholder="Type your full name"
                data-testid="portal-signature-input"
                className="obx-glass mt-1.5 w-full rounded-xl px-3 py-2.5 font-display text-lg italic outline-none focus:border-primary/40 placeholder:text-carbon placeholder:not-italic placeholder:text-sm"
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              data-testid="portal-signature-submit"
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-background disabled:opacity-50"
            >
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              Sign contract
            </button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

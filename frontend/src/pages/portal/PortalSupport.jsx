import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, LifeBuoy, Loader2, ChevronRight, MessageSquare } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { TICKET_STATUS_CONFIG, PRIORITY_CONFIG } from "@/lib/statusConfig";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";

/** Support, as a list of conversations rather than a list of rows.
 *
 *  Two things the old screen dropped on the floor: a ticket never showed
 *  whether the team had replied, and the priority field was collected by the
 *  API but had no control in the form — every ticket was filed as medium
 *  whatever the client actually meant. Both are here now.
 */

const emptyForm = { subject: "", description: "", priority: "medium" };

const PRIORITIES = [
  { value: "low", label: "Low", hint: "Whenever you get to it" },
  { value: "medium", label: "Medium", hint: "This week" },
  { value: "high", label: "High", hint: "Blocking work" },
  { value: "urgent", label: "Urgent", hint: "Something is down" },
];

const OPEN_STATES = new Set(["open", "in_progress", "pending", "waiting"]);

const field =
  "obx-glass w-full rounded-xl px-3 py-2 text-sm outline-none focus:border-primary/40 placeholder:text-carbon";

export default function PortalSupport() {
  const [tickets, setTickets] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const load = async () => {
    try {
      const { data } = await api.get("/portal/tickets");
      setTickets(data);
    } catch {
      setTickets([]);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/portal/tickets", form);
      toast.success("Support ticket submitted.");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const counts = useMemo(() => {
    const rows = tickets || [];
    return {
      open: rows.filter((t) => OPEN_STATES.has(t.status)).length,
      unread: rows.reduce((n, t) => n + (t.unread || 0), 0),
    };
  }, [tickets]);

  if (!tickets) return <div className="p-4 sm:p-6"><Skeleton className="h-64 w-full rounded-2xl bg-surface-1" /></div>;

  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-6" data-testid="portal-support-page">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">Support</h1>
          <p className="mt-1 text-sm text-graphite">
            {tickets.length === 0
              ? "Nothing open."
              : `${counts.open} open · ${tickets.length} total${counts.unread ? ` · ${counts.unread} new repl${counts.unread === 1 ? "y" : "ies"}` : ""}`}
          </p>
        </div>
        <button
          onClick={() => setOpen(true)}
          data-testid="portal-open-create-ticket-btn"
          className="flex items-center gap-1.5 rounded-xl bg-primary px-3.5 py-2 text-sm font-medium text-background"
        >
          <Plus className="h-3.5 w-3.5" /> New ticket
        </button>
      </header>

      {tickets.length === 0 ? (
        <div className="obx-glass rounded-2xl px-6 py-14 text-center" data-testid="portal-support-empty">
          <div className="obx-holo obx-glass relative mx-auto flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl">
            <LifeBuoy className="relative z-10 h-5 w-5 text-primary" />
          </div>
          <p className="mt-4 text-sm">No tickets yet.</p>
          <p className="mx-auto mt-1 max-w-xs text-xs text-graphite">
            Something wrong, or something you need? Open a ticket and it reaches
            the team with a record attached.
          </p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {tickets.map((t, i) => (
            <button
              key={t.id}
              onClick={() => navigate(`/portal/support/${t.id}`)}
              data-testid={`portal-ticket-row-${t.id}`}
              style={{ animationDelay: `${i * 40}ms` }}
              className="obx-glass obx-lift obx-sheen obx-reveal flex w-full items-center gap-3 rounded-2xl p-4 text-left"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-medium">{t.subject}</p>
                  {t.unread > 0 && (
                    <span className="obx-ping h-1.5 w-1.5 shrink-0 rounded-full bg-primary text-primary" />
                  )}
                </div>
                <p className="mt-1 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-carbon">
                  {t.created_at && (
                    <span>{formatDistanceToNow(new Date(t.created_at), { addSuffix: true })}</span>
                  )}
                  {(t.messages?.length || 0) > 0 && (
                    <span className="flex items-center gap-1">
                      <MessageSquare className="h-3 w-3" />
                      {t.messages.filter((m) => !m.internal).length}
                    </span>
                  )}
                </p>
              </div>
              <div className="hidden shrink-0 items-center gap-2 sm:flex">
                <StatusBadge config={PRIORITY_CONFIG} value={t.priority} />
                <StatusBadge config={TICKET_STATUS_CONFIG} value={t.status} />
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-carbon" />
            </button>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="border-white/10 bg-black/85 backdrop-blur-2xl"
          data-testid="portal-create-ticket-dialog"
        >
          <DialogHeader>
            <DialogTitle className="font-display tracking-tight">New support ticket</DialogTitle>
          </DialogHeader>
          <form onSubmit={create} className="space-y-4">
            <label className="block">
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
                Subject
              </span>
              <input
                required
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
                placeholder="One line — what is this about?"
                data-testid="portal-ticket-form-subject"
                className={`mt-1.5 ${field}`}
              />
            </label>

            <label className="block">
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
                What&apos;s happening?
              </span>
              <textarea
                required
                rows={4}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="What you expected, what happened instead, and when it started."
                data-testid="portal-ticket-form-description"
                className={`mt-1.5 resize-y ${field}`}
              />
            </label>

            <fieldset>
              <legend className="font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
                How urgent?
              </legend>
              <div className="mt-1.5 grid grid-cols-2 gap-2">
                {PRIORITIES.map((p) => (
                  <button
                    key={p.value}
                    type="button"
                    onClick={() => setForm({ ...form, priority: p.value })}
                    data-testid={`portal-ticket-priority-${p.value}`}
                    className={`obx-glass rounded-xl px-3 py-2 text-left transition-colors ${
                      form.priority === p.value ? "border-primary/40 bg-primary/[0.08]" : ""
                    }`}
                  >
                    <span className={`block text-xs font-medium ${form.priority === p.value ? "text-primary" : ""}`}>
                      {p.label}
                    </span>
                    <span className="mt-0.5 block text-[10px] text-carbon">{p.hint}</span>
                  </button>
                ))}
              </div>
            </fieldset>

            <button
              type="submit"
              disabled={busy}
              data-testid="portal-ticket-form-submit"
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-background disabled:opacity-50"
            >
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              Submit ticket
            </button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

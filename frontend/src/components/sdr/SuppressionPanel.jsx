import { useCallback, useEffect, useState } from "react";
import { Ban, Plus, Trash2, Search, Loader2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import { format } from "date-fns";
import { toast } from "sonner";

const REASONS = [
  "unsubscribe", "bounce", "complaint", "manual",
  "legal", "competitor", "existing_client",
];

const REASON_STYLE = {
  unsubscribe: "bg-info/15 text-info",
  complaint: "bg-danger/15 text-danger",
  bounce: "bg-warning/15 text-warning",
  legal: "bg-danger/15 text-danger",
};

const emptyForm = { value: "", value_type: "email", reason: "manual" };

export default function SuppressionPanel() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [entries, setEntries] = useState(null);
  const [summary, setSummary] = useState([]);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [removeTarget, setRemoveTarget] = useState(null);

  const load = useCallback(async (term) => {
    const query = term ? `&search=${encodeURIComponent(term)}` : "";
    const [list, counts] = await Promise.all([
      api.get(`/sdr/suppression?limit=100${query}`),
      api.get("/sdr/suppression/summary"),
    ]);
    setEntries(list.data.items);
    setSummary(counts.data.by_reason || []);
  }, []);

  useEffect(() => { load(""); }, [load]);

  useEffect(() => {
    const timer = setTimeout(() => load(search), 250);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const add = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/sdr/suppression", form);
      toast.success("Added — this address will never be contacted again");
      setOpen(false);
      setForm(emptyForm);
      load(search);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.delete(
        `/sdr/suppression?value=${encodeURIComponent(removeTarget.value_normalized)}` +
        `&value_type=${removeTarget.value_type}`
      );
      toast.success("Removed from the suppression list");
      setRemoveTarget(null);
      load(search);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  if (!entries) return <Skeleton className="h-48 bg-surface-1" />;

  const total = summary.reduce((sum, row) => sum + row.count, 0);

  return (
    <div className="space-y-4" data-testid="sdr-suppression-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-graphite max-w-2xl">
          Anyone here is never contacted again, on any channel, in any campaign.
          Checked before every send and before anything else is spent.
        </p>
        <Button
          size="sm"
          data-testid="sdr-add-suppression-btn"
          className="gap-1.5 shrink-0"
          onClick={() => setOpen(true)}
        >
          <Plus className="h-3.5 w-3.5" /> Add
        </Button>
      </div>

      {total > 0 && (
        <div className="flex flex-wrap gap-2" data-testid="sdr-suppression-summary">
          {summary.map((row) => (
            <span
              key={row.reason}
              className={`font-mono text-[10px] px-2 py-1 rounded uppercase ${REASON_STYLE[row.reason] || "bg-surface-2 text-graphite"}`}
            >
              {row.reason} {row.count}
            </span>
          ))}
        </div>
      )}

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-carbon" />
        <Input
          data-testid="sdr-suppression-search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search suppressed addresses and domains…"
          className="bg-surface-2 border-white/10 pl-9"
        />
      </div>

      {entries.length === 0 ? (
        <EmptyState
          icon={Ban}
          title={search ? "No matches" : "Nothing suppressed"}
          description={
            search
              ? "No suppressed address or domain matches that search."
              : "Unsubscribes, bounces and complaints land here automatically."
          }
          testId="sdr-suppression-empty"
        />
      ) : (
        <div className="space-y-2" data-testid="sdr-suppression-list">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-surface-1 px-4 py-2.5"
              data-testid={`sdr-suppression-${entry.id}`}
            >
              <span className="font-mono text-sm truncate flex-1 min-w-0">
                {entry.value_normalized}
              </span>
              <span className="font-mono text-[9px] px-1.5 py-0.5 rounded uppercase bg-surface-2 text-graphite">
                {entry.value_type}
              </span>
              <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${REASON_STYLE[entry.reason] || "bg-surface-2 text-graphite"}`}>
                {entry.reason}
              </span>
              {entry.created_at && (
                <span className="font-mono text-[11px] text-carbon hidden sm:block">
                  {format(new Date(entry.created_at), "MMM d, yyyy")}
                </span>
              )}
              {isAdmin && (
                <button
                  data-testid={`sdr-unsuppress-${entry.id}`}
                  onClick={() => setRemoveTarget(entry)}
                  className="text-graphite hover:text-danger p-1 shrink-0"
                  title="Remove from suppression list"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="sdr-add-suppression-dialog">
          <DialogHeader><DialogTitle>Suppress an address or domain</DialogTitle></DialogHeader>
          <form onSubmit={add} className="space-y-3">
            <div className="grid grid-cols-[1fr_130px] gap-3">
              <div className="space-y-1">
                <Label>Value *</Label>
                <Input
                  required
                  data-testid="sdr-suppression-value"
                  value={form.value}
                  onChange={(e) => setForm({ ...form, value: e.target.value })}
                  placeholder="someone@example.com"
                  className="bg-surface-2 border-white/10"
                />
              </div>
              <div className="space-y-1">
                <Label>Type</Label>
                <Select
                  value={form.value_type}
                  onValueChange={(v) => setForm({ ...form, value_type: v })}
                >
                  <SelectTrigger className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="email">Email</SelectItem>
                    <SelectItem value="domain">Domain</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label>Reason</Label>
              <Select value={form.reason} onValueChange={(v) => setForm({ ...form, reason: v })}>
                <SelectTrigger className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {REASONS.map((reason) => (
                    <SelectItem key={reason} value={reason}>{reason.replace(/_/g, " ")}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <p className="text-xs text-graphite">
              Suppressing a domain covers every address at that company, not just this one.
            </p>
            <DialogFooter>
              <Button type="submit" disabled={busy} className="gap-1.5">
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Ban className="h-3.5 w-3.5" />}
                Suppress
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={!!removeTarget} onOpenChange={(o) => !o && setRemoveTarget(null)}>
        <DialogContent className="bg-surface-1 border-white/10">
          <DialogHeader><DialogTitle>Remove from the suppression list?</DialogTitle></DialogHeader>
          <p className="text-sm text-graphite">
            <span className="font-mono text-foreground">{removeTarget?.value_normalized}</span>{" "}
            becomes contactable again. If they unsubscribed, only do this when you know it
            was a mistake — the removal is recorded in the consent log either way.
          </p>
          <DialogFooter>
            <Button variant="outline" className="border-white/10" onClick={() => setRemoveTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" disabled={busy} onClick={remove}>Remove</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

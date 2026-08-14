import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LifeBuoy, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { TICKET_STATUS_CONFIG, PRIORITY_CONFIG } from "@/lib/statusConfig";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

export default function Support() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [tickets, setTickets] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [deletingSelected, setDeletingSelected] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const navigate = useNavigate();

  const load = () => api.get("/tickets").then((r) => setTickets(r.data));
  useEffect(() => { load(); }, []);

  const toggleSelected = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    const ids = (tickets || []).map((t) => t.id);
    const allOn = ids.length > 0 && ids.every((id) => selected.has(id));
    setSelected(allOn ? new Set() : new Set(ids));
  };

  const deleteSelected = async () => {
    setDeletingSelected(true);
    const ids = [...selected];
    let ok = 0;
    for (const id of ids) {
      try { await api.delete(`/tickets/${id}`); ok += 1; }
      catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    }
    setDeletingSelected(false);
    setConfirmOpen(false);
    setSelected(new Set());
    if (ok) toast.success(`${ok} ticket${ok === 1 ? "" : "s"} deleted`);
    load();
  };

  if (!tickets) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  const allSelected = tickets.length > 0 && tickets.every((t) => selected.has(t.id));

  return (
    <div className="p-6" data-testid="support-page">
      <PageHeader
        title="Support Desk"
        description={`${tickets.length} tickets`}
        actions={isAdmin && tickets.length > 0 ? (
          <button type="button" onClick={selectAll}
            className="text-xs font-mono uppercase text-carbon hover:text-ash transition-colors"
            data-testid="support-select-all">
            {allSelected ? "Select none" : "Select all"}
          </button>
        ) : null}
      />

      {/* Only present while something is selected — same as the Pipeline. */}
      {selected.size > 0 && (
        <div data-testid="support-selection-toolbar"
          className="mb-3 flex items-center gap-3 rounded-lg border border-accent/30 bg-accent/5 px-3 py-2">
          <span className="text-sm font-medium" data-testid="support-selection-count">{selected.size} selected</span>
          <button type="button" onClick={() => setSelected(new Set())}
            className="text-xs text-graphite hover:text-ash transition-colors">Clear</button>
          <div className="flex-1" />
          <Button data-testid="support-delete-selected-btn" onClick={() => setConfirmOpen(true)}
            disabled={deletingSelected} size="sm" variant="outline"
            className="gap-1.5 border-danger/30 text-danger hover:bg-danger/10 hover:text-danger">
            <Trash2 className="h-3.5 w-3.5" />
            {`Delete ${selected.size}`}
          </Button>
        </div>
      )}

      {tickets.length === 0 ? (
        <EmptyState icon={LifeBuoy} title="No support tickets" description="Client support tickets will appear here once submitted from the Client Portal." testId="support-empty-state" />
      ) : (
        <div className="space-y-2" data-testid="tickets-list">
          {tickets.map((t) => (
            <Card
              key={t.id}
              onClick={() => navigate(`/support/${t.id}`)}
              data-testid={`ticket-row-${t.id}`}
              className={`p-4 border flex items-center gap-3 cursor-pointer transition-colors ${
                selected.has(t.id) ? "border-accent/60 bg-accent/5" : "bg-surface-1 border-white/10 hover:border-white/25"
              }`}
            >
              {isAdmin && (
                <span onClick={(e) => { e.stopPropagation(); toggleSelected(t.id); }} className="shrink-0">
                  <Checkbox data-testid={`ticket-select-${t.id}`} checked={selected.has(t.id)} aria-label={`Select ${t.subject}`} />
                </span>
              )}
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{t.subject}</p>
                <p className="text-xs text-graphite">{t.client_name || "Unknown client"}</p>
              </div>
              <StatusBadge config={PRIORITY_CONFIG} value={t.priority} />
              <StatusBadge config={TICKET_STATUS_CONFIG} value={t.status} />
            </Card>
          ))}
        </div>
      )}

      <Dialog open={confirmOpen} onOpenChange={(o) => !o && setConfirmOpen(false)}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="support-delete-dialog">
          <DialogHeader>
            <DialogTitle>Delete {selected.size} ticket{selected.size === 1 ? "" : "s"}?</DialogTitle>
            <DialogDescription>
              This permanently deletes the selected ticket{selected.size === 1 ? "" : "s"} and all their messages. This can't be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" className="border-white/10" onClick={() => setConfirmOpen(false)}>Cancel</Button>
            <Button variant="destructive" disabled={deletingSelected} onClick={deleteSelected} data-testid="support-confirm-delete-btn">
              {deletingSelected ? "Deleting…" : `Delete ${selected.size}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

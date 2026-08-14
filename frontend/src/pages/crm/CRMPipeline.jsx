import { useEffect, useState, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Plus, KanbanSquare, Building2, Upload, Link2, Trash2, AlertTriangle } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { formatMoney } from "@/lib/currency";
import { useAuth } from "@/contexts/AuthContext";
import { Checkbox } from "@/components/ui/checkbox";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { STAGE_CONFIG, STAGES_LIST, TERMINAL_STAGES, PRIORITY_CONFIG } from "@/lib/statusConfig";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

const emptyForm = { company: "", website: "", industry: "", email: "", phone: "", location: "", revenue: "", priority: "medium", source: "manual", notes: "" };

//: Matches the server's default page size for /leads.
const PAGE_SIZE = 500;
//: A ceiling on the board itself. Past this a kanban is not a usable view of
//: a pipeline anyway, and rendering it just locks the tab up.
const MAX_BOARD_LEADS = 5000;

export default function CRMPipeline() {
  const [leads, setLeads] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [dragStage, setDragStage] = useState(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importing, setImporting] = useState(false);
  const [wipeOpen, setWipeOpen] = useState(false);
  const [wipePreview, setWipePreview] = useState(null);
  const [wipeIncludeWon, setWipeIncludeWon] = useState(false);
  const [wipeConfirm, setWipeConfirm] = useState("");
  const [wiping, setWiping] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [deletingSelected, setDeletingSelected] = useState(false);

  const toggleSelected = (leadId) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(leadId) ? next.delete(leadId) : next.add(leadId);
      return next;
    });
  };

  const selectStage = (stage) => {
    const ids = (byStage[stage] || []).map((l) => l.id);
    const allOn = ids.length > 0 && ids.every((id) => selected.has(id));
    setSelected((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => (allOn ? next.delete(id) : next.add(id)));
      return next;
    });
  };

  const deleteSelected = async () => {
    setDeletingSelected(true);
    try {
      const { data } = await api.post("/leads/delete-selected", {
        lead_ids: Array.from(selected),
      });
      toast.success(data.message);
      setSelected(new Set());
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setDeletingSelected(false);
    }
  };
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { user } = useAuth();

  // Counted server-side before anything is destroyed, and re-counted whenever
  // the won-leads toggle changes - the number on the button has to be the
  // number that gets deleted, or the confirmation is theatre.
  const loadWipePreview = async (includeWon) => {
    setWipePreview(null);
    try {
      const { data } = await api.get("/leads/bulk-delete/preview", { params: { include_won: includeWon } });
      setWipePreview(data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const openWipe = () => {
    setWipeConfirm("");
    setWipeIncludeWon(false);
    setWipeOpen(true);
    loadWipePreview(false);
  };

  const wipeAll = async () => {
    setWiping(true);
    try {
      const { data } = await api.post("/leads/bulk-delete", {
        confirm: wipeConfirm,
        include_won: wipeIncludeWon,
      });
      toast.success(data.message);
      setWipeOpen(false);
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setWiping(false);
    }
  };

  // Paged, because the board has to show the whole pipeline and the endpoint
  // returns at most `PAGE_SIZE` rows. It used to take one unpaged response and
  // treat it as the pipeline, so past the server's cap the extra leads were
  // simply invisible — including in the "N total leads" count above the board.
  const load = async () => {
    const all = [];
    for (let skip = 0; ; skip += PAGE_SIZE) {
      const { data } = await api.get("/leads", { params: { limit: PAGE_SIZE, skip } });
      all.push(...data);
      // A short page means the last one. Guard on the page cap too, so a
      // server-side change can never turn this into an unbounded loop.
      if (data.length < PAGE_SIZE || all.length >= MAX_BOARD_LEADS) break;
    }
    setLeads(all);
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (params.get("new") === "1") {
      setOpen(true);
      params.delete("new");
      setParams(params);
    }
  }, [params]);

  const byStage = useMemo(() => {
    const map = {};
    STAGES_LIST.forEach((s) => (map[s] = []));
    (leads || []).forEach((l) => map[l.stage]?.push(l));
    return map;
  }, [leads]);

  const createLead = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/leads", { ...form, revenue: form.revenue ? parseFloat(form.revenue) : null });
      toast.success("Lead created");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const moveStage = async (leadId, stage) => {
    const lead = leads.find((l) => l.id === leadId);
    if (lead && lead.stage === stage) return;

    // Refused here as well as on the server, so dragging a won card produces an
    // explanation instead of a card that visibly moves and then snaps back.
    if (lead && TERMINAL_STAGES.includes(lead.stage)) {
      toast.error(
        "This deal is already won. It created a client, a project and an invoice — reopening it would leave those with no deal behind them."
      );
      return;
    }

    setLeads((prev) => prev.map((l) => (l.id === leadId ? { ...l, stage } : l)));
    try {
      const { data } = await api.patch(`/leads/${leadId}/stage`, { stage });
      if (data.automation && !data.automation.already_ran) {
        toast.success("Deal won! Client, project & invoice auto-generated.", { duration: 5000 });
      }
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      load();
    }
  };

  const importCsv = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportResult(null);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const { data } = await api.post("/leads/import-csv", formData, { headers: { "Content-Type": "multipart/form-data" } });
      setImportResult(data);
      toast.success(`Imported ${data.imported} lead(s)`);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  };

  if (!leads) {
    return (
      <div className="p-6 space-y-4" data-testid="pipeline-loading">
        <Skeleton className="h-8 w-56 bg-surface-1" />
        <div className="flex gap-4 overflow-hidden">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-96 w-64 bg-surface-1 shrink-0" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full" data-testid="pipeline-page">
      <PageHeader
        title="Pipeline"
        description={`${leads.length} total leads across the funnel`}
        actions={
          <div className="flex items-center gap-2">
            <Button
              data-testid="copy-leadform-link-btn"
              size="sm" variant="outline" className="gap-1.5 border-white/10"
              onClick={async () => {
                try {
                  const { data } = await api.get("/leadform/settings");
                  await navigator.clipboard.writeText(`${window.location.origin}/start/${data.slug}`);
                  toast.success("Lead form link copied — put it on your website or share it");
                } catch (err) {
                  toast.error(formatApiError(err.response?.data?.detail));
                }
              }}
            >
              <Link2 className="h-3.5 w-3.5" /> Lead Form Link
            </Button>
            <Button data-testid="open-import-csv-btn" onClick={() => { setImportOpen(true); setImportResult(null); }} size="sm" variant="outline" className="gap-1.5 border-white/10">
              <Upload className="h-3.5 w-3.5" /> Import CSV
            </Button>
            <Button data-testid="open-create-lead-btn" onClick={() => setOpen(true)} size="sm" className="gap-1.5">
              <Plus className="h-3.5 w-3.5" /> New Lead
            </Button>
            {/* Admin-only, and last in the row: the destructive control should
                not sit where the primary action is expected. */}
            {user?.role === "admin" && leads.length > 0 && (
              <Button
                data-testid="open-delete-all-leads-btn"
                onClick={openWipe}
                size="sm" variant="outline"
                className="gap-1.5 border-danger/30 text-danger hover:bg-danger/10 hover:text-danger"
              >
                <Trash2 className="h-3.5 w-3.5" /> Delete All
              </Button>
            )}
          </div>
        }
      />

      {/* Only present while something is selected. A permanently-visible
          delete bar is a permanently-available accident. */}
      {selected.size > 0 && (
        <div
          data-testid="selection-toolbar"
          className="mx-6 mb-3 flex items-center gap-3 rounded-lg border border-accent/30 bg-accent/5 px-3 py-2"
        >
          <span className="text-sm font-medium" data-testid="selection-count">
            {selected.size} selected
          </span>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            data-testid="clear-selection-btn"
            className="text-xs text-graphite hover:text-ash transition-colors"
          >
            Clear
          </button>
          <div className="flex-1" />
          <Button
            data-testid="delete-selected-btn"
            onClick={deleteSelected}
            disabled={deletingSelected}
            size="sm" variant="outline"
            className="gap-1.5 border-danger/30 text-danger hover:bg-danger/10 hover:text-danger"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {deletingSelected ? "Deleting..." : `Delete ${selected.size}`}
          </Button>
        </div>
      )}

      <div className="flex-1 overflow-x-auto px-6 pb-6 flex gap-4" data-testid="pipeline-board">
        {STAGES_LIST.map((stage) => (
          <div
            key={stage}
            data-testid={`pipeline-column-${stage}`}
            onDragOver={(e) => { e.preventDefault(); setDragStage(stage); }}
            onDrop={(e) => {
              const leadId = e.dataTransfer.getData("leadId");
              if (leadId) moveStage(leadId, stage);
              setDragStage(null);
            }}
            className={`w-64 shrink-0 rounded-xl border bg-surface-1/60 flex flex-col transition-colors ${dragStage === stage ? "border-info/50 bg-surface-2" : "border-white/10"}`}
          >
            <div className="flex items-center justify-between px-3 py-2.5 border-b border-white/10">
              <span className="font-mono text-[11px] uppercase tracking-wide text-ash">{STAGE_CONFIG[stage].label}</span>
              <div className="flex items-center gap-2">
                {byStage[stage]?.length > 0 && (
                  <button
                    type="button"
                    data-testid={`select-stage-${stage}`}
                    onClick={() => selectStage(stage)}
                    className="text-[10px] font-mono uppercase text-carbon hover:text-ash transition-colors"
                  >
                    {byStage[stage].every((l) => selected.has(l.id)) ? "None" : "All"}
                  </button>
                )}
                <span className="text-[11px] font-mono text-carbon">{byStage[stage]?.length || 0}</span>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto scrollbar-thin p-2 space-y-2 min-h-[100px]">
              {byStage[stage]?.map((lead) => (
                <motion.div
                  key={lead.id}
                  layout
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData("leadId", lead.id)}
                  onClick={() => navigate(`/crm/${lead.id}`)}
                  data-testid={`lead-card-${lead.id}`}
                  className={`cursor-pointer rounded-lg border bg-surface-2 p-3 transition-colors ${
                    selected.has(lead.id)
                      ? "border-accent/60 bg-accent/5"
                      : "border-white/10 hover:border-white/25"
                  }`}
                >
                  <div className="flex items-start gap-2">
                    {/* stopPropagation on the wrapper, not just the control:
                        the whole card navigates on click, and a checkbox that
                        opens the lead you were trying to tick is worse than
                        no checkbox. */}
                    <span
                      onClick={(e) => { e.stopPropagation(); toggleSelected(lead.id); }}
                      className="pt-0.5 shrink-0"
                    >
                      <Checkbox
                        data-testid={`lead-select-${lead.id}`}
                        checked={selected.has(lead.id)}
                        aria-label={`Select ${lead.company}`}
                      />
                    </span>
                    <p className="text-sm font-medium truncate flex-1">{lead.company}</p>
                  </div>
                  {/* formatMoney, not a $ icon: `revenue` is INR. When a lead
                      is Won, automation_engine puts this exact number on an
                      INR invoice - so the $ here was never a different
                      currency, only a mislabelled one. */}
                  {lead.revenue > 0 && (
                    <p className="mt-1 flex items-center gap-1 text-xs font-mono text-graphite">{formatMoney(lead.revenue)}</p>
                  )}
                  <div className="mt-2">
                    <StatusBadge config={PRIORITY_CONFIG} value={lead.priority} />
                  </div>
                </motion.div>
              ))}
              {byStage[stage]?.length === 0 && <p className="text-center text-xs text-carbon py-6">No leads</p>}
            </div>
          </div>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10 max-w-lg" data-testid="create-lead-dialog">
          <DialogHeader><DialogTitle>New Lead</DialogTitle></DialogHeader>
          <form onSubmit={createLead} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Company *</Label>
                <Input data-testid="lead-form-company" required value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} className="bg-surface-2 border-white/10" />
              </div>
              <div className="space-y-1">
                <Label>Website</Label>
                <Input data-testid="lead-form-website" value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} className="bg-surface-2 border-white/10" />
              </div>
              <div className="space-y-1">
                <Label>Email</Label>
                <Input data-testid="lead-form-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="bg-surface-2 border-white/10" />
              </div>
              <div className="space-y-1">
                <Label>Phone</Label>
                <Input data-testid="lead-form-phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className="bg-surface-2 border-white/10" />
              </div>
              <div className="space-y-1">
                <Label>Est. Revenue (₹)</Label>
                <Input data-testid="lead-form-revenue" type="number" value={form.revenue} onChange={(e) => setForm({ ...form, revenue: e.target.value })} className="bg-surface-2 border-white/10" />
              </div>
              <div className="space-y-1">
                <Label>Priority</Label>
                <Select value={form.priority} onValueChange={(v) => setForm({ ...form, priority: v })}>
                  <SelectTrigger data-testid="lead-form-priority" className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent>{Object.entries(PRIORITY_CONFIG).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label>Notes</Label>
              <Textarea data-testid="lead-form-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="bg-surface-2 border-white/10" />
            </div>
            <DialogFooter>
              <Button type="submit" data-testid="lead-form-submit" disabled={saving}>{saving ? "Creating..." : "Create Lead"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="import-csv-dialog">
          <DialogHeader><DialogTitle>Import Leads from CSV</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-xs text-graphite">
              CSV must include a <code className="font-mono">company</code> column. Optional columns: website,
              industry, employees, revenue, location, source, priority, email, phone, linkedin, notes, stage.
            </p>
            <Input
              data-testid="import-csv-file-input"
              type="file"
              accept=".csv"
              disabled={importing}
              onChange={importCsv}
              className="bg-surface-2 border-white/10"
            />
            {importResult && (
              <div data-testid="import-csv-result" className="text-sm space-y-1 rounded-lg bg-surface-2 border border-white/10 p-3">
                <p className="text-success">Imported: {importResult.imported}</p>
                {importResult.skipped_duplicates > 0 && (
                  <p className="text-graphite" data-testid="import-csv-skipped">
                    Skipped {importResult.skipped_duplicates} already in your pipeline
                  </p>
                )}
                {importResult.errors?.length > 0 && (
                  <div className="text-danger">
                    <p>Notes:</p>
                    <ul className="list-disc pl-5 text-xs">{importResult.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={wipeOpen} onOpenChange={setWipeOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="delete-all-leads-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-danger">
              <AlertTriangle className="h-4 w-4" /> Delete all leads
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 text-sm">
            <p className="text-graphite">
              This cannot be undone. There is no backup and no restore.
            </p>

            {/* The counts come from the server, not from what happens to be
                loaded on screen. */}
            {wipePreview ? (
              <div className="rounded-lg border border-danger/25 bg-danger/5 p-3 space-y-1 font-mono text-xs">
                <div className="flex justify-between" data-testid="wipe-count-leads">
                  <span className="text-graphite">Leads</span>
                  <span className="font-semibold text-danger">{wipePreview.leads}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-graphite">Activity records</span>
                  <span>{wipePreview.activities}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-graphite">Linked contacts</span>
                  <span>{wipePreview.contacts}</span>
                </div>
                {/* Called out separately: this is live outreach being stopped
                    mid-sequence, not just rows going away. */}
                {wipePreview.enrollments > 0 && (
                  <div className="flex justify-between" data-testid="wipe-count-enrollments">
                    <span className="text-graphite">Active campaign sequences</span>
                    <span className="text-danger">{wipePreview.enrollments}</span>
                  </div>
                )}
                {wipePreview.won_excluded > 0 && (
                  <div className="flex justify-between border-t border-white/10 pt-1 mt-1">
                    <span className="text-graphite">Won leads kept</span>
                    <span className="text-success">{wipePreview.won_excluded}</span>
                  </div>
                )}
              </div>
            ) : (
              <Skeleton className="h-20 w-full" />
            )}

            <label className="flex items-start gap-2.5 cursor-pointer">
              <Checkbox
                data-testid="wipe-include-won"
                checked={wipeIncludeWon}
                onCheckedChange={(v) => {
                  const next = Boolean(v);
                  setWipeIncludeWon(next);
                  loadWipePreview(next);
                }}
                className="mt-0.5"
              />
              <span className="text-xs text-graphite leading-relaxed">
                Also delete won leads.{" "}
                <span className="text-ash">
                  Won leads already produced a client, a project and an invoice.
                  Deleting them does not undo any of that — it leaves those
                  records with no deal behind them.
                </span>
              </span>
            </label>

            <div className="space-y-1.5">
              <Label className="text-xs">
                Type <span className="font-mono text-danger">DELETE</span> to confirm
              </Label>
              <Input
                data-testid="wipe-confirm-input"
                value={wipeConfirm}
                onChange={(e) => setWipeConfirm(e.target.value)}
                placeholder="DELETE"
                autoComplete="off"
                className="bg-surface-2 border-white/10 font-mono"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" className="border-white/10"
                    onClick={() => setWipeOpen(false)} data-testid="wipe-cancel-btn">
              Cancel
            </Button>
            <Button
              data-testid="wipe-confirm-btn"
              onClick={wipeAll}
              disabled={wipeConfirm !== "DELETE" || wiping || !wipePreview?.leads}
              className="bg-danger text-white hover:bg-danger/90"
            >
              {wiping ? "Deleting..." : `Delete ${wipePreview?.leads ?? 0} leads`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

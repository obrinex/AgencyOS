import { useEffect, useState, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Plus, KanbanSquare, Building2, DollarSign, Upload, Link2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { STAGE_CONFIG, STAGES_LIST, PRIORITY_CONFIG } from "@/lib/statusConfig";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

const emptyForm = { company: "", website: "", industry: "", email: "", phone: "", location: "", revenue: "", priority: "medium", source: "manual", notes: "" };

export default function CRMPipeline() {
  const [leads, setLeads] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [dragStage, setDragStage] = useState(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importing, setImporting] = useState(false);
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const load = async () => {
    const { data } = await api.get("/leads");
    setLeads(data);
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
    setLeads((prev) => prev.map((l) => (l.id === leadId ? { ...l, stage } : l)));
    try {
      const { data } = await api.patch(`/leads/${leadId}/stage`, { stage });
      if (data.automation) {
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
          </div>
        }
      />

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
              <span className="text-[11px] font-mono text-carbon">{byStage[stage]?.length || 0}</span>
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
                  className="cursor-pointer rounded-lg border border-white/10 bg-surface-2 p-3 hover:border-white/25 transition-colors"
                >
                  <p className="text-sm font-medium truncate">{lead.company}</p>
                  {lead.revenue > 0 && (
                    <p className="mt-1 flex items-center gap-1 text-xs font-mono text-graphite"><DollarSign className="h-3 w-3" />{lead.revenue.toLocaleString()}</p>
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
                <Label>Est. Revenue ($)</Label>
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
                {importResult.errors?.length > 0 && (
                  <div className="text-danger">
                    <p>Errors:</p>
                    <ul className="list-disc pl-5 text-xs">{importResult.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

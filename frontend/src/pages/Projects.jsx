import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Plus, FolderKanban, LayoutGrid, List as ListIcon } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { PROJECT_STATUS_CONFIG, PROJECT_STATUS_LIST } from "@/lib/statusConfig";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

const emptyForm = { name: "", client_id: "", description: "", status: "planning", budget: "" };

export default function Projects() {
  const [projects, setProjects] = useState(null);
  const [clients, setClients] = useState([]);
  const [view, setView] = useState("kanban");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const load = async () => {
    const [p, c] = await Promise.all([api.get("/projects"), api.get("/clients")]);
    setProjects(p.data);
    setClients(c.data);
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (params.get("new") === "1") { setOpen(true); params.delete("new"); setParams(params); }
  }, [params]);

  const create = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/projects", { ...form, budget: form.budget ? parseFloat(form.budget) : 0, client_id: form.client_id || null });
      toast.success("Project created");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  if (!projects) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  const byStatus = {};
  PROJECT_STATUS_LIST.forEach((s) => (byStatus[s] = projects.filter((p) => p.status === s)));

  return (
    <div className="p-6" data-testid="projects-page">
      <PageHeader
        title="Projects"
        description={`${projects.length} projects`}
        actions={
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-white/10 bg-surface-1 p-0.5">
              <button data-testid="view-toggle-kanban" onClick={() => setView("kanban")} className={`p-1.5 rounded-md ${view === "kanban" ? "bg-surface-2" : ""}`}><LayoutGrid className="h-3.5 w-3.5" /></button>
              <button data-testid="view-toggle-list" onClick={() => setView("list")} className={`p-1.5 rounded-md ${view === "list" ? "bg-surface-2" : ""}`}><ListIcon className="h-3.5 w-3.5" /></button>
            </div>
            <Button data-testid="open-create-project-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New Project</Button>
          </div>
        }
      />

      {projects.length === 0 ? (
        <EmptyState icon={FolderKanban} title="No projects yet" description="Projects are created automatically when a deal is won, or you can create one manually." testId="projects-empty-state" />
      ) : view === "kanban" ? (
        <div className="flex gap-4 overflow-x-auto pb-4" data-testid="projects-kanban">
          {PROJECT_STATUS_LIST.map((status) => (
            <div key={status} className="w-64 shrink-0 rounded-xl border border-white/10 bg-surface-1/60">
              <div className="flex items-center justify-between px-3 py-2.5 border-b border-white/10">
                <span className="font-mono text-[11px] uppercase text-ash">{PROJECT_STATUS_CONFIG[status].label}</span>
                <span className="text-[11px] font-mono text-carbon">{byStatus[status].length}</span>
              </div>
              <div className="p-2 space-y-2 min-h-[80px]">
                {byStatus[status].map((p) => (
                  <div key={p.id} onClick={() => navigate(`/projects/${p.id}`)} data-testid={`project-card-${p.id}`} className="cursor-pointer rounded-lg border border-white/10 bg-surface-2 p-3 hover:border-white/25">
                    <p className="text-sm font-medium truncate">{p.name}</p>
                    <Progress value={p.progress || 0} className="h-1 mt-2 bg-surface-3" />
                    <p className="text-[10px] font-mono text-carbon mt-1">{p.progress || 0}% · {p.tasks_count} tasks</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-2" data-testid="projects-list">
          {projects.map((p) => (
            <Card key={p.id} onClick={() => navigate(`/projects/${p.id}`)} data-testid={`project-row-${p.id}`} className="p-4 bg-surface-1 border-white/10 cursor-pointer hover:border-white/25 flex items-center justify-between gap-4">
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{p.name}</p>
                <p className="text-xs text-graphite">{p.tasks_count} tasks · {p.progress || 0}% complete</p>
              </div>
              <StatusBadge config={PROJECT_STATUS_CONFIG} value={p.status} />
            </Card>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-project-dialog">
          <DialogHeader><DialogTitle>New Project</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="space-y-1"><Label>Name *</Label><Input data-testid="project-form-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1">
              <Label>Client</Label>
              <Select value={form.client_id} onValueChange={(v) => setForm({ ...form, client_id: v })}>
                <SelectTrigger data-testid="project-form-client" className="bg-surface-2 border-white/10"><SelectValue placeholder="Select client (optional)" /></SelectTrigger>
                <SelectContent>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.company_name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Status</Label>
                <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
                  <SelectTrigger data-testid="project-form-status" className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent>{PROJECT_STATUS_LIST.map((s) => <SelectItem key={s} value={s}>{PROJECT_STATUS_CONFIG[s].label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1"><Label>Budget ($)</Label><Input data-testid="project-form-budget" type="number" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            </div>
            <DialogFooter><Button type="submit" data-testid="project-form-submit" disabled={saving}>{saving ? "Creating..." : "Create Project"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

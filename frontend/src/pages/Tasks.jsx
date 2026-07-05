import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Plus, CheckSquare } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { TASK_STATUS_CONFIG, TASK_STATUS_LIST, PRIORITY_CONFIG } from "@/lib/statusConfig";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import DatePicker from "@/components/DatePicker";
import { format } from "date-fns";
import { toast } from "sonner";

const emptyForm = { title: "", priority: "medium", due_date: "", related_type: "personal" };

export default function Tasks() {
  const { user } = useAuth();
  const [tasks, setTasks] = useState(null);
  const [filter, setFilter] = useState("mine");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [params, setParams] = useSearchParams();

  const load = async () => {
    const query = filter === "mine" ? `?assignee_id=${user.id}` : "";
    const { data } = await api.get(`/tasks${query}`);
    setTasks(data);
  };

  useEffect(() => { load(); }, [filter]);
  useEffect(() => {
    if (params.get("new") === "1") { setOpen(true); params.delete("new"); setParams(params); }
  }, [params]);

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/tasks", { ...form, assignee_id: user.id });
      toast.success("Task created");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const toggleDone = async (task) => {
    const status = task.status === "done" ? "todo" : "done";
    await api.patch(`/tasks/${task.id}/status?status=${status}`);
    load();
  };

  if (!tasks) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="tasks-page">
      <PageHeader
        title="Tasks"
        description="Manage personal and team tasks"
        actions={
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-white/10 bg-surface-1 p-0.5">
              <button data-testid="filter-my-tasks" onClick={() => setFilter("mine")} className={`px-2.5 py-1 text-xs rounded-md ${filter === "mine" ? "bg-surface-2" : ""}`}>My Tasks</button>
              <button data-testid="filter-team-tasks" onClick={() => setFilter("team")} className={`px-2.5 py-1 text-xs rounded-md ${filter === "team" ? "bg-surface-2" : ""}`}>Team Tasks</button>
            </div>
            <Button data-testid="open-create-task-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New Task</Button>
          </div>
        }
      />
      {tasks.length === 0 ? (
        <EmptyState icon={CheckSquare} title="No tasks yet" description="Create a task to start tracking your work." testId="tasks-empty-state" />
      ) : (
        <div className="space-y-2" data-testid="tasks-list">
          {tasks.map((t) => (
            <div key={t.id} data-testid={`task-row-${t.id}`} className="flex items-center gap-3 rounded-lg border border-white/10 bg-surface-1 px-4 py-3">
              <button data-testid={`task-toggle-${t.id}`} onClick={() => toggleDone(t)} className={`h-4 w-4 rounded-full border shrink-0 ${t.status === "done" ? "bg-success border-success" : "border-graphite"}`} />
              <div className="flex-1 min-w-0">
                <p className={`text-sm truncate ${t.status === "done" ? "line-through text-graphite" : ""}`}>{t.title}</p>
                {t.due_date && <p className="text-[10px] font-mono text-carbon">Due {format(new Date(t.due_date), "MMM d, yyyy")}</p>}
              </div>
              <StatusBadge config={PRIORITY_CONFIG} value={t.priority} />
              <StatusBadge config={TASK_STATUS_CONFIG} value={t.status} />
            </div>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-task-dialog">
          <DialogHeader><DialogTitle>New Task</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="space-y-1"><Label>Title *</Label><Input data-testid="task-form-title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Priority</Label>
                <Select value={form.priority} onValueChange={(v) => setForm({ ...form, priority: v })}>
                  <SelectTrigger data-testid="task-form-priority" className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent>{Object.entries(PRIORITY_CONFIG).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1"><Label>Due Date</Label><DatePicker testId="task-form-due-date" value={form.due_date} onChange={(v) => setForm({ ...form, due_date: v })} /></div>
            </div>
            <DialogFooter><Button type="submit" data-testid="task-form-submit">Create Task</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Plus, Flag, DollarSign, Building2, Timer, Trash2, Link2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { PROJECT_STATUS_CONFIG, PROJECT_STATUS_LIST, TASK_STATUS_CONFIG, TASK_STATUS_LIST, PRIORITY_CONFIG } from "@/lib/statusConfig";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import DatePicker from "@/components/DatePicker";
import { toast } from "sonner";

const emptyTask = { title: "", priority: "medium", due_date: "" };

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [project, setProject] = useState(null);
  const [taskOpen, setTaskOpen] = useState(false);
  const [taskForm, setTaskForm] = useState(emptyTask);
  const [milestoneTitle, setMilestoneTitle] = useState("");
  const [time, setTime] = useState(null);
  const [timeForm, setTimeForm] = useState({ description: "", hours: "" });

  const load = async () => {
    const [{ data }, t] = await Promise.all([api.get(`/projects/${id}`), api.get(`/projects/${id}/time`)]);
    setProject(data);
    setTime(t.data);
  };

  const logTime = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/projects/${id}/time`, { description: timeForm.description, hours: parseFloat(timeForm.hours) });
      toast.success("Time logged");
      setTimeForm({ description: "", hours: "" });
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const removeTime = async (entryId) => {
    await api.delete(`/time/${entryId}`);
    load();
  };

  useEffect(() => { load(); }, [id]);

  const changeStatus = async (status) => {
    await api.put(`/projects/${id}`, { status });
    load();
  };

  const createTask = async (e) => {
    e.preventDefault();
    try {
      await api.post("/tasks", { ...taskForm, related_type: "project", related_id: id, assignee_id: user.id });
      toast.success("Task added");
      setTaskOpen(false);
      setTaskForm(emptyTask);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const moveTask = async (taskId, status) => {
    await api.patch(`/tasks/${taskId}/status?status=${status}`);
    load();
  };

  const addMilestone = async () => {
    if (!milestoneTitle.trim()) return;
    await api.post(`/projects/${id}/milestones`, { title: milestoneTitle });
    setMilestoneTitle("");
    load();
  };

  const toggleMilestone = async (mid) => {
    await api.patch(`/milestones/${mid}`);
    load();
  };

  if (!project) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  const byStatus = {};
  TASK_STATUS_LIST.forEach((s) => (byStatus[s] = project.tasks.filter((t) => t.status === s)));
  const profit = (project.budget || 0) - (project.cost || 0);

  return (
    <div className="p-6 space-y-5" data-testid="project-detail-page">
      <button onClick={() => navigate("/projects")} className="flex items-center gap-1.5 text-sm text-graphite hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Projects
      </button>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">{project.name}</h1>
          {project.client && <p className="flex items-center gap-1.5 text-sm text-graphite mt-1"><Building2 className="h-3.5 w-3.5" /> {project.client.company_name}</p>}
        </div>
        <div className="flex items-center gap-2">
          <Button
            data-testid="copy-status-link-btn"
            size="sm" variant="outline" className="gap-1.5 border-white/10"
            onClick={async () => {
              try {
                const { data } = await api.post(`/projects/${id}/share`);
                await navigator.clipboard.writeText(`${window.location.origin}/status/${data.share_token}`);
                toast.success("Status link copied — share it with your client");
              } catch (err) {
                toast.error(formatApiError(err.response?.data?.detail));
              }
            }}
          >
            <Link2 className="h-3.5 w-3.5" /> Client Status Link
          </Button>
          <Select value={project.status} onValueChange={changeStatus}>
            <SelectTrigger data-testid="project-status-select" className="w-48 bg-surface-1 border-white/10"><SelectValue /></SelectTrigger>
            <SelectContent>{PROJECT_STATUS_LIST.map((s) => <SelectItem key={s} value={s}>{PROJECT_STATUS_CONFIG[s].label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Budget</p><p className="font-display text-xl font-bold">${(project.budget || 0).toLocaleString()}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Cost</p><p className="font-display text-xl font-bold">${(project.cost || 0).toLocaleString()}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Profit</p><p className={`font-display text-xl font-bold ${profit >= 0 ? "text-success" : "text-danger"}`}>${profit.toLocaleString()}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Health</p><StatusBadge config={{ green: { label: "Healthy", color: "success" }, yellow: { label: "At Risk", color: "warning" }, red: { label: "Critical", color: "danger" } }} value={project.health} /></Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <p className="font-display font-semibold">Tasks</p>
            <Button data-testid="open-create-task-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={() => setTaskOpen(true)}><Plus className="h-3.5 w-3.5" /> Add Task</Button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3" data-testid="project-tasks-kanban">
            {TASK_STATUS_LIST.map((status) => (
              <div key={status} className="rounded-xl border border-white/10 bg-surface-1/60">
                <div className="px-2.5 py-2 border-b border-white/10 font-mono text-[10px] uppercase text-ash">{TASK_STATUS_CONFIG[status].label} ({byStatus[status].length})</div>
                <div className="p-1.5 space-y-1.5 min-h-[60px]">
                  {byStatus[status].map((t) => (
                    <div key={t.id} data-testid={`task-card-${t.id}`} className="rounded-lg bg-surface-2 border border-white/10 p-2 text-xs">
                      <p className="truncate">{t.title}</p>
                      <Select value={t.status} onValueChange={(v) => moveTask(t.id, v)}>
                        <SelectTrigger className="h-6 mt-1.5 text-[10px] bg-surface-3 border-white/10"><SelectValue /></SelectTrigger>
                        <SelectContent>{TASK_STATUS_LIST.map((s) => <SelectItem key={s} value={s} className="text-xs">{TASK_STATUS_CONFIG[s].label}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3">
          <p className="font-display font-semibold flex items-center gap-1.5"><Flag className="h-4 w-4" /> Milestones</p>
          <div className="flex gap-2">
            <Input data-testid="milestone-input" value={milestoneTitle} onChange={(e) => setMilestoneTitle(e.target.value)} placeholder="New milestone..." className="bg-surface-1 border-white/10" />
            <Button data-testid="milestone-add-btn" size="sm" onClick={addMilestone}>Add</Button>
          </div>
          <div className="space-y-1.5">
            {project.milestones?.map((m) => (
              <div key={m.id} onClick={() => toggleMilestone(m.id)} data-testid={`milestone-item-${m.id}`} className="flex items-center gap-2 rounded-lg border border-white/10 bg-surface-1 px-3 py-2 text-sm cursor-pointer">
                <span className={`h-2 w-2 rounded-full ${m.completed ? "bg-success" : "bg-graphite"}`} />
                <span className={m.completed ? "line-through text-graphite" : ""}>{m.title}</span>
              </div>
            ))}
            {project.milestones?.length === 0 && <p className="text-xs text-graphite">No milestones yet</p>}
          </div>

          <div className="pt-4">
            <div className="flex items-center justify-between mb-2">
              <p className="font-display font-semibold flex items-center gap-1.5"><Timer className="h-4 w-4" /> Time Tracking</p>
              {time && <p className="font-mono text-xs text-graphite">{time.total_hours.toFixed(1)}h total</p>}
            </div>
            <form onSubmit={logTime} className="flex gap-2 mb-2">
              <Input data-testid="time-desc-input" required value={timeForm.description} onChange={(e) => setTimeForm({ ...timeForm, description: e.target.value })} placeholder="What did you work on?" className="bg-surface-1 border-white/10" />
              <Input data-testid="time-hours-input" required type="number" step="0.25" min="0.25" max="24" value={timeForm.hours} onChange={(e) => setTimeForm({ ...timeForm, hours: e.target.value })} placeholder="hrs" className="bg-surface-1 border-white/10 w-20" />
              <Button data-testid="time-log-btn" size="sm" type="submit">Log</Button>
            </form>
            <div className="space-y-1.5">
              {time?.entries?.map((t) => (
                <div key={t.id} data-testid={`time-entry-${t.id}`} className="flex items-center gap-2 rounded-lg border border-white/10 bg-surface-1 px-3 py-2 text-sm group">
                  <span className="font-mono text-xs text-success shrink-0 w-12">{t.hours}h</span>
                  <span className="flex-1 truncate">{t.description}</span>
                  <span className="font-mono text-[10px] text-carbon shrink-0">{t.date}</span>
                  <button onClick={() => removeTime(t.id)} className="text-graphite hover:text-danger opacity-0 group-hover:opacity-100"><Trash2 className="h-3 w-3" /></button>
                </div>
              ))}
              {time?.entries?.length === 0 && <p className="text-xs text-graphite">No time logged yet</p>}
            </div>
          </div>
        </div>
      </div>

      <Dialog open={taskOpen} onOpenChange={setTaskOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-task-dialog">
          <DialogHeader><DialogTitle>New Task</DialogTitle></DialogHeader>
          <form onSubmit={createTask} className="space-y-3">
            <div className="space-y-1"><Label>Title *</Label><Input data-testid="task-form-title" required value={taskForm.title} onChange={(e) => setTaskForm({ ...taskForm, title: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Priority</Label>
                <Select value={taskForm.priority} onValueChange={(v) => setTaskForm({ ...taskForm, priority: v })}>
                  <SelectTrigger data-testid="task-form-priority" className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent>{Object.entries(PRIORITY_CONFIG).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1"><Label>Due Date</Label><DatePicker testId="task-form-due-date" value={taskForm.due_date} onChange={(v) => setTaskForm({ ...taskForm, due_date: v })} /></div>
            </div>
            <DialogFooter><Button type="submit" data-testid="task-form-submit">Add Task</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

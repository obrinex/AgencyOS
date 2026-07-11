import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { FolderKanban, CheckCircle2, Circle, Activity } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { format } from "date-fns";

const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api` });

const STATUS_LABELS = {
  planning: "Planning", onboarding: "Onboarding", development: "In Development",
  automation: "Automation Build", testing: "Testing", review: "In Review",
  waiting_client: "Waiting on Client", completed: "Completed", archived: "Archived",
};

export default function PublicProject() {
  const { token } = useParams();
  const [project, setProject] = useState(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    api.get(`/public/projects/${token}`)
      .then((r) => setProject(r.data))
      .catch(() => setNotFound(true));
  }, [token]);

  if (notFound) {
    return <div className="min-h-screen bg-background flex items-center justify-center p-6"><p className="text-graphite">This status page doesn't exist or the link has expired.</p></div>;
  }
  if (!project) {
    return <div className="min-h-screen bg-background flex items-center justify-center"><p className="text-graphite font-mono text-sm">Loading…</p></div>;
  }

  const healthColor = { green: "text-success", yellow: "text-warning", red: "text-danger" }[project.health] || "text-success";

  return (
    <div className="min-h-screen bg-background text-foreground p-6 flex justify-center" data-testid="public-project-page">
      <div className="max-w-xl w-full">
        <div className="text-center mb-8 mt-6">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-foreground text-background">
            <FolderKanban className="h-5 w-5" />
          </div>
          <h1 className="font-display text-2xl font-bold">{project.name}</h1>
          <p className="text-sm text-graphite mt-1">
            Project status{project.client_name ? ` · for ${project.client_name}` : ""} · by {project.agency_name}
          </p>
        </div>

        <Card className="p-6 bg-surface-1 border-white/10 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-mono text-[10px] uppercase text-graphite mb-1">Current Stage</p>
              <p className="font-display text-lg font-semibold">{STATUS_LABELS[project.status] || project.status}</p>
            </div>
            <div className="text-right">
              <p className="font-mono text-[10px] uppercase text-graphite mb-1">Health</p>
              <p className={`flex items-center gap-1.5 text-sm font-medium ${healthColor}`}>
                <Activity className="h-4 w-4" /> {project.health === "green" ? "On Track" : project.health === "yellow" ? "At Risk" : project.health === "red" ? "Needs Attention" : "On Track"}
              </p>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="font-mono text-[10px] uppercase text-graphite">Overall Progress</p>
              <p className="font-mono text-sm font-bold">{project.progress}%</p>
            </div>
            <Progress value={project.progress} className="h-2" />
            <p className="text-xs text-graphite mt-2">
              {project.tasks_summary.done} of {project.tasks_summary.total} tasks done · {project.tasks_summary.in_progress} in progress
            </p>
          </div>

          {project.milestones?.length > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase text-graphite mb-2">Milestones</p>
              <div className="space-y-1.5">
                {project.milestones.map((m, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    {m.completed ? <CheckCircle2 className="h-4 w-4 text-success shrink-0" /> : <Circle className="h-4 w-4 text-graphite shrink-0" />}
                    <span className={m.completed ? "text-graphite line-through" : ""}>{m.title}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {project.recent_completed?.length > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase text-graphite mb-2">Recently Completed</p>
              <div className="space-y-1">
                {project.recent_completed.map((t, i) => (
                  <p key={i} className="text-sm text-ash flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-success shrink-0" /> {t}</p>
                ))}
              </div>
            </div>
          )}

          {project.updated_at && (
            <p className="text-[11px] text-carbon text-center border-t border-white/10 pt-4">
              Last updated {format(new Date(project.updated_at), "MMMM d, yyyy")} · refreshes live
            </p>
          )}
        </Card>

        <p className="text-center font-mono text-[10px] text-carbon mt-6 tracking-widest uppercase">Powered by {project.agency_name}</p>
      </div>
    </div>
  );
}

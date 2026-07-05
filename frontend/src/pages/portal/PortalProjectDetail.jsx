import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import api from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { PROJECT_STATUS_CONFIG, TASK_STATUS_CONFIG } from "@/lib/statusConfig";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";

export default function PortalProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState(null);

  useEffect(() => {
    api.get(`/portal/projects/${id}`).then((r) => setProject(r.data));
  }, [id]);

  if (!project) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-5" data-testid="portal-project-detail-page">
      <button onClick={() => navigate("/portal/projects")} className="flex items-center gap-1.5 text-sm text-graphite hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Projects
      </button>
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">{project.name}</h1>
        <StatusBadge config={PROJECT_STATUS_CONFIG} value={project.status} />
      </div>
      <Card className="p-4 bg-surface-1 border-white/10">
        <Progress value={project.progress || 0} className="h-2 bg-surface-3" />
        <p className="text-sm text-graphite mt-2">{project.progress || 0}% complete</p>
      </Card>
      <div>
        <p className="font-display font-semibold mb-3">Tasks</p>
        <div className="space-y-2">
          {project.tasks?.map((t) => (
            <div key={t.id} className="flex items-center justify-between rounded-lg border border-white/10 bg-surface-1 px-3 py-2.5">
              <span className="text-sm">{t.title}</span>
              <StatusBadge config={TASK_STATUS_CONFIG} value={t.status} />
            </div>
          ))}
          {(!project.tasks || project.tasks.length === 0) && <p className="text-sm text-graphite py-6 text-center">No tasks yet</p>}
        </div>
      </div>
    </div>
  );
}

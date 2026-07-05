import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FolderKanban } from "lucide-react";
import api from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { PROJECT_STATUS_CONFIG } from "@/lib/statusConfig";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";

export default function PortalProjects() {
  const [projects, setProjects] = useState(null);

  useEffect(() => {
    api.get("/portal/projects").then((r) => setProjects(r.data));
  }, []);

  if (!projects) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="portal-projects-page">
      <PageHeader title="Projects" description={`${projects.length} projects`} />
      {projects.length === 0 ? (
        <EmptyState icon={FolderKanban} title="No projects yet" description="Your active projects will appear here." testId="portal-projects-empty" />
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {projects.map((p) => (
            <Link key={p.id} to={`/portal/projects/${p.id}`}>
              <Card data-testid={`portal-project-card-${p.id}`} className="p-4 bg-surface-1 border-white/10 hover:border-white/25">
                <div className="flex items-center justify-between mb-2">
                  <p className="font-medium">{p.name}</p>
                  <StatusBadge config={PROJECT_STATUS_CONFIG} value={p.status} />
                </div>
                <Progress value={p.progress || 0} className="h-1.5 bg-surface-3" />
                <p className="text-xs text-graphite mt-1.5">{p.progress || 0}% complete</p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

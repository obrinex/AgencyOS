import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, ListChecks } from "lucide-react";
import api from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { PROJECT_STATUS_CONFIG, TASK_STATUS_CONFIG } from "@/lib/statusConfig";
import { Skeleton } from "@/components/ui/skeleton";

/** One project, and the work under it.
 *
 *  The progress figure is stated as a fraction of the tasks as well as a
 *  percentage, because "60%" and "3 of 5 done" answer different questions and a
 *  client checking in is usually asking the second one.
 */
export default function PortalProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState(null);

  useEffect(() => {
    api.get(`/portal/projects/${id}`).then((r) => setProject(r.data)).catch(() => setProject(false));
  }, [id]);

  if (project === null) {
    return <div className="p-4 sm:p-6"><Skeleton className="h-64 w-full rounded-2xl bg-surface-1" /></div>;
  }
  if (project === false) {
    return (
      <div className="mx-auto max-w-3xl p-4 sm:p-6">
        <div className="obx-glass rounded-2xl px-6 py-14 text-center text-sm text-graphite">
          This project could not be found.
        </div>
      </div>
    );
  }

  const tasks = project.tasks || [];
  const done = tasks.filter((t) => ["done", "completed"].includes(t.status)).length;
  const progress = Math.min(100, Math.max(0, project.progress || 0));

  return (
    <div className="mx-auto max-w-3xl space-y-5 p-4 sm:p-6" data-testid="portal-project-detail-page">
      <button
        onClick={() => navigate("/portal/projects")}
        className="flex items-center gap-1.5 text-sm text-graphite transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Projects
      </button>

      <header className="obx-glass obx-sheen relative overflow-hidden rounded-2xl p-4 sm:p-5">
        <div className="obx-aurora pointer-events-none absolute inset-0" />
        <div className="relative z-10">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h1 className="font-display text-2xl font-bold tracking-tight">{project.name}</h1>
            <StatusBadge config={PROJECT_STATUS_CONFIG} value={project.status} />
          </div>

          <div className="mt-5 flex items-center gap-3">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
              <div
                className="h-full rounded-full bg-gradient-to-r from-primary/60 to-primary transition-[width] duration-700"
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="obx-figure shrink-0 font-mono text-sm font-medium">{progress}%</span>
          </div>
          {tasks.length > 0 && (
            <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-carbon">
              {done} of {tasks.length} tasks done
            </p>
          )}
        </div>
      </header>

      <section>
        <div className="mb-3 flex items-center gap-2">
          <ListChecks className="h-3.5 w-3.5 text-primary" />
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">Tasks</p>
        </div>

        {tasks.length === 0 ? (
          <div className="obx-glass rounded-2xl px-6 py-10 text-center text-sm text-graphite">
            No tasks yet.
          </div>
        ) : (
          <div className="space-y-2">
            {tasks.map((t, i) => (
              <div
                key={t.id}
                style={{ animationDelay: `${i * 35}ms` }}
                className="obx-glass obx-reveal flex items-center justify-between gap-3 rounded-xl px-4 py-3"
              >
                <span className="min-w-0 flex-1 truncate text-sm">{t.title}</span>
                <StatusBadge config={TASK_STATUS_CONFIG} value={t.status} />
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

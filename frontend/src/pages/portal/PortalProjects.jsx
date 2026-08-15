import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FolderKanban } from "lucide-react";
import api from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { PROJECT_STATUS_CONFIG } from "@/lib/statusConfig";
import { Skeleton } from "@/components/ui/skeleton";

/** Your projects.
 *
 *  The progress bar is the point of the card, so it gets a figure beside it
 *  rather than a caption under it — a client checking in wants the number, and
 *  a bar alone makes them estimate.
 */
export default function PortalProjects() {
  const [projects, setProjects] = useState(null);

  useEffect(() => {
    api.get("/portal/projects").then((r) => setProjects(r.data)).catch(() => setProjects([]));
  }, []);

  if (!projects) {
    return <div className="p-4 sm:p-6"><Skeleton className="h-64 w-full rounded-2xl bg-surface-1" /></div>;
  }

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6" data-testid="portal-projects-page">
      <header className="mb-5">
        <h1 className="font-display text-2xl font-bold tracking-tight">Projects</h1>
        <p className="mt-1 text-sm text-graphite">
          {projects.length === 0 ? "Nothing yet." : `${projects.length} in total`}
        </p>
      </header>

      {projects.length === 0 ? (
        <div className="obx-glass rounded-2xl px-6 py-14 text-center" data-testid="portal-projects-empty">
          <div className="obx-holo obx-glass relative mx-auto flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl">
            <FolderKanban className="relative z-10 h-5 w-5 text-primary" />
          </div>
          <p className="mt-4 text-sm">No projects yet.</p>
          <p className="mt-1 text-xs text-graphite">Your active work will appear here.</p>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {projects.map((p, i) => {
            const progress = Math.min(100, Math.max(0, p.progress || 0));
            return (
              <Link
                key={p.id}
                to={`/portal/projects/${p.id}`}
                data-testid={`portal-project-card-${p.id}`}
                style={{ animationDelay: `${i * 45}ms` }}
                className="obx-glass obx-lift obx-sheen obx-reveal rounded-2xl p-4 sm:p-5"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="font-display font-semibold leading-snug tracking-tight">{p.name}</p>
                  <StatusBadge config={PROJECT_STATUS_CONFIG} value={p.status} />
                </div>

                <div className="mt-4 flex items-center gap-3">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-primary/60 to-primary transition-[width] duration-700"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <span className="obx-figure shrink-0 font-mono text-[11px] text-ash">
                    {progress}%
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

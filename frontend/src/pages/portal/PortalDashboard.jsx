import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FolderKanban, Receipt, LifeBuoy, ArrowRight, Layers } from "lucide-react";
import api from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { PROJECT_STATUS_CONFIG } from "@/lib/statusConfig";
import { formatMoney } from "@/lib/currency";
import StatusBadge from "@/components/StatusBadge";
import { useAuth } from "@/contexts/AuthContext";

/** The first thing a client sees.
 *
 *  Four figures and the work in progress. Each figure is a link to the page it
 *  came from — a number a client cannot act on is a number they have to go
 *  looking for, and the old cards were dead ends.
 */

function greeting() {
  const hour = new Date().getHours();
  if (hour < 5) return "Still up";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function Kpi({ to, label, value, icon: Icon, tone, testId, index }) {
  return (
    <Link
      to={to}
      data-testid={testId}
      style={{ animationDelay: `${index * 50}ms` }}
      className="obx-glass obx-lift obx-sheen obx-reveal group relative overflow-hidden rounded-2xl p-4"
    >
      <div className="flex items-center gap-2 text-graphite">
        <Icon className="h-3.5 w-3.5 text-primary" />
        <p className="font-mono text-[9px] uppercase tracking-[0.16em]">{label}</p>
      </div>
      <p className={`obx-figure mt-2 font-display text-2xl font-bold ${tone || ""}`}>{value}</p>
      <ArrowRight className="absolute bottom-3 right-3 h-3.5 w-3.5 text-carbon opacity-0 transition-all duration-200 group-hover:translate-x-0.5 group-hover:opacity-100" />
    </Link>
  );
}

export default function PortalDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/portal/overview").then((r) => setData(r.data)).catch(() => setData(false));
  }, []);

  if (data === null) {
    return <div className="p-4 sm:p-6"><Skeleton className="h-64 w-full rounded-2xl bg-surface-1" /></div>;
  }
  if (data === false) {
    return (
      <div className="mx-auto max-w-4xl p-4 sm:p-6">
        <div className="obx-glass rounded-2xl p-6 text-sm text-graphite">
          Your overview could not be loaded.
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-7 p-4 sm:p-6" data-testid="portal-dashboard-page">
      <header className="obx-aurora relative overflow-hidden rounded-2xl">
        <div className="relative z-10 py-2">
          <h1 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">
            {greeting()}, <span className="obx-gradient-text">{user?.name?.split(" ")[0]}</span>
          </h1>
          <p className="mt-1 text-sm text-graphite">Where your account stands right now.</p>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        <Kpi
          index={0} to="/portal/projects" label="Active projects" icon={FolderKanban}
          value={data.active_projects_count} testId="portal-kpi-active-projects"
        />
        <Kpi
          index={1} to="/portal/invoices" label="Outstanding" icon={Receipt}
          value={formatMoney(data.outstanding_amount)} tone="text-warning"
          testId="portal-kpi-outstanding"
        />
        <Kpi
          index={2} to="/portal/support" label="Open tickets" icon={LifeBuoy}
          value={data.open_tickets_count} testId="portal-kpi-open-tickets"
        />
        <Kpi
          index={3} to="/portal/projects" label="Total projects" icon={Layers}
          value={data.projects_count} testId="portal-kpi-total-projects"
        />
      </div>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
            Recent projects
          </p>
          <Link
            to="/portal/projects"
            className="flex items-center gap-1 text-xs text-graphite transition-colors hover:text-primary"
          >
            All <ArrowRight className="h-3 w-3" />
          </Link>
        </div>

        {data.recent_projects.length === 0 ? (
          <div className="obx-glass rounded-2xl px-6 py-12 text-center">
            <FolderKanban className="mx-auto h-5 w-5 text-carbon" />
            <p className="mt-2 text-sm text-graphite">No projects yet.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {data.recent_projects.map((p, i) => (
              <Link
                key={p.id}
                to={`/portal/projects/${p.id}`}
                data-testid={`portal-project-row-${p.id}`}
                style={{ animationDelay: `${i * 40}ms` }}
                className="obx-glass obx-lift obx-sheen obx-reveal flex items-center justify-between gap-3 rounded-xl px-4 py-3"
              >
                <span className="truncate text-sm">{p.name}</span>
                <StatusBadge config={PROJECT_STATUS_CONFIG} value={p.status} />
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

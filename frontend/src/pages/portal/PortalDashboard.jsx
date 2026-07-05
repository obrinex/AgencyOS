import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FolderKanban, Receipt, LifeBuoy, ArrowRight } from "lucide-react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PROJECT_STATUS_CONFIG } from "@/lib/statusConfig";
import StatusBadge from "@/components/StatusBadge";
import { useAuth } from "@/contexts/AuthContext";

export default function PortalDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/portal/overview").then((r) => setData(r.data));
  }, []);

  if (!data) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6 space-y-6" data-testid="portal-dashboard-page">
      <div>
        <h1 className="font-display text-2xl font-bold">Welcome back, {user?.name?.split(" ")[0]}</h1>
        <p className="text-sm text-graphite mt-1">Here's an overview of your account</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 bg-surface-1 border-white/10" data-testid="portal-kpi-active-projects"><p className="text-[10px] font-mono uppercase text-graphite">Active Projects</p><p className="font-display text-xl font-bold">{data.active_projects_count}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10" data-testid="portal-kpi-outstanding"><p className="text-[10px] font-mono uppercase text-graphite">Outstanding</p><p className="font-display text-xl font-bold text-warning">${data.outstanding_amount.toLocaleString()}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10" data-testid="portal-kpi-open-tickets"><p className="text-[10px] font-mono uppercase text-graphite">Open Tickets</p><p className="font-display text-xl font-bold">{data.open_tickets_count}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10" data-testid="portal-kpi-total-projects"><p className="text-[10px] font-mono uppercase text-graphite">Total Projects</p><p className="font-display text-xl font-bold">{data.projects_count}</p></Card>
      </div>

      <div>
        <div className="flex items-center justify-between mb-3">
          <p className="font-display font-semibold flex items-center gap-2"><FolderKanban className="h-4 w-4" /> Recent Projects</p>
          <Link to="/portal/projects" className="text-xs text-graphite hover:text-foreground flex items-center gap-1">All <ArrowRight className="h-3 w-3" /></Link>
        </div>
        <div className="space-y-2">
          {data.recent_projects.length === 0 && <p className="text-sm text-graphite py-6 text-center">No projects yet</p>}
          {data.recent_projects.map((p) => (
            <Link key={p.id} to={`/portal/projects/${p.id}`} data-testid={`portal-project-row-${p.id}`} className="flex items-center justify-between rounded-lg border border-white/10 bg-surface-1 px-4 py-3 hover:border-white/25">
              <span className="text-sm">{p.name}</span>
              <StatusBadge config={PROJECT_STATUS_CONFIG} value={p.status} />
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

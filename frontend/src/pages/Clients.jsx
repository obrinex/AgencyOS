import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, HeartPulse } from "lucide-react";
import api from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";

export default function Clients() {
  const [clients, setClients] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/clients").then((r) => setClients(r.data));
  }, []);

  if (!clients) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="clients-page">
      <PageHeader title="Clients" description={`${clients.length} active client accounts`} />
      {clients.length === 0 ? (
        <EmptyState
          icon={Building2}
          title="No clients yet"
          description="Clients are created automatically when a deal is marked as Won in your Pipeline."
          testId="clients-empty-state"
        />
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {clients.map((c) => (
            <Card
              key={c.id}
              data-testid={`client-card-${c.id}`}
              onClick={() => navigate(`/clients/${c.id}`)}
              className="p-5 bg-surface-1 border-white/10 cursor-pointer hover:border-white/25 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 border border-white/10">
                  <Building2 className="h-4 w-4 text-graphite" />
                </div>
                <span className="flex items-center gap-1 text-xs font-mono text-success"><HeartPulse className="h-3 w-3" /> {c.health_score ?? 100}</span>
              </div>
              <p className="font-medium truncate">{c.company_name}</p>
              <p className="text-xs text-graphite">{c.industry || "—"}</p>
              <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                <div>
                  <p className="text-graphite">Revenue</p>
                  <p className="font-mono font-semibold text-success">${(c.revenue_generated || 0).toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-graphite">Outstanding</p>
                  <p className="font-mono font-semibold text-warning">${(c.outstanding_amount || 0).toLocaleString()}</p>
                </div>
              </div>
              <p className="mt-3 text-[11px] font-mono text-carbon">{c.projects_count || 0} project(s)</p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

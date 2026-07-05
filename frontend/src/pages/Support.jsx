import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LifeBuoy } from "lucide-react";
import api from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { TICKET_STATUS_CONFIG, PRIORITY_CONFIG } from "@/lib/statusConfig";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function Support() {
  const [tickets, setTickets] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/tickets").then((r) => setTickets(r.data));
  }, []);

  if (!tickets) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="support-page">
      <PageHeader title="Support Desk" description={`${tickets.length} tickets`} />
      {tickets.length === 0 ? (
        <EmptyState icon={LifeBuoy} title="No support tickets" description="Client support tickets will appear here once submitted from the Client Portal." testId="support-empty-state" />
      ) : (
        <div className="space-y-2" data-testid="tickets-list">
          {tickets.map((t) => (
            <Card key={t.id} onClick={() => navigate(`/support/${t.id}`)} data-testid={`ticket-row-${t.id}`} className="p-4 bg-surface-1 border-white/10 cursor-pointer hover:border-white/25 flex items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{t.subject}</p>
                <p className="text-xs text-graphite">{t.client_name || "Unknown client"}</p>
              </div>
              <StatusBadge config={PRIORITY_CONFIG} value={t.priority} />
              <StatusBadge config={TICKET_STATUS_CONFIG} value={t.status} />
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

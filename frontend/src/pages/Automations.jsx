import { useEffect, useState } from "react";
import { Zap, CheckCircle2, XCircle } from "lucide-react";
import api from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDistanceToNow } from "date-fns";

const TRIGGER_LABELS = { deal_won: "Deal Won → Client Onboarding", meeting_booked: "Meeting Booked → Prep Automation" };

export default function Automations() {
  const [logs, setLogs] = useState(null);

  useEffect(() => {
    api.get("/automations/logs").then((r) => setLogs(r.data));
  }, []);

  if (!logs) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="automations-page">
      <PageHeader title="Automation Center" description="Every automated workflow run across AgencyOS" />
      {logs.length === 0 ? (
        <EmptyState icon={Zap} title="No automations run yet" description="Automations trigger automatically — e.g. marking a deal as Won generates a client, project & invoice." testId="automations-empty-state" />
      ) : (
        <div className="space-y-3" data-testid="automation-logs-list">
          {logs.map((log) => (
            <Card key={log.id} data-testid={`automation-log-${log.id}`} className="p-4 bg-surface-1 border-white/10">
              <div className="flex items-center justify-between mb-2">
                <p className="font-medium flex items-center gap-2">
                  {log.status === "success" ? <CheckCircle2 className="h-4 w-4 text-success" /> : <XCircle className="h-4 w-4 text-danger" />}
                  {TRIGGER_LABELS[log.trigger] || log.trigger}
                </p>
                <span className="text-[10px] font-mono text-carbon">{formatDistanceToNow(new Date(log.created_at), { addSuffix: true })}</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {log.steps.map((s, i) => (
                  <span key={i} className="rounded-md border border-white/10 bg-surface-2 px-2 py-0.5 text-[10px] font-mono text-ash">{s.name}</span>
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

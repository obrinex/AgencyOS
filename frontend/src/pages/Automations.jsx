import { useEffect, useState } from "react";
import { Zap, CheckCircle2, XCircle } from "lucide-react";
import api, { formatRequestError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import LoadError from "@/components/LoadError";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { safeDistanceToNow } from "@/lib/dates";

const TRIGGER_LABELS = { deal_won: "Deal Won → Client Onboarding", meeting_booked: "Meeting Booked → Prep Automation" };

export default function Automations() {
  const [logs, setLogs] = useState(null);
  const [error, setError] = useState(null);

  // The `.then()` here used to have no `.catch()`. On any failure `logs`
  // stayed null and the skeleton below rendered forever - indistinguishable
  // from loading, and from having no automations at all.
  const load = async () => {
    setError(null);
    try {
      const { data } = await api.get("/automations/logs");
      setLogs(data);
    } catch (err) {
      setError(formatRequestError(err));
    }
  };

  useEffect(() => { load(); }, []);

  if (error) {
    return (
      <div className="p-6" data-testid="automations-page">
        <PageHeader title="Automation Center" description="Every automated workflow run across Obrinex CRM" />
        <LoadError message={error} onRetry={load} testId="automations-error" />
      </div>
    );
  }

  if (!logs) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="automations-page">
      <PageHeader title="Automation Center" description="Every automated workflow run across Obrinex CRM" />
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
                <span className="text-[10px] font-mono text-carbon">{safeDistanceToNow(log.created_at)}</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {/* `?? []` - older automation_log documents predate `steps`,
                    and .map on undefined took out the whole page. */}
                {(log.steps ?? []).map((s, i) => (
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

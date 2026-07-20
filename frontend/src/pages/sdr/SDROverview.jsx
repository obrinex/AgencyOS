import { useEffect, useState } from "react";
import { Bot, Power, ShieldAlert, Activity, Users, Building2, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import { format } from "date-fns";
import { toast } from "sonner";

const STAGE_LABELS = {
  prospect: "Prospect", contacted: "Contacted", qualified: "Qualified",
  interested: "Interested", discovery: "Discovery", meeting_scheduled: "Meeting",
  proposal_sent: "Proposal", negotiation: "Negotiation",
};

function Kpi({ label, value, hint, testId }) {
  return (
    <Card className="p-4 bg-surface-1 border-white/10" data-testid={testId}>
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">{label}</p>
      <p className="font-display text-2xl font-semibold tracking-tight mt-1.5">{value}</p>
      {hint && <p className="text-xs text-graphite mt-0.5">{hint}</p>}
    </Card>
  );
}

export default function SDROverview() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [data, setData] = useState(null);
  const [settings, setSettings] = useState(null);
  const [saving, setSaving] = useState(false);
  const [killDialog, setKillDialog] = useState(false);
  const [killReason, setKillReason] = useState("");

  const load = async () => {
    const [o, s] = await Promise.all([api.get("/sdr/overview"), api.get("/sdr/settings")]);
    setData(o.data);
    setSettings(s.data);
  };

  useEffect(() => { load(); }, []);

  const toggleModule = async (enabled) => {
    setSaving(true);
    try {
      const { data: updated } = await api.put("/sdr/settings", { module_enabled: enabled });
      setSettings(updated);
      toast.success(enabled ? "AI SDR enabled" : "AI SDR disabled");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const setKillSwitch = async (enabled, reason) => {
    setSaving(true);
    try {
      const { data: updated } = await api.post("/sdr/kill-switch", { enabled, reason: reason || null });
      setSettings(updated);
      setKillDialog(false);
      setKillReason("");
      toast.success(enabled ? "All outbound sending halted" : "Outbound sending resumed");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  if (!data || !settings) {
    return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;
  }

  const { leads, companies, conversion, health, recent_runs: recentRuns } = data;
  const hasAnyData = companies.total > 0 || leads.open > 0 || leads.won > 0;
  const activeStages = Object.entries(leads.by_stage || {})
    .filter(([stage]) => STAGE_LABELS[stage])
    .sort((a, b) => b[1] - a[1]);

  return (
    <div className="p-6 space-y-5" data-testid="sdr-overview-page">
      <PageHeader
        title="AI SDR"
        description="Autonomous prospecting — discovery, research, scoring and qualification"
        actions={
          isAdmin && (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <Label htmlFor="sdr-module-toggle" className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
                  Module
                </Label>
                <Switch
                  id="sdr-module-toggle"
                  data-testid="sdr-module-toggle"
                  checked={settings.module_enabled}
                  disabled={saving}
                  onCheckedChange={toggleModule}
                />
              </div>
              <Button
                size="sm"
                variant="outline"
                data-testid="sdr-kill-switch-btn"
                className={settings.kill_switch ? "border-success/40 text-success hover:text-success gap-1.5" : "border-danger/40 text-danger hover:text-danger gap-1.5"}
                onClick={() => (settings.kill_switch ? setKillSwitch(false) : setKillDialog(true))}
              >
                <Power className="h-3.5 w-3.5" />
                {settings.kill_switch ? "Resume sending" : "Halt sending"}
              </Button>
            </div>
          )
        }
      />

      {settings.kill_switch && (
        <Card className="p-4 bg-danger/10 border-danger/20" data-testid="sdr-kill-switch-banner">
          <p className="text-sm text-danger flex items-center gap-2">
            <ShieldAlert className="h-4 w-4" /> Kill switch is on — all outbound sending is halted.
          </p>
          {settings.kill_switch_reason && (
            <p className="text-xs text-graphite mt-1">
              {settings.kill_switch_reason}
              {settings.kill_switch_at && ` · ${format(new Date(settings.kill_switch_at), "MMM d, HH:mm")}`}
            </p>
          )}
        </Card>
      )}

      {!settings.module_enabled && !settings.kill_switch && (
        <Card className="p-4 bg-warning/10 border-warning/20" data-testid="sdr-disabled-banner">
          <p className="text-sm text-warning flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" /> The AI SDR module is off — no agents will run.
          </p>
          <p className="text-xs text-graphite mt-1">
            {isAdmin
              ? "Flip the Module switch above to start discovering and scoring leads."
              : "Ask an admin to enable it."}
          </p>
        </Card>
      )}

      {health.jobs_dead_letter > 0 && (
        <Card className="p-4 bg-danger/10 border-danger/20" data-testid="sdr-dead-letter-banner">
          <p className="text-sm text-danger flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {health.jobs_dead_letter} job{health.jobs_dead_letter === 1 ? "" : "s"} gave up after exhausting retries.
          </p>
          <p className="text-xs text-graphite mt-1">That work was abandoned — inspect and replay it from the Agents page.</p>
        </Card>
      )}

      {!hasAnyData ? (
        <EmptyState
          icon={Bot}
          title="No prospects yet"
          description="Once discovery runs, leads found, researched and scored by the SDR agents will appear here."
          testId="sdr-overview-empty"
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi
              label="Open pipeline"
              value={leads.open}
              hint={`${leads.qualified} qualified`}
              testId="sdr-kpi-open"
            />
            <Kpi
              label="Companies"
              value={companies.total}
              hint={`${Math.round(companies.enrichment_coverage * 100)}% enriched`}
              testId="sdr-kpi-companies"
            />
            <Kpi
              label="Needs review"
              value={leads.needs_review}
              hint="Borderline — a human decides"
              testId="sdr-kpi-review"
            />
            <Kpi
              label="Won rate"
              value={conversion.sample_size ? `${Math.round(conversion.won_rate * 100)}%` : "—"}
              hint={conversion.sample_size ? `of ${conversion.sample_size} closed` : "No closed leads yet"}
              testId="sdr-kpi-won"
            />
          </div>

          {activeStages.length > 0 && (
            <Card className="p-5 bg-surface-1 border-white/10" data-testid="sdr-funnel">
              <p className="font-display text-sm font-semibold mb-4">Pipeline by stage</p>
              <div className="space-y-2">
                {activeStages.map(([stage, count]) => {
                  const max = activeStages[0][1] || 1;
                  return (
                    <div key={stage} className="flex items-center gap-3" data-testid={`sdr-stage-${stage}`}>
                      <span className="w-28 shrink-0 text-xs text-graphite">{STAGE_LABELS[stage]}</span>
                      <div className="flex-1 h-2 rounded-full bg-surface-2 overflow-hidden">
                        <div className="h-full rounded-full bg-info" style={{ width: `${(count / max) * 100}%` }} />
                      </div>
                      <span className="w-10 shrink-0 text-right font-mono text-sm">{count}</span>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}
        </>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5 bg-surface-1 border-white/10" data-testid="sdr-health">
          <p className="font-display text-sm font-semibold mb-4">Agent health</p>
          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-graphite flex items-center gap-2"><Activity className="h-3.5 w-3.5" /> Jobs queued</span>
              <span className="font-mono">{health.jobs_queued}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-graphite flex items-center gap-2"><AlertTriangle className="h-3.5 w-3.5" /> Dead-lettered</span>
              <span className={`font-mono ${health.jobs_dead_letter > 0 ? "text-danger" : ""}`}>{health.jobs_dead_letter}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-graphite flex items-center gap-2"><Bot className="h-3.5 w-3.5" /> Failed runs</span>
              <span className={`font-mono ${health.agent_runs_failed > 0 ? "text-warning" : ""}`}>{health.agent_runs_failed}</span>
            </div>
          </div>
        </Card>

        <Card className="p-5 bg-surface-1 border-white/10" data-testid="sdr-channels">
          <p className="font-display text-sm font-semibold mb-4">Outbound channels</p>
          <div className="space-y-2.5">
            {Object.entries(settings.channels).map(([channel, on]) => (
              <div key={channel} className="flex items-center justify-between text-sm" data-testid={`sdr-channel-${channel}`}>
                <span className="text-graphite capitalize">{channel}</span>
                <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${on ? "bg-success/15 text-success" : "bg-surface-2 text-graphite"}`}>
                  {on ? "On" : "Off"}
                </span>
              </div>
            ))}
          </div>
          <p className="text-xs text-carbon mt-4">
            Sending stays off until deliverability is set up — see the AI SDR docs before enabling a channel.
          </p>
        </Card>
      </div>

      {recentRuns.length > 0 && (
        <Card className="p-5 bg-surface-1 border-white/10" data-testid="sdr-recent-runs">
          <p className="font-display text-sm font-semibold mb-4">Recent agent runs</p>
          <div className="space-y-2">
            {recentRuns.map((run) => (
              <div key={run.id} className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-surface-2 px-3 py-2" data-testid={`sdr-run-${run.id}`}>
                <span className="font-mono text-xs truncate">{run.agent_key}</span>
                <div className="flex items-center gap-3 shrink-0">
                  {run.duration_ms != null && <span className="font-mono text-[11px] text-carbon">{run.duration_ms}ms</span>}
                  <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${
                    run.status === "succeeded" ? "bg-success/15 text-success"
                      : run.status === "failed" ? "bg-danger/15 text-danger"
                      : "bg-surface-3 text-graphite"
                  }`}>
                    {run.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Dialog open={killDialog} onOpenChange={setKillDialog}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="sdr-kill-switch-dialog">
          <DialogHeader><DialogTitle>Halt all outbound sending?</DialogTitle></DialogHeader>
          <p className="text-sm text-graphite">
            Every queued and scheduled message stops immediately, across all channels and campaigns.
            Nothing is deleted — sending resumes where it left off when you turn this off.
          </p>
          <div className="space-y-1">
            <Label>Reason (recorded in the audit log)</Label>
            <Input
              data-testid="sdr-kill-reason"
              value={killReason}
              onChange={(e) => setKillReason(e.target.value)}
              placeholder="e.g. investigating a bounce spike"
              className="bg-surface-2 border-white/10"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" className="border-white/10" onClick={() => setKillDialog(false)}>Cancel</Button>
            <Button
              variant="destructive"
              data-testid="sdr-kill-confirm"
              disabled={saving}
              onClick={() => setKillSwitch(true, killReason)}
              className="gap-1.5"
            >
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Power className="h-3.5 w-3.5" />}
              Halt sending
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

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
    <Card className="p-4 bg-surface-1 card-interactive" data-testid={testId}>
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">{label}</p>
      <p className="font-display text-2xl font-semibold tracking-tight mt-1.5 tabular-nums">{value}</p>
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
  const [running, setRunning] = useState(false);
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

  const runLeadGen = async () => {
    setRunning(true);
    try {
      const { data } = await api.post("/sdr/run");
      const did = [
        data.researched ? `researched ${data.researched} lead${data.researched === 1 ? "" : "s"}` : null,
        data.drafted ? `drafted ${data.drafted} email${data.drafted === 1 ? "" : "s"}` : null,
        data.sent ? `queued ${data.sent} send${data.sent === 1 ? "" : "s"}` : null,
        data.replies ? `read ${data.replies} repl${data.replies === 1 ? "y" : "ies"}` : null,
      ].filter(Boolean);

      if (did.length) {
        toast.success(`Done — ${did.join(", ")}.`, {
          description: data.awaiting_approval
            ? `${data.awaiting_approval} email${data.awaiting_approval === 1 ? "" : "s"} waiting for your approval on the Outreach page.`
            : data.still_queued
            ? `${data.still_queued} job${data.still_queued === 1 ? "" : "s"} still working — run again in a minute.`
            : undefined,
        });
      } else if (data.still_queued) {
        toast.info(`Nothing finished yet — ${data.still_queued} job${data.still_queued === 1 ? "" : "s"} still in progress.`);
      } else {
        toast.info("Nothing to do. Add leads on the Lead Database page first.");
      }
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setRunning(false);
    }
  };

  const saveSetting = async (patch, message) => {
    setSaving(true);
    try {
      const { data: updated } = await api.put("/sdr/settings", patch);
      setSettings(updated);
      toast.success(message);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const toggleChannel = async (channel, on) => {
    setSaving(true);
    try {
      const { data: updated } = await api.put("/sdr/settings", {
        channels: { ...settings.channels, [channel]: on },
      });
      setSettings(updated);
      toast.success(
        on
          ? `${channel} sending enabled — messages can now leave the building`
          : `${channel} sending disabled`
      );
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
        title="Lead Gen Agent"
        description="Finds businesses, researches them, and writes the emails. You approve."
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

      {/* The one button. Everything below it is detail; this is the verb. */}
      <Card
        className="p-5 bg-surface-1 border-white/10 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
        data-testid="sdr-run-card"
      >
        <div className="min-w-0">
          <p className="font-display text-sm font-semibold">Run the agent now</p>
          <p className="text-xs text-graphite mt-1 max-w-xl">
            It works through everything due: researching new leads, scoring them,
            and writing emails for whoever qualifies. It runs on its own every few
            minutes — this is for when you would rather not wait. Give it up to a
            minute; anything unfinished keeps going in the background.
            {settings.module_enabled
              ? " Nothing is emailed without your approval."
              : " Turn the Module switch on first."}
          </p>
        </div>
        <Button
          size="sm"
          disabled={running || !settings.module_enabled || settings.kill_switch}
          onClick={runLeadGen}
          data-testid="sdr-run-btn"
          className="gap-2 shrink-0 transition-transform duration-150 active:scale-[0.97]"
        >
          {running
            ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Working…</>
            : <><Bot className="h-3.5 w-3.5" /> Run Lead Gen</>}
        </Button>
      </Card>

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
            {Object.entries(settings.channels).map(([channel, on]) => {
              // Only email is built. The rest are declared so the shape is
              // stable, but switching one on would promise a channel that has
              // no provider behind it.
              const available = channel === "email";
              return (
                <div key={channel} className="flex items-center justify-between text-sm" data-testid={`sdr-channel-${channel}`}>
                  <span className="text-graphite capitalize">{channel}</span>
                  {isAdmin && available ? (
                    <Switch
                      id={`sdr-channel-toggle-${channel}`}
                      data-testid={`sdr-channel-toggle-${channel}`}
                      checked={on}
                      disabled={saving}
                      onCheckedChange={(next) => toggleChannel(channel, next)}
                    />
                  ) : (
                    <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${on ? "bg-success/15 text-success" : "bg-surface-2 text-graphite"}`}>
                      {available ? (on ? "On" : "Off") : "Not built"}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
          <p className="text-xs text-carbon mt-4">
            Turning email on only permits sending — it does not start it. Nothing
            leaves until a campaign runs, a draft is approved, and Outreach is
            switched from Simulate to LIVE.
          </p>

          {isAdmin && (
            <div className="mt-4 pt-4 border-t border-white/10">
              <div className="flex items-center justify-between text-sm">
                <span className="text-graphite">Allow unlisted countries</span>
                <Switch
                  id="sdr-allow-unlisted-toggle"
                  data-testid="sdr-allow-unlisted-toggle"
                  checked={!!settings.allow_unlisted_countries}
                  disabled={saving}
                  onCheckedChange={(next) => saveSetting(
                    { allow_unlisted_countries: next },
                    next
                      ? "Unlisted countries allowed — check local law yourself"
                      : "Unlisted countries blocked again"
                  )}
                />
              </div>
              <p className="text-xs text-carbon mt-2">
                Leads in countries with no shipped compliance profile are blocked,
                because their cold-outreach law is not modelled here. Turning this on
                says you have checked it yourself. It cannot unblock Canada or
                Germany — both require prior consent for email by law.
              </p>
            </div>
          )}
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

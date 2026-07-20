import { useCallback, useEffect, useState } from "react";
import {
  Bot, Activity, AlertTriangle, RotateCcw, Play, Loader2, DollarSign, Clock, X,
} from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useAuth } from "@/contexts/AuthContext";
import { format } from "date-fns";
import { toast } from "sonner";

const RUN_STATUS_STYLE = {
  succeeded: "bg-success/15 text-success",
  failed: "bg-danger/15 text-danger",
  running: "bg-info/15 text-info",
};

const JOB_STATUS_STYLE = {
  succeeded: "bg-success/15 text-success",
  dead_letter: "bg-danger/15 text-danger",
  queued: "bg-surface-3 text-graphite",
  running: "bg-info/15 text-info",
  cancelled: "bg-surface-3 text-carbon",
};

function Stat({ icon: Icon, label, value, tone }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-graphite flex items-center gap-2">
        <Icon className="h-3.5 w-3.5" /> {label}
      </span>
      <span className={`font-mono ${tone || ""}`}>{value}</span>
    </div>
  );
}

function RunInspector({ runId, open, onOpenChange }) {
  const [run, setRun] = useState(null);

  useEffect(() => {
    setRun(null);
    if (!open || !runId) return;
    api.get(`/sdr/agents/runs/${runId}`).then(({ data }) => setRun(data)).catch(() => {});
  }, [open, runId]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="bg-surface-1 border-white/10 w-full sm:max-w-lg overflow-y-auto scrollbar-thin"
        data-testid="sdr-run-inspector"
      >
        {!run ? (
          <div className="space-y-3 pt-6"><Skeleton className="h-40 bg-surface-2" /></div>
        ) : (
          <>
            <SheetHeader><SheetTitle className="pr-8 text-left">{run.agent_key}</SheetTitle></SheetHeader>
            <div className="mt-5 space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${RUN_STATUS_STYLE[run.status] || "bg-surface-2 text-ash"}`}>
                  {run.status}
                </span>
                <span className="font-mono text-[10px] text-carbon">v{run.version}</span>
                <span className="font-mono text-[10px] text-carbon">{run.trigger}</span>
                <span className="font-mono text-[10px] text-carbon">
                  attempt {run.attempt}/{run.max_attempts}
                </span>
              </div>

              <div className="rounded-lg border border-white/10 bg-surface-2 p-3 space-y-2">
                <Stat icon={Clock} label="Duration" value={`${run.duration_ms ?? "—"} ms`} />
                <Stat
                  icon={DollarSign}
                  label="Cost (estimated)"
                  value={`$${(run.cost_usd_estimated || 0).toFixed(5)}`}
                />
                <Stat
                  icon={Activity}
                  label="Tokens"
                  value={`${run.input_tokens || 0} in / ${run.output_tokens || 0} out`}
                />
              </div>

              {run.error_message && (
                <div className="rounded-lg border border-danger/20 bg-danger/10 p-3">
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-danger mb-1">
                    {run.error_type}
                  </p>
                  <p className="text-sm text-danger break-words">{run.error_message}</p>
                </div>
              )}

              {run.guardrail_flags?.length > 0 && (
                <div className="rounded-lg border border-warning/20 bg-warning/10 p-3 space-y-1">
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-warning">
                    Guardrails
                  </p>
                  {run.guardrail_flags.map((flag, i) => (
                    <p key={i} className="text-xs text-warning break-words">
                      {flag.kind}
                      {flag.detail ? `: ${JSON.stringify(flag.detail).slice(0, 200)}` : ""}
                    </p>
                  ))}
                </div>
              )}

              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon mb-1">
                  Input
                </p>
                <pre className="rounded-lg border border-white/10 bg-surface-2 p-3 text-xs text-ash overflow-x-auto scrollbar-thin whitespace-pre-wrap break-words">
                  {JSON.stringify(run.input, null, 2)}
                </pre>
              </div>

              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon mb-1">
                  Output
                </p>
                <pre className="rounded-lg border border-white/10 bg-surface-2 p-3 text-xs text-ash overflow-x-auto scrollbar-thin whitespace-pre-wrap break-words">
                  {run.output ? JSON.stringify(run.output, null, 2) : "—"}
                </pre>
              </div>

              <p className="text-[11px] text-carbon font-mono">
                Personal data and secrets are redacted before a run is stored.
              </p>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

export default function SDRAgents() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [data, setData] = useState(null);
  const [runs, setRuns] = useState(null);
  const [deadLetters, setDeadLetters] = useState(null);
  const [inspectRunId, setInspectRunId] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [agents, runList, dead] = await Promise.all([
      api.get("/sdr/agents"),
      api.get("/sdr/agents/runs?limit=25"),
      api.get("/sdr/jobs/dead-letter"),
    ]);
    setData(agents.data);
    setRuns(runList.data.items);
    setDeadLetters(dead.data.jobs);
  }, []);

  useEffect(() => { load(); }, [load]);

  const drain = async () => {
    setBusy(true);
    try {
      const { data: report } = await api.post("/sdr/jobs/drain");
      toast.success(
        report.processed === 0
          ? "Nothing due in the queue"
          : `Processed ${report.processed} — ${report.succeeded} succeeded, ${report.failed} failed`
      );
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const replay = async (jobId) => {
    setBusy(true);
    try {
      await api.post(`/sdr/jobs/${jobId}/replay`);
      toast.success("Requeued with a fresh attempt budget");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  if (!data) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  const statsByAgent = Object.fromEntries((data.stats || []).map((s) => [s.agent_key, s]));

  return (
    <div className="p-6 space-y-5" data-testid="sdr-agents-page">
      <PageHeader
        title="AI Agents"
        description="Run history, queue health and dead-lettered work"
        actions={
          isAdmin && (
            <Button
              size="sm"
              data-testid="sdr-drain-btn"
              disabled={busy}
              className="gap-1.5"
              onClick={drain}
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              Run queue now
            </Button>
          )
        }
      />

      {/* The silent failure: if the external pinger dies, work just piles up.
          No error, no failed job — so it has to be said out loud. */}
      {data.jobs.queue_stalled && (
        <Card className="p-4 bg-warning/10 border-warning/20" data-testid="sdr-queue-stalled-alert">
          <p className="text-sm text-warning flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Nothing has drained for {Math.floor((data.jobs.queue_lag_minutes || 0) / 60)}h
            {(data.jobs.queue_lag_minutes || 0) % 60}m
          </p>
          <p className="text-xs text-graphite mt-1">
            The oldest queued job was due long ago and is still waiting, which means
            the external pinger has stopped calling the drain endpoint. Nothing is
            failing — it has simply stopped running. Check the pinger before assuming
            the pipeline is idle.
          </p>
        </Card>
      )}

      {data.jobs.dead_letter > 0 && (
        <Card className="p-4 bg-danger/10 border-danger/20" data-testid="sdr-dead-letter-alert">
          <p className="text-sm text-danger flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {data.jobs.dead_letter} job{data.jobs.dead_letter === 1 ? "" : "s"} gave up after
            exhausting their retries.
          </p>
          <p className="text-xs text-graphite mt-1">
            That work was abandoned. Inspect the error, fix the cause, then replay below.
          </p>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-4 bg-surface-1 border-white/10" data-testid="sdr-jobs-queued">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">Queued</p>
          <p className="font-display text-2xl font-semibold tracking-tight mt-1.5">{data.jobs.queued}</p>
          {data.jobs.oldest_queued_at && (
            <p className="text-xs text-graphite mt-0.5">
              oldest {format(new Date(data.jobs.oldest_queued_at), "MMM d, HH:mm")}
            </p>
          )}
        </Card>
        <Card className="p-4 bg-surface-1 border-white/10">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">Running</p>
          <p className="font-display text-2xl font-semibold tracking-tight mt-1.5">{data.jobs.running}</p>
        </Card>
        <Card className="p-4 bg-surface-1 border-white/10">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">Dead-lettered</p>
          <p className={`font-display text-2xl font-semibold tracking-tight mt-1.5 ${data.jobs.dead_letter > 0 ? "text-danger" : ""}`}>
            {data.jobs.dead_letter}
          </p>
        </Card>
        <Card className="p-4 bg-surface-1 border-white/10" data-testid="sdr-daily-spend">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">AI spend today</p>
          <p className="font-display text-2xl font-semibold tracking-tight mt-1.5">
            ${(data.daily_spend_usd || 0).toFixed(4)}
          </p>
          <p className="text-xs text-graphite mt-0.5">estimated</p>
        </Card>
      </div>

      <div className="space-y-2" data-testid="sdr-agent-cards">
        {data.agents.map((agent) => {
          const stats = statsByAgent[agent.key];
          return (
            <Card
              key={agent.key}
              className="p-4 bg-surface-1 border-white/10"
              data-testid={`sdr-agent-${agent.key}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium flex items-center gap-2">
                    <Bot className="h-3.5 w-3.5 text-carbon" /> {agent.key}
                  </p>
                  <p className="text-xs text-graphite mt-0.5">{agent.description}</p>
                  <p className="text-[11px] text-carbon font-mono mt-1">
                    v{agent.version} · queue {agent.queue} · ceiling ${agent.cost_ceiling_usd} ·
                    timeout {agent.timeout_ms}ms
                  </p>
                </div>
                <div className="text-right shrink-0">
                  {stats ? (
                    <>
                      <p className="font-mono text-sm">
                        <span className={stats.success_rate >= 0.9 ? "text-success" : stats.success_rate >= 0.6 ? "text-warning" : "text-danger"}>
                          {Math.round(stats.success_rate * 100)}%
                        </span>
                        <span className="text-carbon"> / {stats.total} runs</span>
                      </p>
                      <p className="text-[11px] text-carbon font-mono">
                        {stats.avg_duration_ms}ms avg · ${stats.cost_usd_estimated.toFixed(4)}
                      </p>
                    </>
                  ) : (
                    <p className="text-xs text-carbon font-mono">no runs in 24h</p>
                  )}
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      <Tabs defaultValue="runs">
        <TabsList className="bg-surface-2">
          <TabsTrigger value="runs" data-testid="sdr-tab-runs">Recent runs</TabsTrigger>
          <TabsTrigger value="dead" data-testid="sdr-tab-dead">
            Dead-lettered{deadLetters?.length ? ` (${deadLetters.length})` : ""}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="runs" className="mt-3">
          {!runs?.length ? (
            <EmptyState
              icon={Activity}
              title="No agent runs yet"
              description="Runs appear here as soon as an agent executes, whether it succeeds or fails."
              testId="sdr-runs-empty"
            />
          ) : (
            <div className="space-y-2" data-testid="sdr-runs-list">
              {runs.map((run) => (
                <button
                  key={run.id}
                  data-testid={`sdr-run-${run.id}`}
                  onClick={() => setInspectRunId(run.id)}
                  className="w-full flex items-center gap-3 rounded-lg border border-white/10 bg-surface-1 px-4 py-3 text-left hover:border-white/25"
                >
                  <span className="font-mono text-sm truncate flex-1">{run.agent_key}</span>
                  {run.entity_id && (
                    <span className="font-mono text-[11px] text-carbon truncate hidden sm:block">
                      {run.entity_type} {run.entity_id.slice(-6)}
                    </span>
                  )}
                  <span className="font-mono text-[11px] text-carbon">{run.duration_ms ?? "—"}ms</span>
                  <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${RUN_STATUS_STYLE[run.status] || "bg-surface-2 text-ash"}`}>
                    {run.status}
                  </span>
                </button>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="dead" className="mt-3">
          {!deadLetters?.length ? (
            <EmptyState
              icon={Bot}
              title="Nothing dead-lettered"
              description="Jobs land here only after exhausting every retry. An empty list is the healthy state."
              testId="sdr-dead-empty"
            />
          ) : (
            <div className="space-y-2" data-testid="sdr-dead-list">
              {deadLetters.map((job) => (
                <Card
                  key={job.id}
                  className="p-4 bg-surface-1 border-danger/20"
                  data-testid={`sdr-dead-${job.id}`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-sm">{job.agent_key}</p>
                      <p className="text-xs text-danger mt-0.5 break-words">
                        {job.last_error?.type}: {job.last_error?.message}
                      </p>
                      <p className="text-[11px] text-carbon font-mono mt-1">
                        {job.attempt} attempts · queue {job.queue}
                        {job.updated_at && ` · ${format(new Date(job.updated_at), "MMM d, HH:mm")}`}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      data-testid={`sdr-replay-${job.id}`}
                      disabled={busy}
                      className="border-white/10 gap-1.5 h-8 shrink-0"
                      onClick={() => replay(job.id)}
                    >
                      <RotateCcw className="h-3.5 w-3.5" /> Replay
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      <RunInspector
        runId={inspectRunId}
        open={!!inspectRunId}
        onOpenChange={(o) => !o && setInspectRunId(null)}
      />
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import {
  Bot, Sparkles, Activity, AlertTriangle, DollarSign, Cpu, Zap, CheckCircle2, XCircle,
} from "lucide-react";
import api from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { format } from "date-fns";

const RUN_STATUS_STYLE = {
  succeeded: "bg-success/15 text-success",
  failed: "bg-danger/15 text-danger",
  running: "bg-info/15 text-info",
};

const WINDOWS = [
  { value: "24", label: "Last 24 hours" },
  { value: "168", label: "Last 7 days" },
  { value: "720", label: "Last 30 days" },
];

function Kpi({ icon: Icon, label, value, hint, tone }) {
  return (
    <Card className="p-4 bg-surface-1 border-white/10">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon flex items-center gap-1.5">
        <Icon className="h-3 w-3" /> {label}
      </p>
      <p className={`font-display text-2xl font-semibold tracking-tight mt-1.5 ${tone || ""}`}>
        {value}
      </p>
      {hint && <p className="text-xs text-graphite mt-0.5">{hint}</p>}
    </Card>
  );
}

function RunInspector({ runId, open, onOpenChange }) {
  const [run, setRun] = useState(null);

  useEffect(() => {
    setRun(null);
    if (!open || !runId) return;
    api.get(`/ai-agents/runs/${runId}`).then(({ data }) => setRun(data)).catch(() => {});
  }, [open, runId]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="bg-surface-1 border-white/10 w-full sm:max-w-lg overflow-y-auto scrollbar-thin"
        data-testid="ai-run-inspector"
      >
        {!run ? (
          <div className="pt-6"><Skeleton className="h-40 bg-surface-2" /></div>
        ) : (
          <>
            <SheetHeader><SheetTitle className="pr-8 text-left">{run.agent_key}</SheetTitle></SheetHeader>
            <div className="mt-5 space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${RUN_STATUS_STYLE[run.status] || "bg-surface-2 text-ash"}`}>
                  {run.status}
                </span>
                <span className="font-mono text-[10px] text-carbon">v{run.version}</span>
                {run.provider_used && (
                  <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-surface-2 text-ash">
                    {run.provider_used}
                  </span>
                )}
                {run.model_used && (
                  <span className="font-mono text-[10px] text-carbon truncate">{run.model_used}</span>
                )}
              </div>

              <div className="rounded-lg border border-white/10 bg-surface-2 p-3 space-y-1.5 text-sm">
                <div className="flex justify-between"><span className="text-graphite">Duration</span><span className="font-mono">{run.duration_ms ?? "—"} ms</span></div>
                <div className="flex justify-between"><span className="text-graphite">Cost (est.)</span><span className="font-mono">${(run.cost_usd_estimated || 0).toFixed(5)}</span></div>
                <div className="flex justify-between"><span className="text-graphite">Tokens</span><span className="font-mono">{run.input_tokens || 0} in / {run.output_tokens || 0} out</span></div>
              </div>

              {run.error_message && (
                <div className="rounded-lg border border-danger/20 bg-danger/10 p-3">
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-danger mb-1">{run.error_type}</p>
                  <p className="text-sm text-danger break-words">{run.error_message}</p>
                </div>
              )}

              {run.guardrail_flags?.length > 0 && (
                <div className="rounded-lg border border-warning/20 bg-warning/10 p-3 space-y-1">
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-warning">Guardrails</p>
                  {run.guardrail_flags.map((flag, i) => (
                    <p key={i} className="text-xs text-warning break-words">
                      {flag.kind}{flag.detail ? `: ${JSON.stringify(flag.detail).slice(0, 180)}` : ""}
                    </p>
                  ))}
                </div>
              )}

              {["input", "output"].map((field) => (
                <div key={field}>
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon mb-1">{field}</p>
                  <pre className="rounded-lg border border-white/10 bg-surface-2 p-3 text-xs text-ash overflow-x-auto scrollbar-thin whitespace-pre-wrap break-words">
                    {run[field] ? JSON.stringify(run[field], null, 2) : "—"}
                  </pre>
                </div>
              ))}

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

export default function AIAgentsMonitor() {
  const [data, setData] = useState(null);
  const [runs, setRuns] = useState(null);
  const [hours, setHours] = useState("24");
  const [category, setCategory] = useState("all");
  const [inspectId, setInspectId] = useState(null);

  const load = useCallback(async () => {
    const [overview, runList] = await Promise.all([
      api.get(`/ai-agents/overview?hours=${hours}`),
      api.get(`/ai-agents/runs?limit=25${category !== "all" ? `&category=${category}` : ""}`),
    ]);
    setData(overview.data);
    setRuns(runList.data.items);
  }, [hours, category]);

  useEffect(() => { load(); }, [load]);

  if (!data) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  const { groups, totals, providers, active_provider_chain: chain, jobs } = data;
  const visible = category === "all" ? groups : groups.filter((g) => g.category === category);
  const configuredProviders = providers.filter((p) => p.configured);

  return (
    <div className="p-6 space-y-5" data-testid="ai-agents-monitor">
      <PageHeader
        title="AI Agents"
        description="Every AI capability in the dashboard — what it does, whether it is working, and what it costs"
        actions={
          <div className="flex items-center gap-2">
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger data-testid="ai-category-filter" className="w-[170px] bg-surface-2 border-white/10 h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All use cases</SelectItem>
                {groups.map((g) => (
                  <SelectItem key={g.category} value={g.category}>{g.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={hours} onValueChange={setHours}>
              <SelectTrigger data-testid="ai-window-filter" className="w-[150px] bg-surface-2 border-white/10 h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {WINDOWS.map((w) => (
                  <SelectItem key={w.value} value={w.value}>{w.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        }
      />

      {configuredProviders.length === 0 && (
        <Card className="p-4 bg-warning/10 border-warning/20" data-testid="ai-no-provider">
          <p className="text-sm text-warning flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" /> No AI provider is configured
          </p>
          <p className="text-xs text-graphite mt-1">
            Add at least one free API key below. Nothing AI-powered will work until you do.
          </p>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi icon={Activity} label="Runs" value={totals.total}
             hint={totals.success_rate != null ? `${Math.round(totals.success_rate * 100)}% succeeded` : "no runs in this window"} />
        <Kpi icon={XCircle} label="Failures" value={totals.failed}
             tone={totals.failed > 0 ? "text-danger" : ""} hint={totals.failed > 0 ? "inspect below" : "none"} />
        <Kpi icon={DollarSign} label="Spend" value={`$${(totals.cost_usd || 0).toFixed(4)}`} hint="estimated" />
        <Kpi icon={Cpu} label="Queued jobs" value={jobs?.queued ?? 0}
             tone={jobs?.dead_letter > 0 ? "text-danger" : ""}
             hint={jobs?.dead_letter > 0 ? `${jobs.dead_letter} dead-lettered` : "queue healthy"} />
      </div>

      {/* Capability catalogue, grouped by what the AI is used for. */}
      {visible.map((group) => (
        <div key={group.category} className="space-y-2" data-testid={`ai-group-${group.category}`}>
          <div>
            <p className="font-display text-sm font-semibold">{group.label}</p>
            <p className="text-xs text-graphite">{group.description}</p>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {group.items.map((item) => (
              <Card
                key={item.key}
                className="p-3.5 bg-surface-1 border-white/10"
                data-testid={`ai-capability-${item.key}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-sm flex items-center gap-1.5">
                      {item.kind === "agent"
                        ? <Bot className="h-3.5 w-3.5 text-carbon shrink-0" />
                        : <Sparkles className="h-3.5 w-3.5 text-carbon shrink-0" />}
                      <span className="truncate">{item.label}</span>
                    </p>
                    <p className="text-xs text-graphite mt-0.5">{item.description}</p>
                    <p className="text-[11px] text-carbon font-mono mt-1 truncate">
                      {item.kind === "agent" ? "agent" : "assistant"}
                      {item.surface ? ` · ${item.surface}` : ""}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    {item.stats ? (
                      <>
                        <p className="font-mono text-sm">
                          <span className={item.stats.success_rate >= 0.9 ? "text-success" : item.stats.success_rate >= 0.6 ? "text-warning" : "text-danger"}>
                            {Math.round(item.stats.success_rate * 100)}%
                          </span>
                          <span className="text-carbon"> / {item.stats.total}</span>
                        </p>
                        <p className="text-[11px] text-carbon font-mono">
                          {item.stats.avg_duration_ms}ms
                        </p>
                      </>
                    ) : (
                      <p className="text-[11px] text-carbon font-mono">no runs yet</p>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      ))}

      {/* Free provider chain. */}
      <Card className="p-5 bg-surface-1 border-white/10" data-testid="ai-providers">
        <p className="font-display text-sm font-semibold mb-1 flex items-center gap-2">
          <Zap className="h-3.5 w-3.5 text-carbon" /> AI providers
        </p>
        <p className="text-xs text-graphite mb-4">
          All free tiers, tried in order. A rate limit or quota refusal falls through to the
          next one — which is what makes free plans usable rather than a demo.
          {chain?.length > 0 && (
            <span className="block mt-1 font-mono text-[11px] text-ash">
              Active chain: {chain.join(" → ")}
            </span>
          )}
        </p>
        <div className="space-y-1.5">
          {providers.map((provider) => (
            <div
              key={provider.key}
              className="flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-surface-2 px-3 py-2"
              data-testid={`ai-provider-${provider.key}`}
            >
              {provider.configured
                ? <CheckCircle2 className="h-3.5 w-3.5 text-success shrink-0" />
                : <XCircle className="h-3.5 w-3.5 text-carbon shrink-0" />}
              <span className="text-sm w-32 shrink-0">{provider.label}</span>
              <span className="text-xs text-graphite flex-1 min-w-0">{provider.free_note}</span>
              <span className="font-mono text-[10px] text-carbon shrink-0">
                {provider.configured ? provider.model : provider.api_key_env}
              </span>
            </div>
          ))}
        </div>
      </Card>

      {/* Recent runs across everything. */}
      <div className="space-y-2">
        <p className="font-display text-sm font-semibold">Recent runs</p>
        {!runs?.length ? (
          <EmptyState
            icon={Activity}
            title="No runs in this window"
            description="Runs appear here as soon as any AI feature is used — agents and assistants alike."
            testId="ai-runs-empty"
          />
        ) : (
          <div className="space-y-2" data-testid="ai-runs-list">
            {runs.map((run) => (
              <button
                key={run.id}
                data-testid={`ai-run-${run.id}`}
                onClick={() => setInspectId(run.id)}
                className="w-full flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-surface-1 px-4 py-3 text-left hover:border-white/25"
              >
                <span className="font-mono text-sm truncate flex-1 min-w-0">{run.agent_key}</span>
                {run.provider_used && (
                  <span className="font-mono text-[10px] text-carbon hidden sm:block">{run.provider_used}</span>
                )}
                {run.created_at && (
                  <span className="font-mono text-[11px] text-carbon hidden md:block">
                    {format(new Date(run.created_at), "MMM d, HH:mm")}
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
      </div>

      <RunInspector runId={inspectId} open={!!inspectId} onOpenChange={(o) => !o && setInspectId(null)} />
    </div>
  );
}

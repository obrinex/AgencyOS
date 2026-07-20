import { useCallback, useEffect, useState } from "react";
import { Gauge, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

function Meter({ label, used, limit, hint }) {
  if (!limit) return null;
  const pct = Math.min(100, Math.round((used / limit) * 100));
  const tone = pct >= 100 ? "bg-danger" : pct >= 80 ? "bg-warning" : "bg-info";
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
          {label}
        </span>
        <span className="font-mono text-xs">
          {used.toLocaleString()} / {limit.toLocaleString()}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-surface-3 overflow-hidden">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      {hint && <p className="text-[11px] text-carbon font-mono mt-1">{hint}</p>}
    </div>
  );
}

export default function QuotaPanel() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [data, setData] = useState(null);
  const [leadsPerDay, setLeadsPerDay] = useState("");
  const [touches, setTouches] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const { data: quota } = await api.get("/sdr/quota");
    setData(quota);
    setLeadsPerDay(String(quota.daily_new_leads_cap ?? ""));
    setTouches(String(quota.fit?.touches_per_lead ?? 3));
    setPreview(null);
  }, []);

  useEffect(() => { load(); }, [load]);

  const simulate = async (nextLeads, nextTouches) => {
    try {
      const { data: result } = await api.post("/sdr/quota/simulate", {
        daily_new_leads_cap: parseInt(nextLeads, 10) || 0,
        touches_per_lead: parseInt(nextTouches, 10) || 3,
      });
      setPreview(result);
    } catch {
      setPreview(null);
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      const { data: updated } = await api.put("/sdr/settings", {
        daily_new_leads_cap: parseInt(leadsPerDay, 10) || 0,
        touches_per_lead: parseInt(touches, 10) || 3,
      });
      if (updated.quota_fit?.fits) {
        toast.success(`Set to ${updated.daily_new_leads_cap} new leads/day`);
      } else {
        toast.warning(updated.quota_fit?.warnings?.[0] || "Saved, but this exceeds the plan");
      }
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  if (!data) return <Skeleton className="h-48 bg-surface-1" />;

  const { plan, budget, fit } = data;
  const shown = preview || fit;
  const exhausted = budget.exhausted || [];

  return (
    <div className="space-y-4" data-testid="sdr-quota-panel">
      <p className="text-xs text-graphite max-w-2xl">
        New leads per day is not the same as emails per day. A sequence sends roughly one
        email per touch, so the monthly quota is what actually limits how many prospects
        can be approached — not the daily send limit.
      </p>

      {exhausted.length > 0 && (
        <Card className="p-4 bg-danger/10 border-danger/20" data-testid="sdr-quota-exhausted">
          <p className="text-sm text-danger flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {exhausted.includes("monthly")
              ? "Monthly send quota is exhausted — sending is blocked until it resets."
              : "Today's send cap is reached — sending resumes tomorrow."}
          </p>
        </Card>
      )}

      <Card className="p-4 bg-surface-1 border-white/10 space-y-4" data-testid="sdr-quota-meters">
        <div className="flex items-center justify-between">
          <p className="font-display text-sm font-semibold flex items-center gap-2">
            <Gauge className="h-3.5 w-3.5 text-carbon" /> {plan.label}
          </p>
          <span className="font-mono text-[11px] text-carbon">
            {plan.daily_limit?.toLocaleString()}/day · {plan.monthly_limit?.toLocaleString()}/month
          </span>
        </div>

        <Meter
          label="This month"
          used={budget.sent_this_month}
          limit={budget.monthly_limit}
          hint={
            budget.monthly_remaining != null
              ? `${budget.monthly_remaining.toLocaleString()} emails left this month`
              : null
          }
        />
        <Meter
          label="Today"
          used={budget.sent_today}
          limit={budget.daily_limit}
          hint={
            budget.daily_remaining != null
              ? `${budget.daily_remaining.toLocaleString()} emails left today`
              : null
          }
        />
        {plan.note && <p className="text-[11px] text-carbon">{plan.note}</p>}
      </Card>

      <Card className="p-4 bg-surface-1 border-white/10 space-y-3" data-testid="sdr-quota-planner">
        <p className="font-display text-sm font-semibold">How many leads a day?</p>

        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1 w-[150px]">
            <Label>New leads / day</Label>
            <Input
              type="number"
              min="0"
              data-testid="sdr-quota-leads"
              value={leadsPerDay}
              disabled={!isAdmin}
              onChange={(e) => { setLeadsPerDay(e.target.value); simulate(e.target.value, touches); }}
              className="bg-surface-2 border-white/10"
            />
          </div>
          <div className="space-y-1 w-[150px]">
            <Label>Touches per lead</Label>
            <Input
              type="number"
              min="1"
              data-testid="sdr-quota-touches"
              value={touches}
              disabled={!isAdmin}
              onChange={(e) => { setTouches(e.target.value); simulate(leadsPerDay, e.target.value); }}
              className="bg-surface-2 border-white/10"
            />
          </div>
          {isAdmin && (
            <Button size="sm" disabled={busy} onClick={save} data-testid="sdr-quota-save" className="gap-1.5">
              {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save
            </Button>
          )}
        </div>

        <div
          className={`rounded-lg border p-3 ${
            shown.fits ? "border-success/20 bg-success/10" : "border-warning/20 bg-warning/10"
          }`}
          data-testid="sdr-quota-verdict"
        >
          <p className={`text-sm flex items-start gap-2 ${shown.fits ? "text-success" : "text-warning"}`}>
            {shown.fits
              ? <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0" />
              : <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />}
            <span>
              {shown.new_leads_per_day} new leads/day × {shown.touches_per_lead} touches ≈{" "}
              <span className="font-mono">{shown.projected_monthly_sends.toLocaleString()}</span>{" "}
              emails/month
              {shown.monthly_limit
                ? ` against a ${shown.monthly_limit.toLocaleString()} limit.`
                : "."}
            </span>
          </p>
          {shown.warnings?.map((warning, index) => (
            <p key={index} className="text-xs text-graphite mt-1.5">{warning}</p>
          ))}
          {shown.fits && shown.recommended_new_leads_per_day != null && (
            <p className="text-[11px] text-carbon font-mono mt-1.5">
              Maximum sustainable at this sequence length: {shown.recommended_new_leads_per_day}/day
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}

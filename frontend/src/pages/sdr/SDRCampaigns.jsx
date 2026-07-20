import { useCallback, useEffect, useState } from "react";
import {
  Megaphone, Plus, Play, Pause, Square, Loader2, Users, CheckCircle2, AlertTriangle,
} from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { format } from "date-fns";
import { toast } from "sonner";

const STATUS_STYLE = {
  draft: "bg-surface-3 text-graphite",
  running: "bg-success/15 text-success",
  paused: "bg-warning/15 text-warning",
  stopped: "bg-danger/15 text-danger",
  completed: "bg-info/15 text-info",
};

export default function SDRCampaigns() {
  const [campaigns, setCampaigns] = useState(null);
  const [defaultSteps, setDefaultSteps] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [launchTarget, setLaunchTarget] = useState(null);
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("");
  const [approvalMode, setApprovalMode] = useState("manual");
  const [steps, setSteps] = useState([]);

  const [leads, setLeads] = useState(null);
  const [pickedLeads, setPickedLeads] = useState({});

  const load = useCallback(async () => {
    const [list, seq] = await Promise.all([
      api.get("/sdr/campaigns?limit=100"),
      api.get("/sdr/config/sequence-default"),
    ]);
    setCampaigns(list.data.items);
    setDefaultSteps(seq.data.steps);
  }, []);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setName("");
    setApprovalMode("manual");
    setSteps((defaultSteps || []).map((step) => ({ ...step })));
    setCreateOpen(true);
  };

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/sdr/campaigns", {
        name,
        approval_mode: approvalMode,
        sequence: steps.map((step, index) => ({
          delay_days: index === 0 ? 0 : parseInt(step.delay_days, 10) || 1,
          goal: step.goal,
          instruction: step.instruction,
        })),
      });
      toast.success("Campaign created — launch it when you've picked its leads");
      setCreateOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const openLaunch = async (campaign) => {
    setLaunchTarget(campaign);
    setLeads(null);
    setPickedLeads({});
    // Qualified, SDR-managed leads are the sensible launch pool.
    const { data } = await api.get("/sdr/leads?qualification_status=qualified&limit=200");
    setLeads(data.items);
  };

  const launch = async () => {
    const lead_ids = Object.keys(pickedLeads).filter((id) => pickedLeads[id]);
    if (!lead_ids.length) {
      toast.error("Pick at least one lead");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post(`/sdr/campaigns/${launchTarget.id}/launch`, { lead_ids });
      const fit = data.quota_fit;
      if (fit && !fit.fits) {
        toast.warning(fit.warnings?.[0] || "Launched, but this exceeds the email plan");
      } else {
        toast.success(
          `Launched — ${data.enrollment.enrolled} enrolled` +
          (data.enrollment.skipped.length ? `, ${data.enrollment.skipped.length} skipped` : "")
        );
      }
      if (data.enrollment.skipped.length) {
        // Every skip has a reason; surface the first few rather than hiding them.
        data.enrollment.skipped.slice(0, 3).forEach((row) =>
          toast.info(`Skipped: ${row.reason}`)
        );
      }
      setLaunchTarget(null);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (campaign, status) => {
    setBusy(true);
    try {
      await api.post(`/sdr/campaigns/${campaign.id}/status`, { status });
      toast.success(`Campaign ${status}`);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  if (!campaigns) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6 space-y-5" data-testid="sdr-campaigns-page">
      <PageHeader
        title="Campaigns"
        description="A sequence pointed at a set of qualified leads — drafted by AI, gated by you"
        actions={
          <Button size="sm" data-testid="sdr-new-campaign-btn" className="gap-1.5" onClick={openCreate}>
            <Plus className="h-3.5 w-3.5" /> New campaign
          </Button>
        }
      />

      {campaigns.length === 0 ? (
        <EmptyState
          icon={Megaphone}
          title="No campaigns yet"
          description="Create one, pick its qualified leads, and the agents draft every email for your approval."
          testId="sdr-campaigns-empty"
        />
      ) : (
        <div className="space-y-2" data-testid="sdr-campaigns-list">
          {campaigns.map((campaign) => (
            <Card
              key={campaign.id}
              className="p-4 bg-surface-1 border-white/10"
              data-testid={`sdr-campaign-${campaign.id}`}
            >
              <div className="flex flex-wrap items-center gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="font-medium truncate">{campaign.name}</p>
                    <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${STATUS_STYLE[campaign.status] || "bg-surface-2 text-ash"}`}>
                      {campaign.status}
                    </span>
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded uppercase bg-surface-2 text-graphite">
                      {campaign.approval_mode === "auto" ? "auto-send" : "human approval"}
                    </span>
                  </div>
                  <p className="text-[11px] text-carbon font-mono mt-1">
                    {campaign.sequence?.length || 0} touches · {campaign.enrolled_count} enrolled
                    · sent {campaign.stats?.sent ?? 0}
                    · delivered {campaign.stats?.delivered ?? 0}
                    · bounced {campaign.stats?.bounced ?? 0}
                    {campaign.created_at && ` · ${format(new Date(campaign.created_at), "MMM d")}`}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {campaign.status === "draft" && (
                    <Button size="sm" data-testid={`sdr-launch-${campaign.id}`}
                            disabled={busy} className="gap-1.5 h-8"
                            onClick={() => openLaunch(campaign)}>
                      <Play className="h-3.5 w-3.5" /> Launch
                    </Button>
                  )}
                  {campaign.status === "running" && (
                    <Button size="sm" variant="outline" disabled={busy}
                            className="border-white/10 gap-1.5 h-8"
                            data-testid={`sdr-pause-${campaign.id}`}
                            onClick={() => setStatus(campaign, "paused")}>
                      <Pause className="h-3.5 w-3.5" /> Pause
                    </Button>
                  )}
                  {campaign.status === "paused" && (
                    <Button size="sm" variant="outline" disabled={busy}
                            className="border-success/40 text-success hover:text-success gap-1.5 h-8"
                            onClick={() => setStatus(campaign, "running")}>
                      <Play className="h-3.5 w-3.5" /> Resume
                    </Button>
                  )}
                  {["running", "paused"].includes(campaign.status) && (
                    <Button size="sm" variant="outline" disabled={busy}
                            className="border-danger/40 text-danger hover:text-danger gap-1.5 h-8"
                            data-testid={`sdr-stop-${campaign.id}`}
                            onClick={() => setStatus(campaign, "stopped")}>
                      <Square className="h-3.5 w-3.5" /> Stop
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="bg-surface-1 border-white/10 max-w-2xl max-h-[85vh] overflow-y-auto scrollbar-thin" data-testid="sdr-create-campaign-dialog">
          <DialogHeader><DialogTitle>New campaign</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-4">
            <div className="grid grid-cols-[1fr_180px] gap-3">
              <div className="space-y-1">
                <Label>Name *</Label>
                <Input required data-testid="sdr-campaign-name" value={name}
                       onChange={(e) => setName(e.target.value)}
                       placeholder="e.g. Pune dental clinics — July"
                       className="bg-surface-2 border-white/10" />
              </div>
              <div className="space-y-1">
                <Label>Sending</Label>
                <Select value={approvalMode} onValueChange={setApprovalMode}>
                  <SelectTrigger className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">I approve each email</SelectItem>
                    <SelectItem value="auto">Send automatically</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-3">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
                Sequence — each step is an instruction to the writer, not a template
              </p>
              {steps.map((step, index) => (
                <div key={index} className="rounded-lg border border-white/10 bg-surface-2 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-ash">
                      Step {index + 1}{index === 0 ? " — first touch" : ""}
                    </span>
                    {index > 0 && (
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] text-graphite">after</span>
                        <Input type="number" min="1" max="30"
                               value={step.delay_days}
                               onChange={(e) => {
                                 const next = [...steps];
                                 next[index] = { ...step, delay_days: e.target.value };
                                 setSteps(next);
                               }}
                               className="w-16 h-7 bg-surface-3 border-white/10 text-center" />
                        <span className="text-[11px] text-graphite">days</span>
                      </div>
                    )}
                  </div>
                  <Textarea
                    value={step.instruction}
                    onChange={(e) => {
                      const next = [...steps];
                      next[index] = { ...step, instruction: e.target.value };
                      setSteps(next);
                    }}
                    rows={3}
                    className="bg-surface-3 border-white/10 text-sm"
                  />
                </div>
              ))}
              <p className="text-[11px] text-carbon">
                {steps.length} touches per lead. The quota planner on the Deliverability page
                assumes this number — keep them matching or the 30-leads/day figure drifts.
              </p>
            </div>

            <DialogFooter>
              <Button type="submit" disabled={busy} className="gap-1.5">
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                Create as draft
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Launch: pick leads */}
      <Dialog open={!!launchTarget} onOpenChange={(open) => !open && setLaunchTarget(null)}>
        <DialogContent className="bg-surface-1 border-white/10 max-w-xl max-h-[85vh] overflow-y-auto scrollbar-thin" data-testid="sdr-launch-dialog">
          <DialogHeader><DialogTitle>Launch “{launchTarget?.name}”</DialogTitle></DialogHeader>
          {!leads ? (
            <Skeleton className="h-40 bg-surface-2" />
          ) : leads.length === 0 ? (
            <div className="rounded-lg border border-warning/20 bg-warning/10 p-3">
              <p className="text-sm text-warning flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" /> No qualified leads to enroll
              </p>
              <p className="text-xs text-graphite mt-1">
                Process leads in the Lead Database first — only qualified leads with an
                email address can enter a sequence.
              </p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <p className="text-xs text-graphite flex items-center gap-1.5">
                  <Users className="h-3.5 w-3.5" /> {leads.length} qualified lead{leads.length === 1 ? "" : "s"}
                </p>
                <button
                  type="button"
                  className="text-xs text-info hover:underline"
                  data-testid="sdr-launch-select-all"
                  onClick={() => setPickedLeads(Object.fromEntries(leads.map((l) => [l.id, true])))}
                >
                  Select all
                </button>
              </div>
              <div className="space-y-1.5 max-h-72 overflow-y-auto scrollbar-thin">
                {leads.map((lead) => (
                  <label key={lead.id}
                         className="flex items-center gap-3 rounded-lg border border-white/10 bg-surface-2 px-3 py-2 cursor-pointer"
                         data-testid={`sdr-launch-lead-${lead.id}`}>
                    <Checkbox
                      checked={!!pickedLeads[lead.id]}
                      onCheckedChange={(checked) =>
                        setPickedLeads({ ...pickedLeads, [lead.id]: !!checked })}
                    />
                    <span className="text-sm truncate flex-1">{lead.company}</span>
                    <span className="font-mono text-[11px] text-carbon truncate">{lead.email}</span>
                    <span className="font-mono text-xs text-ash">{lead.score}</span>
                  </label>
                ))}
              </div>
              <p className="text-[11px] text-carbon">
                Suppressed, already-sequenced and recently-contacted leads are skipped
                automatically, each with a stated reason.
              </p>
              <DialogFooter>
                <Button disabled={busy} onClick={launch} data-testid="sdr-launch-confirm" className="gap-1.5">
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                  Enroll & start
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

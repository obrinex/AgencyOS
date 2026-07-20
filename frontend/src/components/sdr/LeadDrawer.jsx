import { useEffect, useState } from "react";
import { Globe, Mail, Phone, MapPin, Star, Loader2, ExternalLink, Wand2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SDR_STAGE_CONFIG, QUALIFICATION_CONFIG, scoreColor } from "@/lib/sdrConfig";
import { format } from "date-fns";
import { toast } from "sonner";

function Field({ icon: Icon, label, value, href }) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-2.5">
      <Icon className="h-3.5 w-3.5 text-carbon mt-0.5 shrink-0" />
      <div className="min-w-0">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">{label}</p>
        {href ? (
          <a href={href} target="_blank" rel="noreferrer" className="text-sm text-info hover:underline break-all">
            {value}
          </a>
        ) : (
          <p className="text-sm break-words">{value}</p>
        )}
      </div>
    </div>
  );
}

export default function LeadDrawer({ leadId, open, onOpenChange, onChanged }) {
  const [data, setData] = useState(null);
  const [audit, setAudit] = useState(null);
  const [transitions, setTransitions] = useState({});
  const [saving, setSaving] = useState(false);
  const [processing, setProcessing] = useState(false);

  const load = async () => {
    if (!leadId) return;
    const [detail, config] = await Promise.all([
      api.get(`/sdr/leads/${leadId}`),
      api.get("/sdr/config/pipeline"),
    ]);
    setData(detail.data);
    setTransitions(config.data.transitions || {});

    // Audit, signals and ROI live on the company, so this is a second call.
    // Deliberately not blocking the drawer: the lead is useful without it.
    const companyId = detail.data?.lead?.sdr_company_id;
    if (companyId) {
      try {
        const { data: research } = await api.get(`/sdr/companies/${companyId}/audit`);
        setAudit(research);
      } catch {
        setAudit(null);
      }
    } else {
      setAudit(null);
    }
  };

  const processLead = async () => {
    setProcessing(true);
    try {
      const { data: result } = await api.post(`/sdr/leads/${leadId}/process`);
      const failed = result.steps.filter((s) => s.status === "failed");
      if (failed.length) {
        toast.warning(
          `Scored ${result.score} — ${failed.length} step(s) failed: ${failed.map((s) => s.agent).join(", ")}`
        );
      } else {
        toast.success(`Scored ${result.score} · ${result.qualification_status}`);
      }
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setProcessing(false);
    }
  };

  useEffect(() => {
    setData(null);
    setAudit(null);
    if (open && leadId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, leadId]);

  const moveStage = async (stage) => {
    setSaving(true);
    try {
      await api.patch(`/sdr/leads/${leadId}/stage`, { stage });
      toast.success(`Moved to ${SDR_STAGE_CONFIG[stage]?.label || stage}`);
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const lead = data?.lead;
  const company = data?.company;
  const currentStage = lead?.stage;

  // Only stages the state machine allows from here. The server re-validates
  // regardless — this is UX, not enforcement.
  const allowed = currentStage ? transitions[currentStage] || [] : [];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="bg-surface-1 border-white/10 w-full sm:max-w-md overflow-y-auto scrollbar-thin" data-testid="sdr-lead-drawer">
        {!data ? (
          <div className="space-y-3 pt-6">
            <Skeleton className="h-8 bg-surface-2" />
            <Skeleton className="h-32 bg-surface-2" />
          </div>
        ) : (
          <>
            <SheetHeader>
              <SheetTitle className="pr-8 text-left">{lead.company}</SheetTitle>
            </SheetHeader>

            <div className="mt-5 space-y-5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[9px] px-1.5 py-0.5 rounded uppercase bg-surface-2 text-ash">
                  {SDR_STAGE_CONFIG[currentStage]?.label || currentStage}
                </span>
                {lead.qualification_status && (
                  <span className="font-mono text-[9px] px-1.5 py-0.5 rounded uppercase bg-surface-2 text-ash">
                    {QUALIFICATION_CONFIG[lead.qualification_status]?.label || lead.qualification_status}
                  </span>
                )}
                <span className={`font-mono text-sm font-semibold ${scoreColor(lead.score || 0)}`}>
                  {lead.score || 0}
                </span>
              </div>

              {allowed.length > 0 && (
                <div className="space-y-1">
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">Move to stage</p>
                  <Select value="" onValueChange={moveStage} disabled={saving}>
                    <SelectTrigger data-testid="sdr-drawer-stage" className="bg-surface-2 border-white/10">
                      <SelectValue placeholder={saving ? "Moving…" : "Pick a stage"} />
                    </SelectTrigger>
                    <SelectContent>
                      {allowed.map((s) => (
                        <SelectItem key={s} value={s}>{SDR_STAGE_CONFIG[s]?.label || s}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              <div className="space-y-3 rounded-lg border border-white/10 bg-surface-2 p-3">
                <Field icon={Globe} label="Website" value={lead.website} href={lead.website} />
                <Field icon={Mail} label="Email" value={lead.email} href={lead.email ? `mailto:${lead.email}` : null} />
                <Field icon={Phone} label="Phone" value={lead.phone} href={lead.phone ? `tel:${lead.phone}` : null} />
                <Field icon={MapPin} label="Location" value={lead.location} />
                {company?.google_rating && (
                  <Field
                    icon={Star}
                    label="Google rating"
                    value={`${company.google_rating} (${company.google_review_count || 0} reviews)`}
                  />
                )}
              </div>

              {lead.score_breakdown && (
                <div className="space-y-2" data-testid="sdr-drawer-score">
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
                    Why this score
                  </p>
                  {Object.entries(lead.score_breakdown).map(([key, part]) => (
                    <div key={key} className="rounded-lg border border-white/10 bg-surface-2 px-3 py-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm capitalize">{key.replace(/_/g, " ")}</span>
                        <span className="font-mono text-xs text-ash">
                          {part.points} / {Math.round(part.weight * 100)}
                        </span>
                      </div>
                      {part.reasons?.map((reason, i) => (
                        <p key={i} className="text-xs text-graphite mt-0.5">{reason}</p>
                      ))}
                    </div>
                  ))}
                </div>
              )}

              {audit?.signals?.length > 0 && (
                <div className="space-y-2" data-testid="sdr-drawer-signals">
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
                    Detected gaps
                  </p>
                  {audit.signals.map((signal) => (
                    <div
                      key={signal.signal_key}
                      className="rounded-lg border border-white/10 bg-surface-2 px-3 py-2"
                      data-testid={`sdr-drawer-signal-${signal.signal_key}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm">{signal.label}</span>
                        <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase shrink-0 ${
                          signal.severity === "critical" ? "bg-danger/15 text-danger"
                            : signal.severity === "high" ? "bg-warning/15 text-warning"
                            : signal.severity === "medium" ? "bg-info/15 text-info"
                            : "bg-surface-3 text-graphite"
                        }`}>
                          {signal.severity}
                        </span>
                      </div>
                      <p className="text-xs text-graphite mt-0.5">{signal.description}</p>
                      {signal.confidence != null && (
                        <p className="text-[11px] text-carbon font-mono mt-1">
                          {Math.round(signal.confidence * 100)}% of expected evidence captured
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {audit?.opportunity && (
                <div
                  className="rounded-lg border border-white/10 bg-surface-2 px-3 py-2.5"
                  data-testid="sdr-drawer-roi"
                >
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
                    Opportunity (estimate)
                  </p>
                  <p className="font-display text-lg font-semibold tracking-tight mt-1">
                    {audit.opportunity.currency} {Math.round(audit.opportunity.monthly_opportunity_value).toLocaleString()}
                    <span className="text-xs text-graphite font-sans font-normal"> / month</span>
                  </p>
                  {/* Every AI-derived number has to show its working - the
                      proposal has to be defensible if a prospect pushes back. */}
                  <details className="mt-2">
                    <summary className="text-xs text-info cursor-pointer select-none">
                      What this assumes
                    </summary>
                    <div className="mt-1.5 space-y-0.5 text-[11px] text-graphite font-mono">
                      <p>{audit.opportunity.assumptions.monthly_leads.basis}</p>
                      <p>
                        capture {Math.round(audit.opportunity.current_capture_rate * 100)}% →{" "}
                        {Math.round(audit.opportunity.improved_capture_rate * 100)}%
                      </p>
                      <p>
                        avg deal {audit.opportunity.currency}{" "}
                        {audit.opportunity.assumptions.avg_deal_value} · close{" "}
                        {Math.round(audit.opportunity.assumptions.close_rate * 100)}%
                      </p>
                      <p>benchmarks {audit.opportunity.assumptions.benchmark_version}</p>
                      <p className="text-carbon">
                        {audit.opportunity.assumptions.uplift_method}
                      </p>
                    </div>
                  </details>
                </div>
              )}

              {company?.pitch_angle && (
                <div className="space-y-1" data-testid="sdr-drawer-pitch">
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
                    Pitch angle
                  </p>
                  <p className="text-sm text-ash">{company.pitch_angle}</p>
                  {company.research_summary && (
                    <p className="text-xs text-graphite mt-1">{company.research_summary}</p>
                  )}
                </div>
              )}

              {company && (
                <div className="space-y-1">
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">Source</p>
                  <p className="text-xs text-graphite">
                    {company.discovery_source || "unknown"}
                    {company.data_quality_score != null &&
                      ` · ${Math.round(company.data_quality_score * 100)}% complete`}
                  </p>
                </div>
              )}

              <Button
                size="sm"
                data-testid="sdr-drawer-process"
                disabled={processing}
                className="w-full gap-1.5"
                onClick={processLead}
              >
                {processing
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <Wand2 className="h-3.5 w-3.5" />}
                {lead.score ? "Re-run research" : "Enrich, audit & score"}
              </Button>

              <div className="space-y-2">
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">Timeline</p>
                {data.activities.length === 0 ? (
                  <p className="text-xs text-graphite">Nothing recorded yet.</p>
                ) : (
                  data.activities.map((a) => (
                    <div key={a.id} className="rounded-lg border border-white/10 bg-surface-2 px-3 py-2">
                      <p className="text-sm">{a.content}</p>
                      <p className="text-[11px] text-carbon font-mono mt-0.5">
                        {a.created_at ? format(new Date(a.created_at), "MMM d, HH:mm") : ""}
                      </p>
                    </div>
                  ))
                )}
              </div>

              <Button
                asChild
                variant="outline"
                size="sm"
                className="border-white/10 gap-1.5 w-full"
                data-testid="sdr-drawer-open-crm"
              >
                <a href={`/crm/${lead.id}`}>
                  <ExternalLink className="h-3.5 w-3.5" /> Open in CRM
                </a>
              </Button>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

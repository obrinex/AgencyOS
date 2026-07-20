import { useCallback, useEffect, useState } from "react";
import { ScanSearch, AlertTriangle, ExternalLink, Info, ShieldCheck } from "lucide-react";
import api from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { format } from "date-fns";

const SEVERITY_STYLE = {
  critical: "bg-danger/15 text-danger",
  high: "bg-warning/15 text-warning",
  medium: "bg-info/15 text-info",
  low: "bg-surface-3 text-graphite",
};

const AUDIT_STATUS_STYLE = {
  completed: "bg-success/15 text-success",
  failed: "bg-danger/15 text-danger",
  skipped: "bg-surface-3 text-graphite",
};

function FactRow({ label, value }) {
  const display =
    value === true ? "Yes" : value === false ? "No" : value === null || value === undefined ? "—" : String(value);
  const tone = value === true ? "text-success" : value === false ? "text-danger" : "";
  return (
    <div className="flex items-center justify-between text-sm py-1">
      <span className="text-graphite">{label}</span>
      <span className={`font-mono ${tone}`}>{display}</span>
    </div>
  );
}

function AuditDrawer({ auditId, open, onOpenChange }) {
  const [audit, setAudit] = useState(null);

  useEffect(() => {
    setAudit(null);
    if (!open || !auditId) return;
    api.get(`/sdr/audits/${auditId}`).then(({ data }) => setAudit(data)).catch(() => {});
  }, [open, auditId]);

  const facts = audit?.facts || {};

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="bg-surface-1 border-white/10 w-full sm:max-w-lg overflow-y-auto scrollbar-thin"
        data-testid="sdr-audit-drawer"
      >
        {!audit ? (
          <div className="pt-6"><Skeleton className="h-40 bg-surface-2" /></div>
        ) : (
          <>
            <SheetHeader>
              <SheetTitle className="pr-8 text-left break-all">{audit.url || "Audit"}</SheetTitle>
            </SheetHeader>
            <div className="mt-5 space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${AUDIT_STATUS_STYLE[audit.status] || "bg-surface-2 text-ash"}`}>
                  {audit.status}
                </span>
                <span className="font-mono text-[10px] text-carbon">{audit.audit_version}</span>
                <span className="font-mono text-[10px] text-carbon">
                  {format(new Date(audit.audited_at), "MMM d, HH:mm")}
                </span>
              </div>

              {audit.error && (
                <div className="rounded-lg border border-danger/20 bg-danger/10 p-3">
                  <p className="text-sm text-danger break-words">{audit.error}</p>
                </div>
              )}

              {audit.status === "completed" && (
                <>
                  <div className="rounded-lg border border-white/10 bg-surface-2 p-3">
                    <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon mb-2">
                      Measured
                    </p>
                    <FactRow label="HTTPS valid" value={facts.ssl_valid} />
                    <FactRow label="Mobile viewport" value={facts.mobile_friendly} />
                    <FactRow label="Response time" value={facts.load_time_ms ? `${facts.load_time_ms} ms` : null} />
                    <FactRow label="SEO structure" value={facts.seo_score_basic != null ? `${facts.seo_score_basic}/100` : null} />
                    <FactRow label="Contact form" value={facts.contact_form_present} />
                    <FactRow label="Chat widget" value={facts.chat_vendor || facts.has_chat_widget} />
                    <FactRow label="Booking system" value={facts.booking_vendor || facts.has_booking_system} />
                    <FactRow label="CRM pixel" value={facts.crm_vendor || facts.has_crm_pixel} />
                    <FactRow label="Analytics" value={(facts.analytics_vendors || []).join(", ") || facts.has_analytics} />
                    <FactRow label="WhatsApp link" value={facts.whatsapp_link_present} />
                    <FactRow label="Click-to-call" value={facts.phone_click_to_call} />
                    <FactRow label="Structured data" value={facts.schema_org_present} />
                  </div>

                  {facts.tech_stack?.length > 0 && (
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon mb-1.5">
                        Detected stack
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {facts.tech_stack.map((tech) => (
                          <span key={tech} className="font-mono text-[10px] px-2 py-0.5 rounded bg-surface-2 text-ash border border-white/10">
                            {tech}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {facts.seo_issues?.length > 0 && (
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon mb-1.5">
                        SEO issues
                      </p>
                      <ul className="space-y-0.5">
                        {facts.seo_issues.map((issue) => (
                          <li key={issue} className="text-xs text-warning">
                            {issue.replace(/_/g, " ")}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}

              {audit.unmeasured?.length > 0 && (
                <div className="rounded-lg border border-white/10 bg-surface-2 p-3">
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon mb-1.5 flex items-center gap-1.5">
                    <Info className="h-3 w-3" /> Not checked
                  </p>
                  <p className="text-xs text-graphite mb-2">
                    This audit runs over HTTP, not a real browser, so these were not measured.
                    Their absence here is not a pass.
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {audit.unmeasured.map((item) => (
                      <span key={item} className="font-mono text-[10px] px-2 py-0.5 rounded bg-surface-3 text-carbon">
                        {item.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

export default function SDRAudits() {
  const [audits, setAudits] = useState(null);
  const [summary, setSummary] = useState(null);
  const [drawerId, setDrawerId] = useState(null);

  const load = useCallback(async () => {
    const [list, sum] = await Promise.all([
      api.get("/sdr/audits?limit=50"),
      api.get("/sdr/audits/summary"),
    ]);
    setAudits(list.data.items);
    setSummary(sum.data);
  }, []);

  useEffect(() => { load(); }, [load]);

  if (!audits || !summary) {
    return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;
  }

  const topSignals = (summary.signal_counts || []).slice(0, 8);
  const maxCount = topSignals[0]?.count || 1;

  return (
    <div className="p-6 space-y-5" data-testid="sdr-audits-page">
      <PageHeader
        title="Website Audits"
        description="What each prospect's site is missing, and which gaps are most common"
      />

      {audits.length === 0 ? (
        <EmptyState
          icon={ScanSearch}
          title="No audits yet"
          description="Process a lead from the Lead Database and its site will be audited automatically."
          testId="sdr-audits-empty"
        />
      ) : (
        <>
          {topSignals.length > 0 && (
            <Card className="p-5 bg-surface-1 border-white/10" data-testid="sdr-signal-summary">
              <p className="font-display text-sm font-semibold mb-1">Most common gaps</p>
              <p className="text-xs text-graphite mb-4">
                Across every audited prospect — useful for deciding which offer to lead with.
              </p>
              <div className="space-y-2">
                {topSignals.map((signal) => (
                  <div key={signal.signal_key} className="flex items-center gap-3" data-testid={`sdr-signal-${signal.signal_key}`}>
                    <span className="w-48 shrink-0 text-xs text-graphite truncate">
                      {signal.label || signal.signal_key}
                    </span>
                    <div className="flex-1 h-2 rounded-full bg-surface-2 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${signal.severity === "critical" ? "bg-danger" : signal.severity === "high" ? "bg-warning" : "bg-info"}`}
                        style={{ width: `${(signal.count / maxCount) * 100}%` }}
                      />
                    </div>
                    <span className="w-10 shrink-0 text-right font-mono text-sm">{signal.count}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card className="p-4 bg-surface-1 border-white/10" data-testid="sdr-audit-scope">
            <p className="text-sm text-ash flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-carbon" /> What these audits cover
            </p>
            <p className="text-xs text-graphite mt-1">
              Audits run over HTTP, not a headless browser, so Core Web Vitals, Lighthouse scores
              and form submission are not measured. Gaps that cannot be measured are never
              claimed — an audit finding nothing on those is silence, not a pass.
            </p>
          </Card>

          <div className="space-y-2" data-testid="sdr-audits-list">
            {audits.map((audit) => (
              <button
                key={audit.id}
                data-testid={`sdr-audit-${audit.id}`}
                onClick={() => setDrawerId(audit.id)}
                className="w-full flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-surface-1 px-4 py-3 text-left hover:border-white/25"
              >
                <span className="font-mono text-sm truncate flex-1 min-w-0">
                  {audit.url || "—"}
                </span>
                {audit.status === "completed" && (
                  <>
                    <span className="font-mono text-[11px] text-carbon hidden sm:block">
                      {audit.facts?.load_time_ms}ms
                    </span>
                    <span className="font-mono text-[11px] text-carbon hidden sm:block">
                      SEO {audit.facts?.seo_score_basic}/100
                    </span>
                  </>
                )}
                <span className="font-mono text-[11px] text-carbon">
                  {format(new Date(audit.audited_at), "MMM d")}
                </span>
                <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${AUDIT_STATUS_STYLE[audit.status] || "bg-surface-2 text-ash"}`}>
                  {audit.status}
                </span>
                <ExternalLink className="h-3.5 w-3.5 text-carbon shrink-0" />
              </button>
            ))}
          </div>
        </>
      )}

      <AuditDrawer
        auditId={drawerId}
        open={!!drawerId}
        onOpenChange={(o) => !o && setDrawerId(null)}
      />
    </div>
  );
}

export { SEVERITY_STYLE };

import { useCallback, useEffect, useState } from "react";
import {
  Mail, ShieldCheck, ShieldAlert, Plus, Play, Pause, RefreshCw, Loader2, Info,
} from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const STATUS_STYLE = {
  healthy: "bg-success/15 text-success",
  warming: "bg-info/15 text-info",
  throttled: "bg-warning/15 text-warning",
  paused: "bg-surface-3 text-graphite",
  blocked: "bg-danger/15 text-danger",
};

const DNS_STYLE = {
  pass: "text-success",
  warn: "text-warning",
  fail: "text-danger",
  unknown: "text-carbon",
};

const emptyForm = { identity: "", label: "", dkim_selector: "", daily_cap_target: "200" };

function DnsRow({ name, check }) {
  if (!check) return null;
  return (
    <div className="flex items-start justify-between gap-3 py-1">
      <span className="font-mono text-[11px] uppercase tracking-wider text-carbon w-14 shrink-0">
        {name}
      </span>
      <span className={`text-xs flex-1 ${DNS_STYLE[check.status] || "text-graphite"}`}>
        {check.detail}
      </span>
      <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase shrink-0 ${
        check.status === "pass" ? "bg-success/15 text-success"
          : check.status === "fail" ? "bg-danger/15 text-danger"
          : check.status === "warn" ? "bg-warning/15 text-warning"
          : "bg-surface-3 text-carbon"
      }`}>
        {check.status}
      </span>
    </div>
  );
}

export default function IdentitiesPanel() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [identities, setIdentities] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    const { data } = await api.get("/sdr/identities");
    setIdentities(data.identities);
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async (e) => {
    e.preventDefault();
    setBusy("create");
    try {
      await api.post("/sdr/identities", {
        identity: form.identity,
        label: form.label || null,
        dkim_selector: form.dkim_selector || null,
        daily_cap_target: parseInt(form.daily_cap_target, 10) || 200,
      });
      toast.success("Identity added — verify DNS before activating");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(null);
    }
  };

  const verifyDns = async (id) => {
    setBusy(id);
    try {
      const { data } = await api.post(`/sdr/identities/${id}/verify-dns`);
      if (data.ready_to_send) {
        toast.success("DNS verified — this domain can send");
      } else {
        toast.warning(data.reason);
      }
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(null);
    }
  };

  const activate = async (id) => {
    setBusy(id);
    try {
      await api.post(`/sdr/identities/${id}/activate`);
      toast.success("Warm-up started — volume ramps over about three weeks");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(null);
    }
  };

  const pause = async (id) => {
    setBusy(id);
    try {
      await api.post(`/sdr/identities/${id}/pause`, { reason: "Paused from the dashboard" });
      toast.success("Sending paused for this identity");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(null);
    }
  };

  if (!identities) return <Skeleton className="h-48 bg-surface-1" />;

  return (
    <div className="space-y-4" data-testid="sdr-identities-panel">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-graphite">
          A domain cannot send until SPF, DKIM and DMARC all pass. That is deliberate —
          sending without them lands in spam, and the reputation damage outlasts the campaign.
        </p>
        {isAdmin && (
          <Button
            size="sm"
            data-testid="sdr-add-identity-btn"
            className="gap-1.5 shrink-0"
            onClick={() => setOpen(true)}
          >
            <Plus className="h-3.5 w-3.5" /> Add identity
          </Button>
        )}
      </div>

      {identities.length === 0 ? (
        <EmptyState
          icon={Mail}
          title="No sending identities"
          description="Add the address outreach will be sent from, then verify its DNS records."
          testId="sdr-identities-empty"
        />
      ) : (
        <div className="space-y-3">
          {identities.map((identity) => {
            const dns = identity.dns_status;
            const canSend = dns && !(dns.blocking || []).length
              && dns.checks?.dkim?.status === "pass"
              && dns.checks?.dmarc?.status !== "fail";
            const rampPercent = identity.daily_cap_target
              ? Math.round((identity.daily_cap_current / identity.daily_cap_target) * 100)
              : 0;

            return (
              <Card
                key={identity.id}
                className="p-4 bg-surface-1 border-white/10 space-y-3"
                data-testid={`sdr-identity-${identity.id}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium flex items-center gap-2">
                      <Mail className="h-3.5 w-3.5 text-carbon" />
                      {identity.identity}
                    </p>
                    <p className="text-[11px] text-carbon font-mono mt-1">
                      {identity.channel} · target {identity.daily_cap_target}/day
                      {identity.dkim_selector && ` · selector ${identity.dkim_selector}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${STATUS_STYLE[identity.status] || "bg-surface-2 text-ash"}`}>
                      {identity.status}
                    </span>
                    {canSend
                      ? <ShieldCheck className="h-4 w-4 text-success" />
                      : <ShieldAlert className="h-4 w-4 text-warning" />}
                  </div>
                </div>

                {identity.status_reason && (
                  <p className="text-xs text-graphite">{identity.status_reason}</p>
                )}

                <div className="rounded-lg border border-white/10 bg-surface-2 p-3">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
                      Warm-up
                    </span>
                    <span className="font-mono text-xs">
                      {identity.daily_cap_current} / {identity.daily_cap_target} per day
                    </span>
                  </div>
                  <Progress value={rampPercent} className="h-1.5 bg-surface-3" />
                  <p className="text-[11px] text-carbon font-mono mt-1.5">
                    {identity.is_warmed
                      ? "Fully warmed"
                      : `Day ${identity.warmup_day + 1} — volume ramps over about three weeks`}
                    {" · reputation "}{Math.round((identity.reputation_score ?? 1) * 100)}%
                  </p>
                </div>

                {dns ? (
                  <div className="rounded-lg border border-white/10 bg-surface-2 p-3">
                    <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon mb-1">
                      DNS
                    </p>
                    <DnsRow name="MX" check={dns.checks?.mx} />
                    <DnsRow name="SPF" check={dns.checks?.spf} />
                    <DnsRow name="DKIM" check={dns.checks?.dkim} />
                    <DnsRow name="DMARC" check={dns.checks?.dmarc} />
                  </div>
                ) : (
                  <div className="rounded-lg border border-white/10 bg-surface-2 p-3 flex items-start gap-2">
                    <Info className="h-3.5 w-3.5 text-carbon mt-0.5 shrink-0" />
                    <p className="text-xs text-graphite">
                      DNS has not been checked yet. Run a check before activating.
                    </p>
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    data-testid={`sdr-verify-dns-${identity.id}`}
                    disabled={busy === identity.id}
                    className="border-white/10 gap-1.5 h-8"
                    onClick={() => verifyDns(identity.id)}
                  >
                    {busy === identity.id
                      ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      : <RefreshCw className="h-3.5 w-3.5" />}
                    Check DNS
                  </Button>
                  {isAdmin && (identity.status === "paused" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      data-testid={`sdr-activate-${identity.id}`}
                      disabled={busy === identity.id}
                      className="border-success/40 text-success hover:text-success gap-1.5 h-8"
                      onClick={() => activate(identity.id)}
                    >
                      <Play className="h-3.5 w-3.5" /> Start warm-up
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      data-testid={`sdr-pause-${identity.id}`}
                      disabled={busy === identity.id}
                      className="border-white/10 gap-1.5 h-8"
                      onClick={() => pause(identity.id)}
                    >
                      <Pause className="h-3.5 w-3.5" /> Pause
                    </Button>
                  ))}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="sdr-add-identity-dialog">
          <DialogHeader><DialogTitle>Add a sending identity</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="space-y-1">
              <Label>From address *</Label>
              <Input
                required
                data-testid="sdr-identity-address"
                type="email"
                value={form.identity}
                onChange={(e) => setForm({ ...form, identity: e.target.value })}
                placeholder="hello@yourdomain.com"
                className="bg-surface-2 border-white/10"
              />
            </div>
            <div className="space-y-1">
              <Label>DKIM selector</Label>
              <Input
                data-testid="sdr-identity-selector"
                value={form.dkim_selector}
                onChange={(e) => setForm({ ...form, dkim_selector: e.target.value })}
                placeholder="e.g. resend"
                className="bg-surface-2 border-white/10"
              />
              <p className="text-[11px] text-carbon">
                Your email provider gives you this when you verify the domain. Without it
                DKIM cannot be checked, and the identity cannot be activated.
              </p>
            </div>
            <div className="space-y-1">
              <Label>Target daily volume</Label>
              <Input
                data-testid="sdr-identity-cap"
                type="number"
                min="1"
                value={form.daily_cap_target}
                onChange={(e) => setForm({ ...form, daily_cap_target: e.target.value })}
                className="bg-surface-2 border-white/10"
              />
              <p className="text-[11px] text-carbon">
                Where warm-up ends up, not where it starts. Day one sends about five.
              </p>
            </div>
            <DialogFooter>
              <Button type="submit" disabled={busy === "create"} className="gap-1.5">
                {busy === "create"
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <Plus className="h-3.5 w-3.5" />}
                Add identity
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

import { useEffect, useState } from "react";
import { CheckCircle2, XCircle, Clock, Loader2, PlayCircle } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { format } from "date-fns";
import { toast } from "sonner";

const CHECK_LABELS = {
  kill_switch: "Kill switch",
  module_enabled: "Module enabled",
  channel_enabled: "Channel enabled",
  recipient_valid: "Valid recipient",
  suppression: "Not suppressed",
  compliance: "Lawful in their country",
  send_window: "Inside their business hours",
  identity: "Sending identity available",
  dns: "SPF, DKIM and DMARC",
  org_cap: "Org daily cap",
  rate_limit: "Rate limits",
};

export default function PreflightTester() {
  const [email, setEmail] = useState("");
  const [country, setCountry] = useState("IN");
  const [countries, setCountries] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/sdr/config/countries")
      .then(({ data }) => setCountries(data.countries || []))
      .catch(() => setCountries([]));
  }, []);

  const run = async (e) => {
    e.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      const { data } = await api.get(
        `/sdr/preflight/check?recipient_email=${encodeURIComponent(email)}` +
        `&country_code=${country}&channel=email`
      );
      setResult(data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="sdr-preflight-panel">
      <p className="text-xs text-graphite max-w-2xl">
        Run the exact gate a real send goes through, without sending anything. Every check
        and its verdict comes back, so “why did nothing send?” is answerable before a
        campaign launches rather than after it silently does nothing.
      </p>

      <Card className="p-4 bg-surface-1 border-white/10">
        <form onSubmit={run} className="flex flex-wrap items-end gap-3">
          <div className="space-y-1 flex-1 min-w-[220px]">
            <Label>Recipient email</Label>
            <Input
              required
              type="email"
              data-testid="sdr-preflight-email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="owner@prospect.com"
              className="bg-surface-2 border-white/10"
            />
          </div>
          <div className="space-y-1 w-[160px]">
            <Label>Their country</Label>
            <Select value={country} onValueChange={setCountry}>
              <SelectTrigger data-testid="sdr-preflight-country" className="bg-surface-2 border-white/10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {countries.map((entry) => (
                  <SelectItem key={entry.code} value={entry.code}>{entry.name}</SelectItem>
                ))}
                <SelectItem value="ZZ">Unlisted country</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" size="sm" disabled={busy} data-testid="sdr-preflight-run" className="gap-1.5">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlayCircle className="h-3.5 w-3.5" />}
            Run check
          </Button>
        </form>
      </Card>

      {result && (
        <Card
          className={`p-4 space-y-3 ${
            result.allowed
              ? "bg-success/10 border-success/20"
              : result.code === "outside_send_window"
                ? "bg-info/10 border-info/20"
                : "bg-danger/10 border-danger/20"
          }`}
          data-testid="sdr-preflight-result"
        >
          <div className="flex items-start gap-2">
            {result.allowed
              ? <CheckCircle2 className="h-4 w-4 text-success mt-0.5 shrink-0" />
              : result.code === "outside_send_window"
                ? <Clock className="h-4 w-4 text-info mt-0.5 shrink-0" />
                : <XCircle className="h-4 w-4 text-danger mt-0.5 shrink-0" />}
            <div className="min-w-0">
              <p className={`text-sm ${result.allowed ? "text-success" : result.code === "outside_send_window" ? "text-info" : "text-danger"}`}>
                {result.reason}
              </p>
              <p className="font-mono text-[11px] text-carbon mt-0.5">{result.code}</p>
              {result.identity && (
                <p className="text-xs text-graphite mt-1">
                  Would send as <span className="font-mono">{result.identity}</span>
                </p>
              )}
              {result.scheduled_for && !result.allowed && (
                <p className="text-xs text-graphite mt-1">
                  Would be scheduled for{" "}
                  {format(new Date(result.scheduled_for), "EEE d MMM, HH:mm")} their time.
                </p>
              )}
            </div>
          </div>

          <div className="space-y-1">
            {(result.checks || []).map((check) => (
              <div
                key={check.check}
                className="flex items-start justify-between gap-3 rounded border border-white/10 bg-surface-1/60 px-3 py-1.5"
                data-testid={`sdr-preflight-check-${check.check}`}
              >
                <span className="text-xs flex items-center gap-2 shrink-0">
                  {check.passed
                    ? <CheckCircle2 className="h-3 w-3 text-success" />
                    : <XCircle className="h-3 w-3 text-danger" />}
                  {CHECK_LABELS[check.check] || check.check}
                </span>
                <span className="text-[11px] text-graphite font-mono text-right break-words">
                  {check.detail}
                </span>
              </div>
            ))}
          </div>

          <p className="text-[11px] text-carbon">
            This was a dry run — no message was sent and no daily allowance was consumed.
          </p>
        </Card>
      )}
    </div>
  );
}

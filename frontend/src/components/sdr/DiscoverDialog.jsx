import { useEffect, useState } from "react";
import { Search, Loader2, AlertTriangle } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

const emptyForm = {
  niche: "",
  city: "",
  country_code: "IN",
  max_results: 25,
  create_leads: false,
};

function niceNiche(key) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function DiscoverDialog({ open, onOpenChange, onComplete }) {
  const [form, setForm] = useState(emptyForm);
  const [niches, setNiches] = useState([]);
  const [countries, setCountries] = useState([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!open) return;
    setResult(null);
    Promise.all([api.get("/sdr/providers"), api.get("/sdr/config/countries")])
      .then(([p, c]) => {
        setNiches(p.data.niches || []);
        setCountries(c.data.countries || []);
      })
      .catch(() => {});
  }, [open]);

  const run = async (e) => {
    e.preventDefault();
    setRunning(true);
    setResult(null);
    try {
      const { data } = await api.post("/sdr/discovery/run", {
        filters: {
          geo: { cities: [form.city], country_codes: [form.country_code] },
          industry: { categories: [form.niche] },
          limits: { max_results: Number(form.max_results) },
        },
        create_leads: form.create_leads,
      });
      setResult(data);
      const found = data.companies.inserted;
      toast.success(
        found > 0
          ? `Found ${found} new ${found === 1 ? "business" : "businesses"}`
          : "No new businesses — everything found was already in your database"
      );
      onComplete?.();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setRunning(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-surface-1 border-white/10 max-w-lg" data-testid="sdr-discover-dialog">
        <DialogHeader><DialogTitle>Discover businesses</DialogTitle></DialogHeader>

        <form onSubmit={run} className="space-y-3">
          <div className="space-y-1">
            <Label>Business type *</Label>
            <Select value={form.niche} onValueChange={(v) => setForm({ ...form, niche: v })}>
              <SelectTrigger data-testid="sdr-discover-niche" className="bg-surface-2 border-white/10">
                <SelectValue placeholder="Pick a niche" />
              </SelectTrigger>
              <SelectContent>
                {niches.map((n) => <SelectItem key={n} value={n}>{niceNiche(n)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-[1fr_140px] gap-3">
            <div className="space-y-1">
              <Label>City *</Label>
              <Input
                data-testid="sdr-discover-city"
                required
                value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })}
                placeholder="e.g. Pune"
                className="bg-surface-2 border-white/10"
              />
            </div>
            <div className="space-y-1">
              <Label>Country</Label>
              <Select value={form.country_code} onValueChange={(v) => setForm({ ...form, country_code: v })}>
                <SelectTrigger className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {countries.map((c) => <SelectItem key={c.code} value={c.code}>{c.code}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1">
            <Label>Maximum results</Label>
            <Input
              data-testid="sdr-discover-limit"
              type="number"
              min="1"
              max="200"
              value={form.max_results}
              onChange={(e) => setForm({ ...form, max_results: e.target.value })}
              className="bg-surface-2 border-white/10"
            />
          </div>

          <div className="flex items-start justify-between gap-4 rounded-lg border border-white/10 bg-surface-2 px-3 py-2.5">
            <div>
              <Label htmlFor="sdr-create-leads" className="cursor-pointer">Also create CRM leads</Label>
              <p className="text-xs text-graphite mt-0.5">
                Off by default. Discovering businesses is reversible; creating leads puts rows on the pipeline board.
              </p>
            </div>
            <Switch
              id="sdr-create-leads"
              data-testid="sdr-discover-create-leads"
              checked={form.create_leads}
              onCheckedChange={(v) => setForm({ ...form, create_leads: v })}
            />
          </div>

          {result && (
            <div className="rounded-lg border border-white/10 bg-surface-2 p-3 space-y-1.5" data-testid="sdr-discover-result">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">Run report</p>
              <p className="text-sm">
                {result.discovered} found · {result.companies.inserted} new ·{" "}
                {result.companies.merged} updated · {result.companies.deduped_in_batch} duplicates collapsed
              </p>
              {result.leads.created > 0 && (
                <p className="text-sm text-success">{result.leads.created} leads created</p>
              )}
              {Object.keys(result.filtered_out || {}).length > 0 && (
                <p className="text-xs text-graphite">
                  Filtered out: {Object.entries(result.filtered_out).map(([k, v]) => `${k} (${v})`).join(", ")}
                </p>
              )}
              {result.providers.map((p) => (
                <p key={p.provider} className="text-xs text-graphite">
                  {p.label}: {p.status === "ok" ? `${p.returned} results` : `failed — ${p.error}`}
                  {p.post_filters?.length > 0 && (
                    <span className="text-carbon"> · applied afterwards: {p.post_filters.join(", ")}</span>
                  )}
                </p>
              ))}
              {result.providers_rejected?.map((p) => (
                <p key={p.provider} className="text-xs text-carbon flex items-start gap-1.5">
                  <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" /> {p.label} not used — {p.reason}
                </p>
              ))}
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" className="border-white/10" onClick={() => onOpenChange(false)}>
              {result ? "Done" : "Cancel"}
            </Button>
            <Button
              type="submit"
              data-testid="sdr-discover-submit"
              disabled={running || !form.niche || !form.city}
              className="gap-1.5"
            >
              {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
              {running ? "Searching…" : "Search"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

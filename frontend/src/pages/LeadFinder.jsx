import { useState } from "react";
import { Sparkles, Search, Globe, Phone, Mail, MapPin, Plus, Loader2, Copy, ExternalLink } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";

const NICHE_LABELS = {
  cafe: "Cafes", restaurant: "Restaurants", dental_clinic: "Dental Clinics",
  medical_clinic: "Medical Clinics", doctor: "Doctors' Practices", pharmacy: "Pharmacies",
  salon: "Hair Salons", beauty: "Beauty Studios", gym: "Gyms & Fitness",
  hotel: "Hotels", real_estate: "Real Estate Agents", lawyer: "Law Firms",
  accountant: "Accounting Firms", veterinary: "Vet Clinics", car_repair: "Car Repair Shops",
};

export default function LeadFinder() {
  const [niche, setNiche] = useState("cafe");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState(null);
  const [place, setPlace] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(null);
  const [target, setTarget] = useState(null);
  const [importing, setImporting] = useState(false);
  const [imported, setImported] = useState({});

  const search = async (e) => {
    e.preventDefault();
    setSearching(true);
    setResults(null);
    try {
      const { data } = await api.post("/leadfinder/search", { niche, city, country: country || null, limit: 25 });
      setResults(data.businesses);
      setPlace(data.place);
      if (data.businesses.length === 0) toast.info("No businesses found there — try a bigger city or different niche");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSearching(false);
    }
  };

  const analyze = async (b) => {
    setAnalyzing(b.osm_id);
    setTarget(b);
    setAnalysis(null);
    try {
      const { data } = await api.post("/leadfinder/analyze", { business: b, niche });
      setAnalysis(data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      setTarget(null);
    } finally {
      setAnalyzing(null);
    }
  };

  const importLead = async () => {
    setImporting(true);
    try {
      await api.post("/leadfinder/import", { business: target, niche, analysis });
      toast.success(`${target.name} added to your pipeline with the AI pitch attached`);
      setImported({ ...imported, [target.osm_id]: true });
      setTarget(null);
      setAnalysis(null);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setImporting(false);
    }
  };

  const copy = (text, label) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied`);
  };

  return (
    <div className="p-6 space-y-5" data-testid="leadfinder-page">
      <PageHeader
        title="AI Lead Finder"
        description="Find real small businesses anywhere in the world, and let AI craft the pitch"
      />

      <Card className="p-5 bg-surface-1 border-white/10">
        <form onSubmit={search} className="grid sm:grid-cols-[1fr_1fr_1fr_auto] gap-3 items-end">
          <div className="space-y-1">
            <Label>Business Type</Label>
            <Select value={niche} onValueChange={setNiche}>
              <SelectTrigger data-testid="finder-niche" className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
              <SelectContent>{Object.entries(NICHE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1"><Label>City *</Label><Input data-testid="finder-city" required value={city} onChange={(e) => setCity(e.target.value)} placeholder="e.g. London, Dubai, Toronto" className="bg-surface-2 border-white/10" /></div>
          <div className="space-y-1"><Label>Country (optional)</Label><Input data-testid="finder-country" value={country} onChange={(e) => setCountry(e.target.value)} placeholder="e.g. UK" className="bg-surface-2 border-white/10" /></div>
          <Button data-testid="finder-search-btn" type="submit" disabled={searching} className="gap-1.5">
            {searching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
            {searching ? "Searching…" : "Find Leads"}
          </Button>
        </form>
        {place && <p className="text-xs text-graphite mt-3 flex items-center gap-1"><MapPin className="h-3 w-3" /> Searching in: {place}</p>}
      </Card>

      {results && results.length > 0 && (
        <div className="space-y-2" data-testid="finder-results">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">{results.length} real businesses found</p>
          {results.map((b) => (
            <Card key={b.osm_id} className="p-4 bg-surface-1 border-white/10 flex flex-wrap items-center gap-3 justify-between">
              <div className="min-w-0 flex-1">
                <p className="font-medium truncate">{b.name}</p>
                <p className="text-xs text-graphite flex items-center gap-1 mt-0.5"><MapPin className="h-3 w-3 shrink-0" /> <span className="truncate">{b.address}</span></p>
                <div className="flex flex-wrap items-center gap-3 mt-1.5 text-xs">
                  {b.phone && <span className="flex items-center gap-1 text-ash"><Phone className="h-3 w-3" /> {b.phone}</span>}
                  {b.email && <span className="flex items-center gap-1 text-ash"><Mail className="h-3 w-3" /> {b.email}</span>}
                  {b.website && <a href={b.website} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-info hover:underline"><Globe className="h-3 w-3" /> Website <ExternalLink className="h-2.5 w-2.5" /></a>}
                  {!b.website && <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-warning/15 text-warning">NO WEBSITE — opportunity</span>}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {imported[b.osm_id] ? (
                  <span className="text-xs text-success font-mono">✓ In pipeline</span>
                ) : (
                  <Button
                    data-testid={`finder-analyze-${b.osm_id}`}
                    size="sm" className="gap-1.5"
                    disabled={analyzing === b.osm_id}
                    onClick={() => analyze(b)}
                  >
                    {analyzing === b.osm_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                    {analyzing === b.osm_id ? "AI analyzing…" : "AI Pitch"}
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!target && !!analysis} onOpenChange={(o) => { if (!o) { setTarget(null); setAnalysis(null); } }}>
        <DialogContent className="bg-surface-1 border-white/10 max-h-[85vh] overflow-y-auto max-w-xl" data-testid="finder-analysis-dialog">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Sparkles className="h-4 w-4" /> Pitch for {target?.name}</DialogTitle></DialogHeader>
          {analysis && (
            <div className="space-y-4">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite mb-1.5">Services to pitch</p>
                <div className="flex flex-wrap gap-1.5">
                  {(analysis.services || []).map((s, i) => (
                    <span key={i} className="text-xs px-2 py-1 rounded-full bg-surface-2 border border-white/10">{s}</span>
                  ))}
                </div>
              </div>
              {analysis.reason && (
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite mb-1.5">Why them</p>
                  <p className="text-sm text-ash">{analysis.reason}</p>
                </div>
              )}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">Cold email draft</p>
                  <button onClick={() => copy(analysis.cold_email, "Email")} className="text-xs text-info flex items-center gap-1 hover:underline"><Copy className="h-3 w-3" /> Copy</button>
                </div>
                <div className="text-sm text-ash whitespace-pre-line rounded-lg bg-surface-2 border border-white/10 p-3 max-h-48 overflow-y-auto">{analysis.cold_email}</div>
              </div>
              {analysis.whatsapp_message && (
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">WhatsApp / DM version</p>
                    <button onClick={() => copy(analysis.whatsapp_message, "Message")} className="text-xs text-info flex items-center gap-1 hover:underline"><Copy className="h-3 w-3" /> Copy</button>
                  </div>
                  <div className="text-sm text-ash rounded-lg bg-surface-2 border border-white/10 p-3">{analysis.whatsapp_message}</div>
                </div>
              )}
              <Button data-testid="finder-import-btn" onClick={importLead} disabled={importing} className="w-full gap-1.5">
                <Plus className="h-4 w-4" /> {importing ? "Adding…" : "Add to Pipeline with this pitch"}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

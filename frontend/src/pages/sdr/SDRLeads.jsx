import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Search, Upload, Filter, X, Loader2, Trash2, ChevronDown } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import DiscoverDialog from "@/components/sdr/DiscoverDialog";
import ImportCsvDialog from "@/components/sdr/ImportCsvDialog";
import LeadDrawer from "@/components/sdr/LeadDrawer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { SDR_STAGE_CONFIG, QUALIFICATION_CONFIG, scoreColor } from "@/lib/sdrConfig";
import { toast } from "sonner";

const ALL = "__all__";
const PAGE_SIZE = 50;

const emptyFilters = { search: "", stage: ALL, qualification_status: ALL, min_score: "" };

export default function SDRLeads() {
  const [filters, setFilters] = useState(emptyFilters);
  const [leads, setLeads] = useState(null);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const [selected, setSelected] = useState(new Set());
  const [drawerLeadId, setDrawerLeadId] = useState(null);
  const [discoverOpen, setDiscoverOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [busy, setBusy] = useState(false);

  const searchRef = useRef(null);

  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
    if (filters.search) params.set("search", filters.search);
    if (filters.stage !== ALL) params.set("stage", filters.stage);
    if (filters.qualification_status !== ALL) {
      params.set("qualification_status", filters.qualification_status);
    }
    if (filters.min_score) params.set("min_score", filters.min_score);
    return params;
  }, [filters]);

  const load = useCallback(async () => {
    const { data } = await api.get(`/sdr/leads?${query.toString()}`);
    setLeads(data.items);
    setCursor(data.next_cursor);
    setHasMore(data.has_more);
    setSelected(new Set());
  }, [query]);

  useEffect(() => {
    // Debounced so typing in the search box does not fire a request per key.
    const timer = setTimeout(() => { load(); }, 250);
    return () => clearTimeout(timer);
  }, [load]);

  // `/` focuses search, matching the keyboard convention used elsewhere.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const params = new URLSearchParams(query);
      params.set("cursor", cursor);
      const { data } = await api.get(`/sdr/leads?${params.toString()}`);
      setLeads((current) => [...(current || []), ...data.items]);
      setCursor(data.next_cursor);
      setHasMore(data.has_more);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setLoadingMore(false);
    }
  };

  const toggle = (id) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected((current) =>
      current.size === (leads || []).length ? new Set() : new Set((leads || []).map((l) => l.id))
    );
  };

  const confirmDelete = async () => {
    setBusy(true);
    try {
      await api.delete(`/sdr/leads/${deleteTarget.id}`);
      toast.success("Lead removed");
      setDeleteTarget(null);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const bulkDelete = async () => {
    setBusy(true);
    const ids = [...selected];
    try {
      const results = await Promise.allSettled(
        ids.map((id) => api.delete(`/sdr/leads/${id}`))
      );
      const failed = results.filter((r) => r.status === "rejected").length;
      if (failed) {
        toast.warning(`Removed ${ids.length - failed}, ${failed} could not be removed`);
      } else {
        toast.success(`Removed ${ids.length} leads`);
      }
      load();
    } finally {
      setBusy(false);
    }
  };

  const filtersActive =
    filters.search || filters.stage !== ALL ||
    filters.qualification_status !== ALL || filters.min_score;

  if (!leads) {
    return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;
  }

  return (
    <div className="p-6 space-y-5" data-testid="sdr-leads-page">
      <PageHeader
        title="Lead Database"
        description="Businesses discovered, imported and scored by the AI SDR"
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              data-testid="sdr-import-btn"
              className="border-white/10 gap-1.5"
              onClick={() => setImportOpen(true)}
            >
              <Upload className="h-3.5 w-3.5" /> Import CSV
            </Button>
            <Button
              size="sm"
              data-testid="sdr-discover-btn"
              className="gap-1.5"
              onClick={() => setDiscoverOpen(true)}
            >
              <Search className="h-3.5 w-3.5" /> Discover
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-2" data-testid="sdr-leads-filters">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-carbon" />
          <Input
            ref={searchRef}
            data-testid="sdr-leads-search"
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            placeholder="Search companies…  ( / )"
            className="bg-surface-1 border-white/10 pl-8"
          />
        </div>

        <Select value={filters.stage} onValueChange={(v) => setFilters({ ...filters, stage: v })}>
          <SelectTrigger data-testid="sdr-filter-stage" className="w-[160px] bg-surface-1 border-white/10">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All stages</SelectItem>
            {Object.entries(SDR_STAGE_CONFIG).map(([key, cfg]) => (
              <SelectItem key={key} value={key}>{cfg.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.qualification_status}
          onValueChange={(v) => setFilters({ ...filters, qualification_status: v })}
        >
          <SelectTrigger data-testid="sdr-filter-qualification" className="w-[160px] bg-surface-1 border-white/10">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Any qualification</SelectItem>
            {Object.entries(QUALIFICATION_CONFIG).map(([key, cfg]) => (
              <SelectItem key={key} value={key}>{cfg.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Input
          data-testid="sdr-filter-score"
          type="number"
          min="0"
          max="100"
          value={filters.min_score}
          onChange={(e) => setFilters({ ...filters, min_score: e.target.value })}
          placeholder="Min score"
          className="w-[110px] bg-surface-1 border-white/10"
        />

        {filtersActive && (
          <Button
            size="sm"
            variant="ghost"
            data-testid="sdr-clear-filters"
            className="text-graphite gap-1"
            onClick={() => setFilters(emptyFilters)}
          >
            <X className="h-3.5 w-3.5" /> Clear
          </Button>
        )}
      </div>

      {selected.size > 0 && (
        <div
          className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-surface-2 px-4 py-2.5"
          data-testid="sdr-bulk-bar"
        >
          <span className="text-sm">{selected.size} selected</span>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              data-testid="sdr-bulk-delete"
              disabled={busy}
              className="border-danger/40 text-danger hover:text-danger gap-1.5 h-8"
              onClick={bulkDelete}
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
              Remove
            </Button>
            <Button size="sm" variant="ghost" className="text-graphite h-8" onClick={() => setSelected(new Set())}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {leads.length === 0 ? (
        filtersActive ? (
          <EmptyState
            icon={Filter}
            title="No leads match these filters"
            description="Try widening the search, or clear the filters to see everything."
            action={<Button size="sm" variant="outline" className="border-white/10" onClick={() => setFilters(emptyFilters)}>Clear filters</Button>}
            testId="sdr-leads-no-results"
          />
        ) : (
          <EmptyState
            icon={Bot}
            title="No leads yet"
            description="Run a discovery search to find businesses in a city, or import a spreadsheet you already have."
            action={
              <Button size="sm" className="gap-1.5" onClick={() => setDiscoverOpen(true)}>
                <Search className="h-3.5 w-3.5" /> Discover businesses
              </Button>
            }
            testId="sdr-leads-empty"
          />
        )
      ) : (
        <>
          <div className="flex items-center gap-3 px-4 pb-1">
            <Checkbox
              data-testid="sdr-select-all"
              checked={selected.size === leads.length && leads.length > 0}
              onCheckedChange={toggleAll}
            />
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
              {leads.length} lead{leads.length === 1 ? "" : "s"}{hasMore ? "+" : ""}
            </span>
          </div>

          <div className="space-y-2" data-testid="sdr-leads-list">
            {leads.map((lead) => (
              <div
                key={lead.id}
                data-testid={`sdr-lead-row-${lead.id}`}
                className="flex items-center gap-3 rounded-lg border border-white/10 bg-surface-1 px-4 py-3 hover:border-white/25"
              >
                <Checkbox
                  data-testid={`sdr-select-${lead.id}`}
                  checked={selected.has(lead.id)}
                  onCheckedChange={() => toggle(lead.id)}
                  onClick={(e) => e.stopPropagation()}
                />

                <button
                  className="flex flex-1 items-center gap-3 min-w-0 text-left"
                  onClick={() => setDrawerLeadId(lead.id)}
                >
                  <div className="min-w-0 flex-1">
                    <p className="font-medium truncate">{lead.company}</p>
                    <p className="text-xs text-graphite truncate">
                      {[lead.industry, lead.location].filter(Boolean).join(" · ") || "—"}
                    </p>
                  </div>

                  <span className={`font-mono text-sm font-semibold w-8 text-right ${scoreColor(lead.score || 0)}`}>
                    {lead.score || 0}
                  </span>

                  <span className="font-mono text-[9px] px-1.5 py-0.5 rounded uppercase bg-surface-2 text-ash w-28 text-center shrink-0">
                    {SDR_STAGE_CONFIG[lead.stage]?.label || lead.stage}
                  </span>
                </button>

                <button
                  data-testid={`sdr-delete-${lead.id}`}
                  onClick={() => setDeleteTarget(lead)}
                  className="text-graphite hover:text-danger p-1 shrink-0"
                  aria-label={`Remove ${lead.company}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>

          {hasMore && (
            <div className="flex justify-center pt-1">
              <Button
                size="sm"
                variant="outline"
                data-testid="sdr-load-more"
                disabled={loadingMore}
                className="border-white/10 gap-1.5"
                onClick={loadMore}
              >
                {loadingMore ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ChevronDown className="h-3.5 w-3.5" />}
                Load more
              </Button>
            </div>
          )}
        </>
      )}

      <DiscoverDialog open={discoverOpen} onOpenChange={setDiscoverOpen} onComplete={load} />
      <ImportCsvDialog open={importOpen} onOpenChange={setImportOpen} onComplete={load} />
      <LeadDrawer
        leadId={drawerLeadId}
        open={!!drawerLeadId}
        onOpenChange={(o) => !o && setDrawerLeadId(null)}
        onChanged={load}
      />

      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="sdr-delete-dialog">
          <DialogHeader><DialogTitle>Remove this lead?</DialogTitle></DialogHeader>
          <p className="text-sm text-graphite">
            "{deleteTarget?.company}" will be hidden from the SDR and the CRM pipeline. The record is
            kept so its history and audit trail stay intact, and it can be restored later.
          </p>
          <DialogFooter>
            <Button variant="outline" className="border-white/10" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" disabled={busy} onClick={confirmDelete}>Remove</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

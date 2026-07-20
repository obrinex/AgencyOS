import { useRef, useState } from "react";
import { Upload, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

/**
 * Two-step by design: preview the column mapping, then commit.
 *
 * A mis-mapped export that lands a thousand rows in the database is far more
 * annoying to undo than one extra click, so the preview is not skippable.
 */
export default function ImportCsvDialog({ open, onOpenChange, onComplete }) {
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [createLeads, setCreateLeads] = useState(true);
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setFile(null);
    setPreview(null);
    setBusy(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const pick = async (e) => {
    const chosen = e.target.files?.[0];
    if (!chosen) return;
    setFile(chosen);
    setPreview(null);
    setBusy(true);
    try {
      const body = new FormData();
      body.append("file", chosen);
      const { data } = await api.post("/sdr/discovery/preview-csv", body);
      setPreview(data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      reset();
    } finally {
      setBusy(false);
    }
  };

  const commit = async () => {
    setBusy(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const { data } = await api.post(
        `/sdr/discovery/import-csv?create_leads=${createLeads}`, body
      );
      toast.success(
        `Imported ${data.companies.inserted} new, updated ${data.companies.merged}`
      );
      onComplete?.();
      onOpenChange(false);
      reset();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const report = preview?.report;

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) reset(); }}>
      <DialogContent className="bg-surface-1 border-white/10 max-w-lg" data-testid="sdr-import-dialog">
        <DialogHeader><DialogTitle>Import from a spreadsheet</DialogTitle></DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1">
            <Label>CSV file</Label>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              data-testid="sdr-import-file"
              onChange={pick}
              className="block w-full text-sm text-graphite file:mr-3 file:rounded-md file:border file:border-white/10 file:bg-surface-2 file:px-3 file:py-1.5 file:text-sm file:text-foreground hover:file:border-white/25"
            />
            <p className="text-xs text-carbon">
              Needs a company-name column. Anything called Company, Business or Name works.
            </p>
          </div>

          {busy && !report && (
            <p className="text-sm text-graphite flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Reading the file…
            </p>
          )}

          {report && (
            <div className="rounded-lg border border-white/10 bg-surface-2 p-3 space-y-2" data-testid="sdr-import-preview">
              <p className="text-sm flex items-center gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                {report.rows_accepted} of {report.rows_read} rows are usable
              </p>

              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon mb-1">Columns mapped</p>
                <div className="flex flex-wrap gap-1">
                  {Object.entries(report.columns_mapped).map(([header, field]) => (
                    <span key={header} className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-surface-3 text-ash">
                      {header} → {field}
                    </span>
                  ))}
                </div>
              </div>

              {report.columns_ignored?.length > 0 && (
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon mb-1">Ignored</p>
                  <p className="text-xs text-graphite">{report.columns_ignored.join(", ")}</p>
                </div>
              )}

              {report.rows_skipped > 0 && (
                <p className="text-xs text-warning flex items-start gap-1.5">
                  <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
                  {report.rows_skipped} row{report.rows_skipped === 1 ? "" : "s"} will be skipped —{" "}
                  {report.skipped[0]?.reason}
                  {report.rows_skipped > 1 && " (and others)"}
                </p>
              )}

              <div className="flex items-center justify-between gap-4 pt-1">
                <Label htmlFor="sdr-import-create-leads" className="cursor-pointer text-sm">
                  Also create CRM leads
                </Label>
                <Switch
                  id="sdr-import-create-leads"
                  data-testid="sdr-import-create-leads"
                  checked={createLeads}
                  onCheckedChange={setCreateLeads}
                />
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" className="border-white/10" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            data-testid="sdr-import-submit"
            disabled={!report || busy || report.rows_accepted === 0}
            onClick={commit}
            className="gap-1.5"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            Import {report ? `${report.rows_accepted} rows` : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

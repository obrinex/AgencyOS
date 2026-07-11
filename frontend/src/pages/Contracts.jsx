import { useEffect, useState } from "react";
import { Plus, FileSignature, FileDown, Link2 } from "lucide-react";
import api, { formatApiError, downloadFile } from "@/lib/api";
import { Textarea } from "@/components/ui/textarea";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import DatePicker from "@/components/DatePicker";
import { PenLine, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { format } from "date-fns";

const STATUS_COLORS = { draft: "text-graphite", sent: "text-info", signed: "text-success", expired: "text-danger" };
const emptyForm = {
  title: "", client_id: "", start_date: "", end_date: "", renewal_date: "",
  scope: "", payment_terms: "", amount: "", agency_signatory: "", client_signatory: "", extra_clauses: "",
};

export default function Contracts() {
  const [contracts, setContracts] = useState(null);
  const [clients, setClients] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [signTarget, setSignTarget] = useState(null);
  const [signatureName, setSignatureName] = useState("");

  const load = async () => {
    const [c, cl] = await Promise.all([api.get("/contracts"), api.get("/clients")]);
    setContracts(c.data);
    setClients(cl.data);
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    if (!form.client_id) { toast.error("Select a client"); return; }
    try {
      const payload = { ...form, amount: form.amount ? parseFloat(form.amount) : null };
      await api.post("/contracts", payload);
      toast.success("Agreement created — you can download the PDF from its card");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const downloadPdf = async (c) => {
    try {
      await downloadFile(`/contracts/${c.id}/pdf`, `${c.title.replace(/[^a-zA-Z0-9-_ ]/g, "").replace(/ /g, "_") || "agreement"}.pdf`);
    } catch (err) {
      toast.error("Failed to download PDF");
    }
  };

  const copySignLink = async (c) => {
    try {
      const { data } = await api.post(`/contracts/${c.id}/share`);
      await navigator.clipboard.writeText(`${window.location.origin}/agreement/${data.share_token}`);
      toast.success("Sign link copied — send it to your client");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const setStatus = async (id, status) => {
    if (status === "signed") {
      setSignTarget(id);
      return;
    }
    await api.put(`/contracts/${id}`, { status });
    load();
  };

  const submitSign = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/contracts/${signTarget}/sign`, { signature_name: signatureName });
      toast.success("Contract marked as signed");
      setSignTarget(null);
      setSignatureName("");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  if (!contracts) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="contracts-page">
      <PageHeader
        title="Contracts"
        description={`${contracts.length} contracts`}
        actions={<Button data-testid="open-create-contract-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New Contract</Button>}
      />
      {contracts.length === 0 ? (
        <EmptyState icon={FileSignature} title="No contracts yet" description="Upload or create contracts to track renewals and expirations." testId="contracts-empty-state" />
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {contracts.map((c) => (
            <Card key={c.id} data-testid={`contract-card-${c.id}`} className="p-4 bg-surface-1 border-white/10">
              <div className="flex items-center justify-between">
                <p className="font-medium">{c.title}</p>
                <Select value={c.status} onValueChange={(v) => setStatus(c.id, v)}>
                  <SelectTrigger className="w-28 h-7 text-xs bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent>{["draft", "sent", "signed", "expired"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              {c.renewal_date && <p className="mt-2 text-xs font-mono text-graphite">Renews {format(new Date(c.renewal_date), "MMM d, yyyy")}</p>}
              {c.status === "signed" && c.signature_name && (
                <p className="mt-2 flex items-center gap-1.5 text-xs text-success"><CheckCircle2 className="h-3.5 w-3.5" /> Signed by {c.signature_name}</p>
              )}
              <div className="mt-3 flex items-center gap-2">
                <Button
                  data-testid={`download-contract-pdf-${c.id}`}
                  size="sm" variant="outline" className="gap-1.5 border-white/10 h-7 text-xs"
                  onClick={() => downloadPdf(c)}
                >
                  <FileDown className="h-3 w-3" /> Download PDF
                </Button>
                {c.status !== "signed" && (
                  <Button
                    data-testid={`copy-sign-link-${c.id}`}
                    size="sm" variant="outline" className="gap-1.5 border-white/10 h-7 text-xs"
                    onClick={() => copySignLink(c)}
                  >
                    <Link2 className="h-3 w-3" /> Copy Sign Link
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10 max-h-[85vh] overflow-y-auto" data-testid="create-contract-dialog">
          <DialogHeader><DialogTitle>Generate Agreement</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="space-y-1"><Label>Title *</Label><Input data-testid="contract-form-title" required placeholder="e.g. AI Automation Services Agreement" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1">
              <Label>Client *</Label>
              <Select value={form.client_id} onValueChange={(v) => setForm({ ...form, client_id: v })}>
                <SelectTrigger data-testid="contract-form-client" className="bg-surface-2 border-white/10"><SelectValue placeholder="Select client" /></SelectTrigger>
                <SelectContent>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.company_name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1"><Label>Scope of Work</Label><Textarea data-testid="contract-form-scope" placeholder="Describe the services you'll deliver (one point per line)" value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })} className="bg-surface-2 border-white/10" rows={4} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Contract Value (INR)</Label><Input data-testid="contract-form-amount" type="number" step="0.01" min="0" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Payment Terms</Label><Input data-testid="contract-form-payment" placeholder="e.g. 50% upfront, 50% on delivery" value={form.payment_terms} onChange={(e) => setForm({ ...form, payment_terms: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Start Date</Label><DatePicker testId="contract-form-start" value={form.start_date} onChange={(v) => setForm({ ...form, start_date: v })} /></div>
              <div className="space-y-1"><Label>End Date</Label><DatePicker testId="contract-form-end" value={form.end_date} onChange={(v) => setForm({ ...form, end_date: v })} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Your Signatory</Label><Input data-testid="contract-form-agency-sig" placeholder="Who signs for you" value={form.agency_signatory} onChange={(e) => setForm({ ...form, agency_signatory: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Client Signatory</Label><Input data-testid="contract-form-client-sig" placeholder="Who signs for the client" value={form.client_signatory} onChange={(e) => setForm({ ...form, client_signatory: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            </div>
            <div className="space-y-1"><Label>Additional Clauses (optional)</Label><Textarea data-testid="contract-form-clauses" placeholder="Any custom terms, one per line" value={form.extra_clauses} onChange={(e) => setForm({ ...form, extra_clauses: e.target.value })} className="bg-surface-2 border-white/10" rows={3} /></div>
            <p className="text-xs text-graphite">Standard clauses (confidentiality, IP, termination, liability, governing law) are included automatically in the PDF.</p>
            <DialogFooter><Button type="submit" data-testid="contract-form-submit">Generate Agreement</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={!!signTarget} onOpenChange={(o) => !o && setSignTarget(null)}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="staff-sign-contract-dialog">
          <DialogHeader><DialogTitle>Record Signature</DialogTitle></DialogHeader>
          <form onSubmit={submitSign} className="space-y-3">
            <p className="text-sm text-graphite">Record who signed this contract (e.g. captured offline or via the client portal).</p>
            <div className="space-y-1"><Label>Signature Name *</Label><Input data-testid="staff-signature-input" required value={signatureName} onChange={(e) => setSignatureName(e.target.value)} className="bg-surface-2 border-white/10 font-display italic" /></div>
            <DialogFooter><Button type="submit" data-testid="staff-signature-submit" className="gap-1.5"><PenLine className="h-3.5 w-3.5" /> Mark as Signed</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

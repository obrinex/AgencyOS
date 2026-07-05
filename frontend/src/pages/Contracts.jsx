import { useEffect, useState } from "react";
import { Plus, FileSignature } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { format } from "date-fns";

const STATUS_COLORS = { draft: "text-graphite", sent: "text-info", signed: "text-success", expired: "text-danger" };
const emptyForm = { title: "", client_id: "", start_date: "", end_date: "", renewal_date: "" };

export default function Contracts() {
  const [contracts, setContracts] = useState(null);
  const [clients, setClients] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);

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
      await api.post("/contracts", form);
      toast.success("Contract created");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const setStatus = async (id, status) => {
    await api.put(`/contracts/${id}`, { status, signed_at: status === "signed" ? new Date().toISOString() : undefined });
    load();
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
            </Card>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-contract-dialog">
          <DialogHeader><DialogTitle>New Contract</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="space-y-1"><Label>Title *</Label><Input data-testid="contract-form-title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1">
              <Label>Client *</Label>
              <Select value={form.client_id} onValueChange={(v) => setForm({ ...form, client_id: v })}>
                <SelectTrigger data-testid="contract-form-client" className="bg-surface-2 border-white/10"><SelectValue placeholder="Select client" /></SelectTrigger>
                <SelectContent>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.company_name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Start Date</Label><Input data-testid="contract-form-start" type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Renewal Date</Label><Input data-testid="contract-form-renewal" type="date" value={form.renewal_date} onChange={(e) => setForm({ ...form, renewal_date: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            </div>
            <DialogFooter><Button type="submit" data-testid="contract-form-submit">Create Contract</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

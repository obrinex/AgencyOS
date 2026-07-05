import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Plus, Receipt, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { INVOICE_STATUS_CONFIG } from "@/lib/statusConfig";
import { formatMoney } from "@/lib/currency";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

const emptyForm = { client_id: "", description: "Services rendered", quantity: 1, price: "", currency: "INR", conversion_rate: 1 };

export default function Invoices() {
  const [invoices, setInvoices] = useState(null);
  const [clients, setClients] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const load = async () => {
    const [i, c] = await Promise.all([api.get("/invoices"), api.get("/clients")]);
    setInvoices(i.data);
    setClients(c.data);
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (params.get("new") === "1") { setOpen(true); params.delete("new"); setParams(params); }
  }, [params]);

  const create = async (e) => {
    e.preventDefault();
    if (!form.client_id) { toast.error("Select a client"); return; }
    try {
      await api.post("/invoices", {
        client_id: form.client_id,
        line_items: [{ description: form.description, quantity: parseFloat(form.quantity), price: parseFloat(form.price) }],
        currency: form.currency,
        conversion_rate: parseFloat(form.conversion_rate) || 1,
      });
      toast.success("Invoice created");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const remove = async (id) => {
    await api.delete(`/invoices/${id}`);
    load();
  };

  if (!invoices) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="invoices-page">
      <PageHeader
        title="Invoices"
        description={`${invoices.length} invoices`}
        actions={<Button data-testid="open-create-invoice-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New Invoice</Button>}
      />
      {invoices.length === 0 ? (
        <EmptyState icon={Receipt} title="No invoices yet" description="Create your first invoice or wait for one to be auto-generated when a deal is won." testId="invoices-empty-state" />
      ) : (
        <div className="space-y-2" data-testid="invoices-list">
          {invoices.map((inv) => (
            <div key={inv.id} onClick={() => navigate(`/invoices/${inv.id}`)} data-testid={`invoice-row-${inv.id}`} className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-surface-1 px-4 py-3 cursor-pointer hover:border-white/25">
              <span className="font-mono text-sm">{inv.invoice_number}</span>
              <span className="font-mono text-sm flex-1">{formatMoney(inv.total, inv.currency)}</span>
              <StatusBadge config={INVOICE_STATUS_CONFIG} value={inv.status} />
              <button data-testid={`delete-invoice-${inv.id}`} onClick={(e) => { e.stopPropagation(); remove(inv.id); }} className="text-graphite hover:text-danger"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-invoice-dialog">
          <DialogHeader><DialogTitle>New Invoice</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="space-y-1">
              <Label>Client *</Label>
              <Select value={form.client_id} onValueChange={(v) => setForm({ ...form, client_id: v })}>
                <SelectTrigger data-testid="invoice-form-client" className="bg-surface-2 border-white/10"><SelectValue placeholder="Select client" /></SelectTrigger>
                <SelectContent>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.company_name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1"><Label>Line Item Description</Label><Input data-testid="invoice-form-description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Quantity</Label><Input data-testid="invoice-form-quantity" type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Price *</Label><Input data-testid="invoice-form-price" type="number" required value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1">
                <Label>Currency</Label>
                <Select value={form.currency} onValueChange={(v) => setForm({ ...form, currency: v, conversion_rate: v === "INR" ? 1 : form.conversion_rate })}>
                  <SelectTrigger data-testid="invoice-form-currency" className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="INR">INR (₹)</SelectItem><SelectItem value="USD">USD ($)</SelectItem></SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Conversion Rate (to ₹)</Label>
                <Input data-testid="invoice-form-conversion-rate" type="number" step="0.01" disabled={form.currency === "INR"} value={form.conversion_rate} onChange={(e) => setForm({ ...form, conversion_rate: e.target.value })} className="bg-surface-2 border-white/10" />
              </div>
            </div>
            <DialogFooter><Button type="submit" data-testid="invoice-form-submit">Create Invoice</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

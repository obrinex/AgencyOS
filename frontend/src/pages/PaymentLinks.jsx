import { useEffect, useState } from "react";
import { Link as LinkIcon, Plus, Copy, Trash2, CheckCircle2, ExternalLink, Loader2, Wallet } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { formatMoney } from "@/lib/currency";
import { format } from "date-fns";
import { toast } from "sonner";

const emptyForm = { title: "", amount: "", currency: "INR", note: "" };

export default function PaymentLinks() {
  const [links, setLinks] = useState(null);
  const [cryptoOn, setCryptoOn] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const load = async () => {
    const [l, p] = await Promise.all([api.get("/payment-links"), api.get("/settings/payments")]);
    setLinks(l.data);
    const p2 = p.data || {};
    setCryptoOn(!!p2.crypto_enabled && ["usdt_trc20_address", "usdt_pol_address", "usdt_bep20_address", "eth_address", "btc_address", "sol_address"].some((k) => p2[k]));
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      const { data } = await api.post("/payment-links", { ...form, amount: parseFloat(form.amount) });
      toast.success("Crypto payment link generated");
      await navigator.clipboard.writeText(data.url).catch(() => {});
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setCreating(false);
    }
  };

  const copy = (url) => { navigator.clipboard.writeText(url); toast.success("Link copied"); };
  const markPaid = async (id) => { await api.post(`/payment-links/${id}/mark-paid`); toast.success("Marked as paid"); load(); };
  const reopen = async (id) => { await api.post(`/payment-links/${id}/reopen`); load(); };
  const confirmDelete = async () => {
    await api.delete(`/payment-links/${deleteTarget.id}`);
    toast.success("Link deleted");
    setDeleteTarget(null);
    load();
  };

  if (!links) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6 space-y-5" data-testid="payment-links-page">
      <PageHeader
        title="Payment Links"
        description="Generate standalone crypto payment links for any amount — no invoice needed"
        actions={<Button data-testid="new-payment-link-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New Link</Button>}
      />

      {!cryptoOn && (
        <Card className="p-4 bg-warning/10 border-warning/20" data-testid="crypto-off-warning">
          <p className="text-sm text-warning flex items-center gap-2"><Wallet className="h-4 w-4" /> Crypto isn't set up yet.</p>
          <p className="text-xs text-graphite mt-1">Add your wallet addresses in <span className="text-foreground">Settings → Payments</span> and enable crypto, or these links will have no wallet to show.</p>
        </Card>
      )}

      {links.length === 0 ? (
        <EmptyState icon={LinkIcon} title="No payment links yet" description="Generate a crypto payment link and share it with anyone to collect payment." testId="payment-links-empty" />
      ) : (
        <div className="space-y-2">
          {links.map((l) => (
            <Card key={l.id} data-testid={`payment-link-${l.id}`} className="p-4 bg-surface-1 border-white/10 flex flex-wrap items-center gap-3 justify-between">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="font-medium truncate">{l.title}</p>
                  {l.status === "paid" ? (
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-success/15 text-success uppercase">Paid</span>
                  ) : l.payment_claim ? (
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-info/15 text-info uppercase">Claim to verify</span>
                  ) : (
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-surface-2 text-graphite uppercase">Active</span>
                  )}
                </div>
                <p className="text-xs text-graphite font-mono mt-0.5 truncate">{l.url}</p>
                {l.payment_claim && l.status !== "paid" && (
                  <p className="text-xs text-info mt-1">Tx from {l.payment_claim.payer_email} via {l.payment_claim.network} — verify in your wallet.</p>
                )}
                <p className="text-[11px] text-carbon font-mono mt-1">{format(new Date(l.created_at), "MMM d, yyyy")}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="font-mono font-semibold">{formatMoney(l.amount, l.currency)}</span>
                <Button size="sm" variant="outline" className="border-white/10 gap-1 h-8" onClick={() => copy(l.url)}><Copy className="h-3.5 w-3.5" /> Copy</Button>
                <a href={l.url} target="_blank" rel="noreferrer"><Button size="sm" variant="outline" className="border-white/10 gap-1 h-8"><ExternalLink className="h-3.5 w-3.5" /> Open</Button></a>
                {l.status === "paid" ? (
                  <Button size="sm" variant="outline" className="border-white/10 h-8 text-xs" onClick={() => reopen(l.id)}>Reopen</Button>
                ) : (
                  <Button size="sm" variant="outline" className="border-success/40 text-success hover:text-success gap-1 h-8" onClick={() => markPaid(l.id)}><CheckCircle2 className="h-3.5 w-3.5" /> Mark Paid</Button>
                )}
                <button data-testid={`delete-link-${l.id}`} onClick={() => setDeleteTarget(l)} className="text-graphite hover:text-danger p-1"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-link-dialog">
          <DialogHeader><DialogTitle>New Crypto Payment Link</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="space-y-1"><Label>What's this for? *</Label><Input data-testid="link-title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Website deposit, Consultation fee" className="bg-surface-2 border-white/10" /></div>
            <div className="grid grid-cols-[1fr_120px] gap-3">
              <div className="space-y-1"><Label>Amount *</Label><Input data-testid="link-amount" required type="number" step="0.01" min="0" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1">
                <Label>Currency</Label>
                <Select value={form.currency} onValueChange={(v) => setForm({ ...form, currency: v })}>
                  <SelectTrigger className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="INR">INR</SelectItem><SelectItem value="USD">USD</SelectItem></SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1"><Label>Note to payer (optional)</Label><Input data-testid="link-note" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <p className="text-xs text-graphite">The link opens a page showing your crypto wallet addresses and QR codes. The payer sends crypto and submits their transaction hash; you'll be notified to verify and mark it paid.</p>
            <DialogFooter><Button type="submit" data-testid="create-link-submit" disabled={creating} className="gap-1.5">{creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} Generate & Copy Link</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <DialogContent className="bg-surface-1 border-white/10">
          <DialogHeader><DialogTitle>Delete payment link?</DialogTitle></DialogHeader>
          <p className="text-sm text-graphite">"{deleteTarget?.title}" will stop working for anyone who has the link.</p>
          <DialogFooter>
            <Button variant="outline" className="border-white/10" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={confirmDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

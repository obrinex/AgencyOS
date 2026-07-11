import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, HeartPulse, Plus, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { formatMoney } from "@/lib/currency";
import { toast } from "sonner";

const emptyForm = { company_name: "", website: "", industry: "", location: "" };

export default function Clients() {
  const [clients, setClients] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const navigate = useNavigate();

  const load = () => api.get("/clients").then((r) => setClients(r.data));

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.post("/clients", form);
      toast.success(`Client "${data.company_name}" added`);
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const confirmDelete = async () => {
    try {
      await api.delete(`/clients/${deleteTarget.id}`);
      toast.success(`Client "${deleteTarget.company_name}" removed`);
      setDeleteTarget(null);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  if (!clients) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="clients-page">
      <PageHeader
        title="Clients"
        description={`${clients.length} active client accounts`}
        actions={<Button data-testid="open-create-client-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> Add Client</Button>}
      />
      {clients.length === 0 ? (
        <EmptyState
          icon={Building2}
          title="No clients yet"
          description="Add a client directly, or win a deal in your Pipeline to create one automatically."
          testId="clients-empty-state"
        />
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {clients.map((c) => (
            <Card
              key={c.id}
              data-testid={`client-card-${c.id}`}
              onClick={() => navigate(`/clients/${c.id}`)}
              className="p-5 bg-surface-1 border-white/10 cursor-pointer hover:border-white/25 transition-colors group"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 border border-white/10">
                  <Building2 className="h-4 w-4 text-graphite" />
                </div>
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1 text-xs font-mono text-success"><HeartPulse className="h-3 w-3" /> {c.health_score ?? 100}</span>
                  <button
                    data-testid={`delete-client-${c.id}`}
                    onClick={(e) => { e.stopPropagation(); setDeleteTarget(c); }}
                    className="text-graphite hover:text-danger opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Remove client"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              <p className="font-medium truncate">{c.company_name}</p>
              <p className="text-xs text-graphite">{c.industry || "—"}</p>
              <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                <div>
                  <p className="text-graphite">Revenue</p>
                  <p className="font-mono font-semibold text-success">{formatMoney(c.revenue_generated)}</p>
                </div>
                <div>
                  <p className="text-graphite">Outstanding</p>
                  <p className="font-mono font-semibold text-warning">{formatMoney(c.outstanding_amount)}</p>
                </div>
              </div>
              <p className="mt-3 text-[11px] font-mono text-carbon">{c.projects_count || 0} project(s)</p>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-client-dialog">
          <DialogHeader><DialogTitle>Add Client</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="space-y-1"><Label>Company Name *</Label><Input data-testid="client-form-name" required value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1"><Label>Website</Label><Input data-testid="client-form-website" value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} placeholder="https://" className="bg-surface-2 border-white/10" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Industry</Label><Input data-testid="client-form-industry" value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Location</Label><Input data-testid="client-form-location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            </div>
            <DialogFooter><Button type="submit" data-testid="client-form-submit">Add Client</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="delete-client-dialog">
          <DialogHeader>
            <DialogTitle>Remove client?</DialogTitle>
            <DialogDescription>
              This permanently removes <span className="text-foreground font-medium">{deleteTarget?.company_name}</span> and revokes their portal access. Projects and invoices linked to them stay in your records.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" className="border-white/10" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" data-testid="confirm-delete-client-btn" onClick={confirmDelete}>Remove Client</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, FileText, Sparkles } from "lucide-react";
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

const emptyForm = { title: "", client_id: "" };

export default function Proposals() {
  const [proposals, setProposals] = useState(null);
  const [clients, setClients] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const navigate = useNavigate();

  const load = async () => {
    const [p, c] = await Promise.all([api.get("/proposals"), api.get("/clients")]);
    setProposals(p.data);
    setClients(c.data);
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.post("/proposals", { ...form, content: "# " + form.title + "\n\nStart writing your proposal here..." });
      toast.success("Proposal created");
      setOpen(false);
      setForm(emptyForm);
      navigate(`/proposals/${data.id}`);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  if (!proposals) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="proposals-page">
      <PageHeader
        title="Proposals"
        description={`${proposals.length} proposals`}
        actions={<Button data-testid="open-create-proposal-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New Proposal</Button>}
      />
      {proposals.length === 0 ? (
        <EmptyState icon={FileText} title="No proposals yet" description="Create a proposal manually or let the AI Assistant draft one for you." testId="proposals-empty-state" />
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {proposals.map((p) => (
            <Card key={p.id} onClick={() => navigate(`/proposals/${p.id}`)} data-testid={`proposal-card-${p.id}`} className="p-4 bg-surface-1 border-white/10 cursor-pointer hover:border-white/25">
              <p className="font-medium truncate">{p.title}</p>
              <p className="text-xs text-graphite mt-1 uppercase font-mono">{p.status} · v{p.version}</p>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-proposal-dialog">
          <DialogHeader><DialogTitle>New Proposal</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="space-y-1"><Label>Title *</Label><Input data-testid="proposal-form-title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1">
              <Label>Client</Label>
              <Select value={form.client_id} onValueChange={(v) => setForm({ ...form, client_id: v })}>
                <SelectTrigger data-testid="proposal-form-client" className="bg-surface-2 border-white/10"><SelectValue placeholder="Select client (optional)" /></SelectTrigger>
                <SelectContent>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.company_name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <DialogFooter><Button type="submit" data-testid="proposal-form-submit">Create Proposal</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

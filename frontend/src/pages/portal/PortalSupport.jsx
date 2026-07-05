import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, LifeBuoy } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { TICKET_STATUS_CONFIG, PRIORITY_CONFIG } from "@/lib/statusConfig";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

const emptyForm = { subject: "", description: "", priority: "medium" };

export default function PortalSupport() {
  const [tickets, setTickets] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const navigate = useNavigate();

  const load = async () => {
    const { data } = await api.get("/portal/tickets");
    setTickets(data);
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/portal/tickets", form);
      toast.success("Support ticket submitted");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  if (!tickets) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="portal-support-page">
      <PageHeader
        title="Support"
        description={`${tickets.length} tickets`}
        actions={<Button data-testid="portal-open-create-ticket-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New Ticket</Button>}
      />
      {tickets.length === 0 ? (
        <EmptyState icon={LifeBuoy} title="No tickets yet" description="Need help? Submit a support ticket and our team will respond." testId="portal-support-empty" />
      ) : (
        <div className="space-y-2">
          {tickets.map((t) => (
            <Card key={t.id} onClick={() => navigate(`/portal/support/${t.id}`)} data-testid={`portal-ticket-row-${t.id}`} className="p-4 bg-surface-1 border-white/10 cursor-pointer hover:border-white/25 flex items-center justify-between gap-3">
              <span className="text-sm flex-1 truncate">{t.subject}</span>
              <StatusBadge config={PRIORITY_CONFIG} value={t.priority} />
              <StatusBadge config={TICKET_STATUS_CONFIG} value={t.status} />
            </Card>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="portal-create-ticket-dialog">
          <DialogHeader><DialogTitle>New Support Ticket</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="space-y-1"><Label>Subject *</Label><Input data-testid="portal-ticket-form-subject" required value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1"><Label>Description *</Label><Textarea data-testid="portal-ticket-form-description" required value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <DialogFooter><Button type="submit" data-testid="portal-ticket-form-submit">Submit Ticket</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

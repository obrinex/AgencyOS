import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Send, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { TICKET_STATUS_CONFIG } from "@/lib/statusConfig";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { formatDistanceToNow } from "date-fns";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

export default function TicketDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [ticket, setTicket] = useState(null);
  const [message, setMessage] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = async () => {
    const { data } = await api.get(`/tickets/${id}`);
    setTicket(data);
  };

  useEffect(() => { load(); }, [id]);

  const send = async () => {
    if (!message.trim()) return;
    await api.post(`/tickets/${id}/messages`, { message });
    setMessage("");
    load();
  };

  const setStatus = async (status) => {
    await api.put(`/tickets/${id}`, { status });
    load();
  };

  const remove = async () => {
    setDeleting(true);
    try {
      await api.delete(`/tickets/${id}`);
      toast.success("Ticket deleted");
      navigate("/support");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      setDeleting(false);
    }
  };

  if (!ticket) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-4" data-testid="ticket-detail-page">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-sm text-graphite hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back
      </button>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold">{ticket.subject}</h1>
          <p className="text-sm text-graphite mt-1">{ticket.description}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {user.role !== "client" && (
            <Select value={ticket.status} onValueChange={setStatus}>
              <SelectTrigger data-testid="ticket-status-select" className="w-36 bg-surface-1 border-white/10"><SelectValue /></SelectTrigger>
              <SelectContent>{Object.keys(TICKET_STATUS_CONFIG).map((s) => <SelectItem key={s} value={s}>{TICKET_STATUS_CONFIG[s].label}</SelectItem>)}</SelectContent>
            </Select>
          )}
          {user.role === "admin" && (
            <Button
              variant="ghost" size="icon"
              className="text-graphite hover:text-danger"
              onClick={() => setConfirmDelete(true)}
              title="Delete ticket"
              data-testid="ticket-delete-btn"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      <div className="space-y-3" data-testid="ticket-messages">
        {ticket.messages?.map((m, i) => (
          <div key={i} className={`flex ${m.sender_role === "client" ? "justify-start" : "justify-end"}`}>
            <div className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${m.sender_role === "client" ? "bg-surface-2 border border-white/10" : "bg-foreground text-background"}`}>
              <p>{m.message}</p>
              <p className="text-[10px] font-mono opacity-60 mt-1">{formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}</p>
            </div>
          </div>
        ))}
        {(!ticket.messages || ticket.messages.length === 0) && <p className="text-sm text-graphite text-center py-6">No messages yet</p>}
      </div>

      <Card className="p-3 bg-surface-1 border-white/10 flex items-end gap-2">
        <Textarea data-testid="ticket-message-input" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Type a reply..." className="bg-surface-2 border-white/10 min-h-[40px]" />
        <Button data-testid="ticket-message-send" size="icon" onClick={send}><Send className="h-4 w-4" /></Button>
      </Card>

      <Dialog open={confirmDelete} onOpenChange={(o) => !o && setConfirmDelete(false)}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="ticket-delete-dialog">
          <DialogHeader>
            <DialogTitle>Delete ticket?</DialogTitle>
            <DialogDescription>
              This permanently deletes <span className="text-foreground font-medium">{ticket.subject}</span> and all of its messages. This can't be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" className="border-white/10" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button variant="destructive" disabled={deleting} onClick={remove} data-testid="confirm-delete-ticket-btn">
              {deleting ? "Deleting…" : "Delete Ticket"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Send } from "lucide-react";
import api from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { TICKET_STATUS_CONFIG } from "@/lib/statusConfig";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDistanceToNow } from "date-fns";

export default function PortalTicketDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [ticket, setTicket] = useState(null);
  const [message, setMessage] = useState("");

  const load = async () => {
    const { data } = await api.get(`/portal/tickets`);
    setTicket(data.find((t) => t.id === id));
  };

  useEffect(() => { load(); }, [id]);

  const send = async () => {
    if (!message.trim()) return;
    await api.post(`/portal/tickets/${id}/messages`, { message });
    setMessage("");
    load();
  };

  if (!ticket) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-4" data-testid="portal-ticket-detail-page">
      <button onClick={() => navigate("/portal/support")} className="flex items-center gap-1.5 text-sm text-graphite hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Support
      </button>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold">{ticket.subject}</h1>
          <p className="text-sm text-graphite mt-1">{ticket.description}</p>
        </div>
        <StatusBadge config={TICKET_STATUS_CONFIG} value={ticket.status} />
      </div>

      <div className="space-y-3">
        {ticket.messages?.filter((m) => !m.internal).map((m, i) => (
          <div key={i} className={`flex ${m.sender_role === "client" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${m.sender_role === "client" ? "bg-foreground text-background" : "bg-surface-2 border border-white/10"}`}>
              <p>{m.message}</p>
              <p className="text-[10px] font-mono opacity-60 mt-1">{formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}</p>
            </div>
          </div>
        ))}
        {(!ticket.messages || ticket.messages.filter((m) => !m.internal).length === 0) && <p className="text-sm text-graphite text-center py-6">No messages yet</p>}
      </div>

      <Card className="p-3 bg-surface-1 border-white/10 flex items-end gap-2">
        <Textarea data-testid="portal-ticket-message-input" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Type a reply..." className="bg-surface-2 border-white/10 min-h-[40px]" />
        <Button data-testid="portal-ticket-message-send" size="icon" onClick={send}><Send className="h-4 w-4" /></Button>
      </Card>
    </div>
  );
}

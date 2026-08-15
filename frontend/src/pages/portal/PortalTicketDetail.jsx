import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Send, Loader2, LifeBuoy } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { TICKET_STATUS_CONFIG, PRIORITY_CONFIG } from "@/lib/statusConfig";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";

/** One ticket, and the conversation on it.
 *
 *  Fetches the single ticket rather than the whole list and finding it — which
 *  is also what marks it read, so the badge on Support clears by opening the
 *  thing the badge was pointing at.
 */

const POLL_MS = 15000;

export default function PortalTicketDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [ticket, setTicket] = useState(null);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/portal/tickets/${id}`);
      setTicket(data);
    } catch {
      setTicket(false);
    }
  }, [id]);

  useEffect(() => {
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [ticket?.messages?.length]);

  const send = async () => {
    const body = message.trim();
    if (!body || sending) return;
    setSending(true);
    setMessage("");
    try {
      await api.post(`/portal/tickets/${id}/messages`, { message: body });
      await load();
    } catch (err) {
      setMessage(body);
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setSending(false); }
  };

  if (ticket === null) {
    return <div className="p-4 sm:p-6"><Skeleton className="h-64 w-full rounded-2xl bg-surface-1" /></div>;
  }
  if (ticket === false) {
    return (
      <div className="mx-auto max-w-3xl p-4 sm:p-6">
        <div className="obx-glass rounded-2xl px-6 py-14 text-center">
          <LifeBuoy className="mx-auto h-5 w-5 text-carbon" />
          <p className="mt-3 text-sm text-graphite">This ticket could not be found.</p>
          <button
            onClick={() => navigate("/portal/support")}
            className="obx-glass obx-lift mt-4 rounded-xl px-3.5 py-2 text-sm"
          >
            Back to Support
          </button>
        </div>
      </div>
    );
  }

  const thread = (ticket.messages || []).filter((m) => !m.internal);

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4 sm:p-6" data-testid="portal-ticket-detail-page">
      <button
        onClick={() => navigate("/portal/support")}
        className="flex items-center gap-1.5 text-sm text-graphite transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Support
      </button>

      <header className="obx-glass obx-sheen relative overflow-hidden rounded-2xl p-4 sm:p-5">
        <div className="obx-aurora pointer-events-none absolute inset-0" />
        <div className="relative z-10">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h1 className="font-display text-xl font-bold tracking-tight">{ticket.subject}</h1>
            <div className="flex shrink-0 items-center gap-2">
              <StatusBadge config={PRIORITY_CONFIG} value={ticket.priority} />
              <StatusBadge config={TICKET_STATUS_CONFIG} value={ticket.status} />
            </div>
          </div>
          {ticket.description && (
            <p className="mt-2 max-w-prose whitespace-pre-line text-sm leading-relaxed text-ash">
              {ticket.description}
            </p>
          )}
          {ticket.created_at && (
            <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.14em] text-carbon">
              Opened {formatDistanceToNow(new Date(ticket.created_at), { addSuffix: true })}
            </p>
          )}
        </div>
      </header>

      <div className="space-y-2.5">
        {thread.length === 0 ? (
          <p className="py-8 text-center text-sm text-graphite">
            No replies yet. The team has this.
          </p>
        ) : (
          thread.map((m, i) => {
            const mine = m.sender_role === "client";
            return (
              <div
                key={i}
                className={`obx-message-in flex ${mine ? "justify-end" : "justify-start"}`}
              >
                <div className={`max-w-[86%] sm:max-w-[76%] ${mine ? "text-right" : ""}`}>
                  {!mine && (
                    <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-primary/80">
                      Obrinex team
                    </p>
                  )}
                  <div
                    className={`inline-block whitespace-pre-line break-words rounded-2xl px-3.5 py-2.5 text-left text-sm leading-relaxed ${
                      mine
                        ? "border border-primary/25 bg-primary/[0.12]"
                        : "obx-glass"
                    }`}
                  >
                    {m.message}
                  </div>
                  <p className="mt-1 font-mono text-[9px] text-carbon">
                    {m.created_at
                      ? formatDistanceToNow(new Date(m.created_at), { addSuffix: true })
                      : ""}
                  </p>
                </div>
              </div>
            );
          })
        )}
        <div ref={endRef} />
      </div>

      <div className="obx-glass sticky bottom-4 flex items-end gap-2 rounded-2xl p-2">
        <textarea
          rows={1}
          value={message}
          onChange={(e) => {
            setMessage(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }}
          placeholder="Type a reply…"
          data-testid="portal-ticket-message-input"
          className="max-h-[140px] flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-carbon"
        />
        <button
          onClick={send}
          disabled={sending || !message.trim()}
          data-testid="portal-ticket-message-send"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-background transition-opacity disabled:opacity-30"
        >
          {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}

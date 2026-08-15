import { useEffect, useRef, useState } from "react";
import { Send, Loader2, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import PageHeader from "@/components/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDistanceToNow } from "date-fns";
import { toast } from "sonner";

/** The community room, seen from the agency's side.
 *
 *  Same room and same messages the members see — not a moderation console over
 *  a separate feed. Staff post as "Obrinex" so a member can tell at a glance
 *  whether they are hearing from another founder or from the house.
 */
export default function FoundingCommunity() {
  const { user } = useAuth();
  const [messages, setMessages] = useState(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef(null);

  const load = async () => {
    const { data } = await api.get("/founding/chat");
    setMessages(data);
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = async () => {
    if (!text.trim()) return;
    setSending(true);
    try {
      await api.post("/founding/chat", { body: text });
      setText("");
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setSending(false); }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/founding/chat/${id}`);
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  return (
    <div className="p-6 space-y-5" data-testid="founding-community-page">
      <PageHeader
        title="Community"
        description="One room, shared with the circle. You post as Obrinex."
      />

      {!messages ? (
        <Skeleton className="h-[65vh] bg-surface-1" />
      ) : (
        <Card className="bg-surface-1 border-white/10 flex flex-col h-[65vh] max-w-3xl">
          <div className="flex-1 overflow-y-auto p-4 space-y-3" data-testid="founding-community-thread">
            {messages.length === 0 && (
              <div className="py-16 text-center space-y-1">
                <p className="text-sm text-graphite">The room is empty.</p>
                <p className="text-xs text-carbon">
                  Say the first thing — a room nobody has spoken in is one nobody speaks in.
                </p>
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className="group rounded-lg border border-white/10 bg-surface-2 p-3">
                <div className="flex items-center gap-2">
                  <span className={`text-[11px] font-medium ${m.is_host ? "text-accent" : "text-ash"}`}>
                    {m.author_name}
                  </span>
                  {m.is_host && (
                    <span className="rounded-sm bg-accent/10 px-1.5 py-px font-mono text-[9px] uppercase tracking-wide text-accent">
                      Host
                    </span>
                  )}
                  {m.author_company && (
                    <span className="text-[11px] text-carbon">· {m.author_company}</span>
                  )}
                  <span className="ml-auto text-[10px] text-carbon">
                    {m.created_at ? formatDistanceToNow(new Date(m.created_at), { addSuffix: true }) : ""}
                  </span>
                  {user?.role === "admin" && (
                    <button
                      onClick={() => remove(m.id)}
                      title="Delete this message"
                      data-testid={`founding-community-delete-${m.id}`}
                      className="opacity-0 group-hover:opacity-100 text-carbon hover:text-danger transition-opacity"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
                <p className="mt-1.5 text-sm whitespace-pre-line break-words">{m.body}</p>
              </div>
            ))}
            <div ref={endRef} />
          </div>

          <div className="border-t border-white/10 p-3 flex items-center gap-2">
            <Input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder="Post to the circle…"
              className="bg-surface-2 border-white/10"
              data-testid="founding-community-input"
            />
            <Button onClick={send} disabled={sending} data-testid="founding-community-send">
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}

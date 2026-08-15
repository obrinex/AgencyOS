import { useEffect, useRef, useState } from "react";
import { MessageSquare, Sparkles, Send, Loader2, LogOut } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

/** The Founding Circle's own portal.
 *
 *  Deliberately not the client portal. A member has their own role, so the
 *  client routes are unreachable from here and these are unreachable from
 *  there — the separation is enforced by the API, not by hiding links.
 */
export default function FoundingPortal() {
  const { user, logout } = useAuth();
  const [me, setMe] = useState(null);
  const [tab, setTab] = useState("chat");

  useEffect(() => {
    api.get("/founding/me").then(({ data }) => setMe(data)).catch(() => setMe(false));
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-white/10 px-6 py-4 flex items-center gap-4">
        <div>
          <h1 className="font-display text-lg font-bold tracking-tight">Founding Circle</h1>
          <p className="text-xs text-graphite">
            {me ? `${me.members} of ${me.seats_total} seats taken` : " "}
          </p>
        </div>
        <nav className="ml-6 flex items-center gap-1">
          {[
            { key: "chat", label: "Community", icon: MessageSquare },
            { key: "assistant", label: "Assistant", icon: Sparkles },
          ].map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              data-testid={`founding-tab-${t.key}`}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors ${
                tab === t.key ? "bg-surface-2 text-foreground" : "text-ash hover:bg-surface-1"
              }`}
            >
              <t.icon className="h-3.5 w-3.5" /> {t.label}
            </button>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-sm text-graphite">{user?.name}</span>
          <Button size="icon" variant="ghost" onClick={logout} data-testid="founding-logout">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>

      <main className="p-6 max-w-3xl mx-auto">
        {tab === "chat" ? <CommunityChat /> : <Assistant />}
      </main>
    </div>
  );
}

function CommunityChat() {
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

  if (!messages) return <Skeleton className="h-96 bg-surface-1" />;

  return (
    <Card className="bg-surface-1 border-white/10 flex flex-col h-[70vh]" data-testid="founding-chat">
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <p className="text-sm text-graphite text-center py-12">
            Nothing here yet. Ten people, one room — say something.
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className="rounded-lg bg-surface-2 border border-white/10 p-3">
            <p className="text-[11px] text-graphite">
              {m.author_name}
              {m.author_company ? ` · ${m.author_company}` : ""}
            </p>
            <p className="mt-1 text-sm whitespace-pre-line break-words">{m.body}</p>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="border-t border-white/10 p-3 flex items-center gap-2">
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Message the circle…"
          className="bg-surface-2 border-white/10"
          data-testid="founding-chat-input"
        />
        <Button onClick={send} disabled={sending} data-testid="founding-chat-send">
          {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </div>
    </Card>
  );
}

function Assistant() {
  const [thread, setThread] = useState(null);
  const [text, setText] = useState("");
  const [asking, setAsking] = useState(false);
  const endRef = useRef(null);

  const load = async () => {
    const { data } = await api.get("/founding/assistant");
    setThread(data);
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [thread]);

  const ask = async () => {
    if (!text.trim()) return;
    setAsking(true);
    try {
      await api.post("/founding/assistant", { message: text });
      setText("");
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setAsking(false); }
  };

  if (!thread) return <Skeleton className="h-96 bg-surface-1" />;

  return (
    <Card className="bg-surface-1 border-white/10 flex flex-col h-[70vh]" data-testid="founding-assistant">
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {thread.length === 0 && (
          <div className="text-center py-12 space-y-2">
            <Sparkles className="h-5 w-5 text-graphite mx-auto" />
            <p className="text-sm text-graphite">Your assistant. Ask it anything general.</p>
            <p className="text-xs text-carbon">
              It can't see the agency's client data or anyone else's information.
            </p>
          </div>
        )}
        {thread.map((m) => (
          <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={`max-w-[80%] rounded-lg p-3 text-sm whitespace-pre-line break-words ${
              m.role === "user" ? "bg-surface-2 border border-white/10" : "bg-accent/5 border border-accent/20"
            }`}>
              {m.content}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="border-t border-white/10 p-3 flex items-center gap-2">
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }}
          placeholder="Ask your assistant…"
          className="bg-surface-2 border-white/10"
          data-testid="founding-assistant-input"
        />
        <Button onClick={ask} disabled={asking} data-testid="founding-assistant-send">
          {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </div>
    </Card>
  );
}

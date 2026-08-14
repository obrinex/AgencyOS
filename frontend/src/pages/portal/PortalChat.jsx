import { useState, useEffect, useCallback, useRef } from "react";
import { Send, Paperclip, Loader2, X, MessageSquare } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

// The client's side of the one-per-client chat thread (roadmap Phase A).
// Their own messages sit on the right; the team/agent on the left.
export default function PortalChat() {
  const [messages, setMessages] = useState(null);
  const [text, setText] = useState("");
  const [pending, setPending] = useState([]); // [{file_id, filename}]
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef();
  const scrollRef = useRef();

  const load = useCallback(async () => {
    try { const { data } = await api.get("/portal/chat"); setMessages(data); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); setMessages([]); }
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);
  useEffect(() => { scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight); }, [messages]);

  const attach = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/files/upload?related_type=chat", form,
        { headers: { "Content-Type": "multipart/form-data" } });
      setPending((p) => [...p, { file_id: data.id, filename: data.filename || data.name || file.name }]);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setUploading(false); }
  };

  const send = async () => {
    if (!text.trim() && pending.length === 0) return;
    setSending(true);
    try {
      await api.post("/portal/chat", {
        body: text.trim(), attachment_file_ids: pending.map((p) => p.file_id),
      });
      setText(""); setPending([]);
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setSending(false); }
  };

  return (
    <div className="p-4 sm:p-6 max-w-3xl mx-auto" data-testid="portal-chat">
      <h1 className="font-display text-2xl font-bold mb-1">Messages</h1>
      <p className="text-sm text-graphite mb-4">Chat directly with your Obrinex team.</p>

      <Card className="flex flex-col h-[68vh] bg-surface-1 border-white/10 overflow-hidden">
        {!messages ? <div className="p-4"><Skeleton className="h-40 w-full" /></div> : (
          <>
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.length === 0 && (
                <div className="h-full flex items-center justify-center text-sm text-graphite">
                  <div className="text-center"><MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-40" />No messages yet — say hello to your team.</div>
                </div>
              )}
              {messages.map((m) => {
                const mine = m.sender_type === "client";
                return (
                  <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[78%] rounded-2xl px-3 py-2 text-sm ${mine ? "bg-primary text-background" : "bg-surface-2"}`}>
                      {!mine && <div className="text-[10px] opacity-70 mb-0.5">{m.sender_name || "Obrinex team"}</div>}
                      {m.body && <p className="whitespace-pre-wrap">{m.body}</p>}
                      {(m.attachments || []).map((a) => (
                        <a key={a.file_id} href={`${api.defaults.baseURL}/files/${a.file_id}/download`}
                          target="_blank" rel="noreferrer"
                          className="flex items-center gap-1 underline mt-1 text-xs opacity-90">
                          <Paperclip className="h-3 w-3" />{a.filename}
                        </a>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            {pending.length > 0 && (
              <div className="px-4 py-2 flex flex-wrap gap-2 border-t border-white/10">
                {pending.map((p) => (
                  <span key={p.file_id} className="flex items-center gap-1 text-xs bg-surface-2 rounded px-2 py-1">
                    <Paperclip className="h-3 w-3" />{p.filename}
                    <X className="h-3 w-3 cursor-pointer" onClick={() => setPending((x) => x.filter((f) => f.file_id !== p.file_id))} />
                  </span>
                ))}
              </div>
            )}

            <div className="border-t border-white/10 p-3 flex items-center gap-2">
              <input ref={fileRef} type="file" className="hidden" onChange={attach} />
              <Button variant="ghost" size="icon" onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="portal-chat-attach">
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
              </Button>
              <Input value={text} onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                placeholder="Type a message…" className="bg-surface-2 border-white/10" data-testid="portal-chat-input" />
              <Button onClick={send} disabled={sending} data-testid="portal-chat-send">
                {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

import { useState, useEffect, useCallback, useRef } from "react";
import { MessageSquare, Send, Paperclip, Loader2, X, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

// Client ↔ team chat (roadmap Phase A). One thread per client; the team posts
// here and the client sees it in their portal. Attachments reuse /files/upload.
export default function Chat() {
  const { user } = useAuth();
  const [threads, setThreads] = useState(null);
  const [clients, setClients] = useState([]);
  const [active, setActive] = useState(null); // client_id
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [pending, setPending] = useState([]); // [{file_id, filename}]
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState(() => new Set()); // client_ids to delete
  const [deletingSelected, setDeletingSelected] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const isAdmin = user?.role === "admin";
  const fileRef = useRef();
  const scrollRef = useRef();

  const loadThreads = useCallback(async () => {
    try { const { data } = await api.get("/chat/threads"); setThreads(data); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); setThreads([]); }
  }, []);

  const loadMessages = useCallback(async (cid) => {
    if (!cid) return;
    try { const { data } = await api.get(`/chat/threads/${cid}/messages`); setMessages(data); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  }, []);

  useEffect(() => { loadThreads(); }, [loadThreads]);
  useEffect(() => { api.get("/clients").then(({ data }) => setClients(data || [])).catch(() => {}); }, []);

  useEffect(() => {
    if (!active) return;
    loadMessages(active);
    const t = setInterval(() => loadMessages(active), 5000); // light polling
    return () => clearInterval(t);
  }, [active, loadMessages]);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages]);

  const openThread = (cid) => { setActive(cid); setText(""); setPending([]); };

  const attach = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !active) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post(
        `/files/upload?related_type=chat&related_id=${active}`, form,
        { headers: { "Content-Type": "multipart/form-data" } });
      setPending((p) => [...p, { file_id: data.id, filename: data.filename || data.name || file.name }]);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setUploading(false); }
  };

  const send = async () => {
    if (!active || (!text.trim() && pending.length === 0)) return;
    setSending(true);
    try {
      await api.post(`/chat/threads/${active}/messages`, {
        body: text.trim(), attachment_file_ids: pending.map((p) => p.file_id),
      });
      setText(""); setPending([]);
      await loadMessages(active);
      loadThreads();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setSending(false); }
  };

  const toggleSelected = (cid) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(cid) ? next.delete(cid) : next.add(cid);
      return next;
    });
  };

  const selectAll = () => {
    const ids = (threads || []).map((t) => t.client_id);
    const allOn = ids.length > 0 && ids.every((id) => selected.has(id));
    setSelected(allOn ? new Set() : new Set(ids));
  };

  const deleteSelected = async () => {
    setDeletingSelected(true);
    const ids = [...selected];
    let ok = 0;
    for (const cid of ids) {
      try { await api.delete(`/chat/threads/${cid}`); ok += 1; if (cid === active) { setActive(null); setMessages([]); } }
      catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    }
    setDeletingSelected(false);
    setConfirmOpen(false);
    setSelected(new Set());
    if (ok) toast.success(`${ok} conversation${ok === 1 ? "" : "s"} deleted`);
    loadThreads();
  };

  const activeThread = threads?.find((t) => t.client_id === active);
  const activeName = activeThread?.client_name
    || clients.find((c) => c.id === active)?.company_name || "Client";

  return (
    <div className="p-6" data-testid="chat-page">
      <PageHeader title="Client Chat"
        description="One conversation per client — your team and your clients, in one place." />

      {/* Only present while something is selected — same as the Pipeline. */}
      {selected.size > 0 && (
        <div data-testid="chat-selection-toolbar"
          className="mt-3 flex items-center gap-3 rounded-lg border border-accent/30 bg-accent/5 px-3 py-2">
          <span className="text-sm font-medium" data-testid="chat-selection-count">{selected.size} selected</span>
          <button type="button" onClick={() => setSelected(new Set())}
            className="text-xs text-graphite hover:text-ash transition-colors">Clear</button>
          <div className="flex-1" />
          <Button data-testid="chat-delete-selected-btn" onClick={() => setConfirmOpen(true)}
            disabled={deletingSelected} size="sm" variant="outline"
            className="gap-1.5 border-danger/30 text-danger hover:bg-danger/10 hover:text-danger">
            <Trash2 className="h-3.5 w-3.5" />
            {`Delete ${selected.size}`}
          </Button>
        </div>
      )}

      <div className="grid lg:grid-cols-[320px_1fr] gap-4 mt-4 h-[70vh]">
        {/* Inbox */}
        <Card className="p-2 bg-surface-1 border-white/10 overflow-y-auto flex flex-col">
          <select value="" data-testid="chat-client-picker"
            onChange={(e) => { if (e.target.value) openThread(e.target.value); }}
            className="w-full mb-2 rounded-md bg-surface-2 border border-white/10 text-sm px-2 py-1.5">
            <option value="">＋ Start / open a client…</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.company_name}</option>)}
          </select>
          {isAdmin && threads?.length > 0 && (
            <button type="button" onClick={selectAll}
              className="self-end mb-1 pr-1 text-[10px] font-mono uppercase text-carbon hover:text-ash transition-colors"
              data-testid="chat-select-all">
              {threads.every((t) => selected.has(t.client_id)) ? "Select none" : "Select all"}
            </button>
          )}
          {!threads ? <Skeleton className="h-40 w-full" /> :
            threads.length === 0 ? (
              <p className="text-sm text-graphite p-3">No conversations yet. Pick a client above to start one.</p>
            ) : threads.map((t) => (
              <div key={t.client_id}
                className={`flex items-start gap-2 rounded-lg p-2 mb-1 transition-colors ${
                  selected.has(t.client_id) ? "bg-accent/5 border border-accent/40"
                  : active === t.client_id ? "bg-surface-2" : "hover:bg-surface-2/50 border border-transparent"
                }`}>
                {isAdmin && (
                  <span onClick={(e) => { e.stopPropagation(); toggleSelected(t.client_id); }} className="pt-0.5 shrink-0">
                    <Checkbox data-testid={`chat-thread-select-${t.client_id}`} checked={selected.has(t.client_id)} aria-label={`Select ${t.client_name}`} />
                  </span>
                )}
                <button onClick={() => openThread(t.client_id)}
                  data-testid="chat-thread"
                  className="flex-1 min-w-0 text-left">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium truncate">{t.client_name}</span>
                    {t.unread > 0 && <span className="text-[10px] bg-primary text-background rounded-full px-1.5 py-0.5">{t.unread}</span>}
                  </div>
                  <p className="text-xs text-graphite truncate mt-0.5">
                    {t.last_sender === "staff" ? "You: " : ""}{t.last_message}
                  </p>
                </button>
              </div>
            ))}
        </Card>

        {/* Conversation */}
        <Card className="flex flex-col bg-surface-1 border-white/10 overflow-hidden">
          {!active ? (
            <div className="flex-1 flex items-center justify-center text-sm text-graphite">
              <div className="text-center"><MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-40" />Select or start a conversation</div>
            </div>
          ) : (
            <>
              <div className="border-b border-white/10 px-4 py-3 font-medium truncate">{activeName}</div>
              <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3" data-testid="chat-messages">
                {messages.length === 0 && <p className="text-sm text-graphite text-center mt-8">No messages yet — say hello.</p>}
                {messages.map((m) => (
                  <div key={m.id} className={`flex ${m.sender_type === "staff" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[75%] rounded-2xl px-3 py-2 text-sm ${m.sender_type === "staff" ? "bg-primary text-background" : "bg-surface-2"}`}>
                      <div className="text-[10px] opacity-70 mb-0.5">{m.sender_name}{m.sender_type === "agent" ? " · agent" : ""}</div>
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
                ))}
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
                <Button variant="ghost" size="icon" onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="chat-attach">
                  {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
                </Button>
                <Input value={text} onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                  placeholder="Type a message…" className="bg-surface-2 border-white/10" data-testid="chat-input" />
                <Button onClick={send} disabled={sending} data-testid="chat-send">
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </div>
            </>
          )}
        </Card>
      </div>

      <Dialog open={confirmOpen} onOpenChange={(o) => !o && setConfirmOpen(false)}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="chat-delete-dialog">
          <DialogHeader>
            <DialogTitle>Delete {selected.size} conversation{selected.size === 1 ? "" : "s"}?</DialogTitle>
            <DialogDescription>
              This permanently deletes the selected conversation{selected.size === 1 ? "" : "s"} — every message, on both your side and the client portal. This can't be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" className="border-white/10" onClick={() => setConfirmOpen(false)}>Cancel</Button>
            <Button variant="destructive" disabled={deletingSelected} onClick={deleteSelected} data-testid="chat-confirm-delete-btn">
              {deletingSelected ? "Deleting…" : `Delete ${selected.size}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

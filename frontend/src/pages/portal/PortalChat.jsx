import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Send, Paperclip, Loader2, X, MessageSquare, ArrowDown, Check, CheckCheck } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

/** The client's side of the one-per-client thread.
 *
 *  Their messages on the right, the team's on the left, grouped under one
 *  header per run and ruled off when the day changes — the same conversation
 *  grammar as the circle's room, because it is the same act. What is different
 *  here is the receipt: a client who sends a file at 2am wants to know it was
 *  received, so a sent message says so and a read one says that too.
 */

const POLL_MS = 6000;
const GROUP_WINDOW_MS = 5 * 60 * 1000;

const dayOf = (iso) => (iso ? new Date(iso).toDateString() : "");

function dayLabel(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  if (d.toDateString() === new Date().toDateString()) return "Today";
  if (d.toDateString() === new Date(Date.now() - 86400000).toDateString()) return "Yesterday";
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

const timeOf = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

const initials = (name = "O") =>
  name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "O";

function grouped(messages) {
  let previous = null;
  return messages.map((m) => {
    const sameSide = previous && previous.sender_type === m.sender_type
      && previous.sender_name === m.sender_name;
    const gap = previous ? new Date(m.created_at) - new Date(previous.created_at) : Infinity;
    const sameDay = previous && dayOf(previous.created_at) === dayOf(m.created_at);
    const row = { ...m, _head: !(sameSide && sameDay && gap < GROUP_WINDOW_MS) };
    previous = m;
    return row;
  });
}

export default function PortalChat() {
  const [messages, setMessages] = useState(null);
  const [text, setText] = useState("");
  const [pending, setPending] = useState([]); // [{file_id, filename}]
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [atBottom, setAtBottom] = useState(true);
  const fileRef = useRef();
  const scrollRef = useRef();
  const endRef = useRef();
  const inputRef = useRef();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/portal/chat");
      setMessages(Array.isArray(data) ? data : []);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      setMessages((m) => m || []);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (atBottom) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, atBottom]);

  const onScroll = (e) => {
    const el = e.currentTarget;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  };

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
    const body = text.trim();
    if ((!body && pending.length === 0) || sending) return;
    setSending(true);
    const attachments = pending;
    setText("");
    setPending([]);
    try {
      await api.post("/portal/chat", {
        body, attachment_file_ids: attachments.map((p) => p.file_id),
      });
      setAtBottom(true);
      await load();
    } catch (err) {
      // Hand back exactly what was about to be sent, text and files both.
      setText(body);
      setPending(attachments);
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const rows = useMemo(() => grouped(messages || []), [messages]);

  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-6" data-testid="portal-chat">
      <header className="mb-4">
        <h1 className="font-display text-2xl font-bold tracking-tight">Messages</h1>
        <p className="mt-1 text-sm text-graphite">One thread, straight to your Obrinex team.</p>
      </header>

      <div className="obx-glass relative flex h-[calc(100dvh-16rem)] min-h-[24rem] flex-col overflow-hidden rounded-2xl md:h-[70vh]">
        {!messages ? (
          <div className="p-4"><Skeleton className="h-40 w-full bg-surface-1" /></div>
        ) : (
          <>
            <div
              ref={scrollRef}
              onScroll={onScroll}
              className="scrollbar-thin flex-1 space-y-1 overflow-y-auto px-3 py-4 sm:px-4"
            >
              {rows.length === 0 && (
                <div className="flex h-full flex-col items-center justify-center px-6 text-center">
                  <div className="obx-holo obx-glass relative flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl">
                    <MessageSquare className="relative z-10 h-5 w-5 text-primary" />
                  </div>
                  <p className="mt-4 text-sm">No messages yet.</p>
                  <p className="mt-1 max-w-xs text-xs text-graphite">
                    Anything you send here reaches the people working on your account.
                  </p>
                </div>
              )}

              {rows.map((m, i) => {
                const mine = m.sender_type === "client";
                const newDay = i === 0 || dayOf(rows[i - 1].created_at) !== dayOf(m.created_at);
                return (
                  <div key={m.id}>
                    {newDay && (
                      <div className="flex items-center gap-3 py-3">
                        <span className="h-px flex-1 bg-white/[0.08]" />
                        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-carbon">
                          {dayLabel(m.created_at)}
                        </span>
                        <span className="h-px flex-1 bg-white/[0.08]" />
                      </div>
                    )}

                    <div
                      className={`obx-message-in flex gap-2.5 ${mine ? "flex-row-reverse" : ""} ${
                        m._head ? "mt-3" : "mt-0.5"
                      }`}
                    >
                      <div className="w-8 shrink-0">
                        {m._head && !mine && (
                          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary/12 font-mono text-[11px] font-semibold text-primary ring-1 ring-primary/30">
                            {initials(m.sender_name || "Obrinex")}
                          </div>
                        )}
                      </div>

                      <div className={`min-w-0 max-w-[86%] sm:max-w-[76%] ${mine ? "text-right" : ""}`}>
                        {m._head && !mine && (
                          <div className="mb-1 flex items-baseline gap-2">
                            <span className="truncate text-xs font-medium">
                              {m.sender_name || "Obrinex team"}
                            </span>
                            <span className="obx-figure shrink-0 font-mono text-[9px] text-carbon">
                              {timeOf(m.created_at)}
                            </span>
                          </div>
                        )}

                        <div
                          className={`inline-block rounded-2xl px-3 py-2 text-left text-sm leading-relaxed ${
                            mine
                              ? "border border-primary/25 bg-primary/[0.12]"
                              : "border border-white/10 bg-white/[0.035]"
                          }`}
                        >
                          {m.body && <p className="whitespace-pre-wrap break-words">{m.body}</p>}
                          {(m.attachments || []).map((a) => (
                            <a
                              key={a.file_id}
                              href={`${api.defaults.baseURL}/files/${a.file_id}/download`}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-1.5 flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1.5 text-xs transition-colors hover:border-primary/40 hover:text-primary"
                            >
                              <Paperclip className="h-3 w-3 shrink-0" />
                              <span className="truncate">{a.filename}</span>
                            </a>
                          ))}
                        </div>

                        {mine && (
                          <p className="mt-0.5 flex items-center justify-end gap-1 font-mono text-[9px] text-carbon">
                            {timeOf(m.created_at)}
                            {m.read_by_staff ? (
                              <CheckCheck className="h-3 w-3 text-primary" />
                            ) : (
                              <Check className="h-3 w-3" />
                            )}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
              <div ref={endRef} />
            </div>

            {!atBottom && (
              <button
                onClick={() => { setAtBottom(true); endRef.current?.scrollIntoView({ behavior: "smooth" }); }}
                data-testid="portal-chat-jump"
                className="obx-glass obx-lift absolute bottom-24 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs"
              >
                <ArrowDown className="h-3 w-3" /> Latest
              </button>
            )}

            {pending.length > 0 && (
              <div className="flex flex-wrap gap-2 border-t border-white/10 px-3 py-2">
                {pending.map((p) => (
                  <span
                    key={p.file_id}
                    className="flex max-w-full items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-xs"
                  >
                    <Paperclip className="h-3 w-3 shrink-0" />
                    <span className="truncate">{p.filename}</span>
                    <button
                      onClick={() => setPending((x) => x.filter((f) => f.file_id !== p.file_id))}
                      aria-label={`Remove ${p.filename}`}
                      className="shrink-0 text-carbon hover:text-danger"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            <div className="shrink-0 border-t border-white/10 p-2.5 sm:p-3">
              <div className="obx-glass flex items-end gap-1.5 rounded-xl p-1.5 focus-within:border-primary/40">
                <input ref={fileRef} type="file" className="hidden" onChange={attach} />
                <button
                  onClick={() => fileRef.current?.click()}
                  disabled={uploading}
                  data-testid="portal-chat-attach"
                  aria-label="Attach a file"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-carbon transition-colors hover:bg-white/[0.06] hover:text-foreground disabled:opacity-50"
                >
                  {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
                </button>
                <textarea
                  ref={inputRef}
                  rows={1}
                  value={text}
                  onChange={(e) => {
                    setText(e.target.value);
                    e.target.style.height = "auto";
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
                  }}
                  placeholder="Type a message…"
                  data-testid="portal-chat-input"
                  className="max-h-[140px] flex-1 resize-none bg-transparent px-1 py-1.5 text-sm outline-none placeholder:text-carbon"
                />
                <button
                  onClick={send}
                  disabled={sending || (!text.trim() && pending.length === 0)}
                  data-testid="portal-chat-send"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-background transition-opacity disabled:opacity-30"
                >
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

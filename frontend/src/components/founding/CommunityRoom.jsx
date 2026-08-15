import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Send, Loader2, Trash2, ArrowDown, Radio } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

/** The one shared room.
 *
 *  Rebuilt from a list of identical grey boxes into a conversation: messages
 *  group under their author, the day is ruled off when it changes, and anything
 *  that arrived while you were away sits under a line that says so. Ten people
 *  in one room means the interface has to make *who and when* free to read —
 *  there are no other channels to carry that information.
 */

const POLL_MS = 8000;

/* Colour is derived from the name, so a person looks the same every time
   without anyone choosing a colour for them. Hues only — saturation and
   lightness are fixed so no member is louder than another. */
function hueOf(name = "") {
  let h = 0;
  for (let i = 0; i < name.length; i += 1) h = (h * 31 + name.charCodeAt(i)) % 360;
  return h;
}

function initials(name = "?") {
  return name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";
}

function Avatar({ name, host }) {
  const hue = hueOf(name);
  return (
    <div
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl font-mono text-[11px] font-semibold ring-1"
      style={
        host
          ? { background: "hsl(190 100% 50% / 0.14)", color: "hsl(190 100% 72%)", boxShadow: "inset 0 0 0 1px hsl(190 100% 50% / 0.4)" }
          : {
              background: `hsl(${hue} 60% 55% / 0.16)`,
              color: `hsl(${hue} 70% 78%)`,
              boxShadow: `inset 0 0 0 1px hsl(${hue} 60% 60% / 0.3)`,
            }
      }
    >
      {initials(name)}
    </div>
  );
}

const dayOf = (iso) => (iso ? new Date(iso).toDateString() : "");

function dayLabel(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const today = new Date().toDateString();
  const yesterday = new Date(Date.now() - 86400000).toDateString();
  if (d.toDateString() === today) return "Today";
  if (d.toDateString() === yesterday) return "Yesterday";
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

const timeOf = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

/** Consecutive messages from one person within five minutes become one block.
 *  Repeating a name and an avatar for every line is what made the old room read
 *  as a log rather than as people talking. */
const GROUP_WINDOW_MS = 5 * 60 * 1000;

function grouped(messages) {
  const out = [];
  let previous = null;
  messages.forEach((m) => {
    const sameAuthor = previous && previous.author_id === m.author_id;
    const gap = previous ? new Date(m.created_at) - new Date(previous.created_at) : Infinity;
    const sameDay = previous && dayOf(previous.created_at) === dayOf(m.created_at);
    out.push({ ...m, _head: !(sameAuthor && sameDay && gap < GROUP_WINDOW_MS) });
    previous = m;
  });
  return out;
}

export default function CommunityRoom({ onRead }) {
  const { user } = useAuth();
  const [messages, setMessages] = useState(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [atBottom, setAtBottom] = useState(true);
  const [firstUnreadId, setFirstUnreadId] = useState(null);
  const scrollRef = useRef(null);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const seenIds = useRef(new Set());

  const load = useCallback(async (initial = false) => {
    try {
      const { data } = await api.get("/founding/chat");
      const rows = Array.isArray(data) ? data : [];
      if (initial) {
        rows.forEach((m) => seenIds.current.add(m.id));
      } else {
        // The first message we have not rendered before is where the "new"
        // rule goes. Computed on arrival rather than from a stored timestamp,
        // so it survives a page that was left open for an hour.
        const fresh = rows.find(
          (m) => !seenIds.current.has(m.id) && m.author_id !== user?.id
        );
        if (fresh && !atBottom) setFirstUnreadId((current) => current || fresh.id);
        rows.forEach((m) => seenIds.current.add(m.id));
      }
      setMessages(rows);
    } catch {
      setMessages((m) => m || []);
    }
  }, [user?.id, atBottom]);

  // Only seeds the baseline. Marking the room read is left entirely to the
  // effect below, which fires as soon as the messages land — doing it here too
  // would post twice on every open for no extra truth.
  useEffect(() => { load(true); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const t = setInterval(() => load(false), POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  // Being at the bottom is what "I have read this" means in a chat, so the
  // server marker moves on that rather than on the tab being mounted.
  useEffect(() => {
    if (!atBottom || !messages?.length) return;
    setFirstUnreadId(null);
    api.post("/founding/chat/read").then(() => onRead?.()).catch(() => {});
  }, [atBottom, messages?.length]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (atBottom) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, atBottom]);

  const onScroll = (e) => {
    const el = e.currentTarget;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  };

  const send = async () => {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    setText("");
    try {
      await api.post("/founding/chat", { body });
      setAtBottom(true);
      await load(false);
    } catch (err) {
      // Give the text back. Losing what someone typed because a request failed
      // is the one thing a chat box must never do.
      setText(body);
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/founding/chat/${id}`);
      setMessages((rows) => rows.filter((m) => m.id !== id));
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const rows = useMemo(() => grouped(messages || []), [messages]);

  if (!messages) return <Skeleton className="h-[70vh] w-full rounded-2xl bg-surface-1" />;

  return (
    <div
      className="obx-glass relative flex h-[calc(100dvh-15rem)] min-h-[24rem] flex-col overflow-hidden rounded-2xl md:h-[70vh]"
      data-testid="founding-chat"
    >
      <div className="obx-aurora flex shrink-0 items-center gap-2 border-b border-white/10 px-4 py-2.5">
        <Radio className="relative z-10 h-3.5 w-3.5 text-primary" />
        <p className="relative z-10 font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
          The room · one channel, everyone in it
        </p>
      </div>

      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="scrollbar-thin flex-1 space-y-1 overflow-y-auto px-3 py-4 sm:px-4"
      >
        {rows.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <div className="obx-holo obx-glass relative flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl">
              <Radio className="relative z-10 h-5 w-5 text-primary" />
            </div>
            <p className="mt-4 text-sm">Nothing here yet.</p>
            <p className="mt-1 max-w-xs text-xs text-graphite">
              One room, and everyone in the circle is in it. Say something —
              somebody has to go first.
            </p>
          </div>
        )}

        {rows.map((m, i) => {
          const mine = m.author_id === user?.id;
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
              {firstUnreadId === m.id && (
                <div className="flex items-center gap-3 py-2" data-testid="founding-chat-new-line">
                  <span className="h-px flex-1 bg-primary/40" />
                  <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-primary">
                    New
                  </span>
                  <span className="h-px flex-1 bg-primary/40" />
                </div>
              )}

              <div
                className={`obx-message-in group flex gap-2.5 ${
                  mine ? "flex-row-reverse" : ""
                } ${m._head ? "mt-3" : "mt-0.5"}`}
              >
                <div className="w-8 shrink-0">
                  {m._head && <Avatar name={m.author_name} host={m.is_host} />}
                </div>

                <div className={`min-w-0 max-w-[86%] sm:max-w-[76%] ${mine ? "items-end text-right" : ""}`}>
                  {m._head && (
                    <div className={`mb-1 flex items-baseline gap-2 ${mine ? "justify-end" : ""}`}>
                      <span className="truncate text-xs font-medium">
                        {mine ? "You" : m.author_name}
                      </span>
                      {m.is_host && (
                        <span className="rounded-full border border-primary/30 bg-primary/10 px-1.5 py-px font-mono text-[9px] uppercase tracking-wider text-primary">
                          Host
                        </span>
                      )}
                      {!mine && m.author_company && (
                        <span className="truncate text-[10px] text-carbon">{m.author_company}</span>
                      )}
                      <span className="obx-figure shrink-0 font-mono text-[9px] text-carbon">
                        {timeOf(m.created_at)}
                      </span>
                    </div>
                  )}

                  <div
                    className={`inline-block whitespace-pre-line break-words rounded-2xl px-3 py-2 text-sm leading-relaxed text-left ${
                      mine
                        ? "border border-primary/25 bg-primary/[0.12]"
                        : m.is_host
                        ? "border border-white/12 bg-white/[0.055]"
                        : "border border-white/10 bg-white/[0.035]"
                    }`}
                  >
                    {m.body}
                  </div>

                  {mine && (
                    <button
                      onClick={() => remove(m.id)}
                      aria-label="Delete message"
                      className="ml-2 align-middle text-carbon opacity-0 transition-opacity hover:text-danger focus:opacity-100 group-hover:opacity-100"
                    >
                      <Trash2 className="inline h-3 w-3" />
                    </button>
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
          data-testid="founding-chat-jump"
          className="obx-glass obx-lift absolute bottom-20 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs"
        >
          <ArrowDown className="h-3 w-3" /> Latest
        </button>
      )}

      <div className="shrink-0 border-t border-white/10 p-2.5 sm:p-3">
        <div className="obx-glass flex items-end gap-2 rounded-xl p-1.5 focus-within:border-primary/40">
          <textarea
            ref={inputRef}
            rows={1}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              // Grows with the message instead of scrolling a one-line box.
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
            }}
            placeholder="Message the circle…"
            data-testid="founding-chat-input"
            className="max-h-[140px] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-carbon"
          />
          <button
            onClick={send}
            disabled={sending || !text.trim()}
            data-testid="founding-chat-send"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-background transition-opacity disabled:opacity-30"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
        <p className="mt-1.5 hidden px-1 font-mono text-[9px] uppercase tracking-[0.16em] text-carbon sm:block">
          Enter to send · Shift + Enter for a new line
        </p>
      </div>
    </div>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Loader2, Sparkles, ShieldCheck, Trash2, RefreshCw } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

/** The assistant, for a member or a client.
 *
 *  One component for both, because the difference between them is entirely
 *  server-side: `/api/me/assistant` builds a different persona and a different
 *  data snapshot from the role on the session. Forking the UI would mean two
 *  chat screens to keep in step for no difference anyone can see.
 *
 *  It knows their real account — invoices, projects, stamps, invitations — so
 *  the empty state says that plainly, and so do the suggested openers, which
 *  are generated from what is actually true of them rather than being four
 *  fixed strings.
 */

const EASE = [0.16, 1, 0.3, 1];

/** Minimal markdown: bold, inline code, and bullets. The model reaches for all
 *  three constantly, and rendering the asterisks raw is what makes an assistant
 *  look unfinished. Anything richer is a parser nobody asked for. */
function RichText({ text }) {
  const blocks = String(text).split(/\n{2,}/);
  return blocks.map((block, b) => {
    const lines = block.split("\n");
    const bulleted = lines.every((l) => /^\s*[-*•]\s+/.test(l)) && lines.length > 0;
    if (bulleted) {
      return (
        <ul key={b} className="my-1.5 space-y-1 pl-1">
          {lines.map((l, i) => (
            <li key={i} className="flex gap-2">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-primary/70" />
              <span>{inline(l.replace(/^\s*[-*•]\s+/, ""))}</span>
            </li>
          ))}
        </ul>
      );
    }
    return (
      <p key={b} className={b === 0 ? "" : "mt-2.5"}>
        {lines.map((l, i) => (
          <span key={i}>
            {i > 0 && <br />}
            {inline(l)}
          </span>
        ))}
      </p>
    );
  });
}

function inline(text) {
  const parts = String(text).split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (/^\*\*[^*]+\*\*$/.test(part)) {
      return <strong key={i} className="font-semibold text-foreground">{part.slice(2, -2)}</strong>;
    }
    if (/^`[^`]+`$/.test(part)) {
      return (
        <code key={i} className="rounded bg-white/[0.07] px-1 py-0.5 font-mono text-[0.85em] text-primary">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

export default function PortalAssistant({ audience = "client" }) {
  const [thread, setThread] = useState(null);
  const [openers, setOpeners] = useState([]);
  const [text, setText] = useState("");
  const [asking, setAsking] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  const load = useCallback(async () => {
    const { data } = await api.get("/me/assistant");
    setThread(Array.isArray(data) ? data : []);
  }, []);

  useEffect(() => {
    load().catch(() => setThread([]));
    api.get("/me/assistant/suggestions")
      .then(({ data }) => setOpeners(Array.isArray(data) ? data : []))
      .catch(() => setOpeners([]));
  }, [load]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [thread, asking]);

  const ask = async (preset) => {
    const message = String(preset ?? text).trim();
    if (!message || asking) return;
    setAsking(true);
    if (!preset) setText("");
    // On screen immediately, so the question is visible while the answer is
    // being written rather than after it.
    setThread((t) => [
      ...(t || []),
      { id: `pending-${Date.now()}`, role: "user", content: message },
    ]);
    try {
      await api.post("/me/assistant", { message });
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      setThread((t) => (t || []).filter((m) => !String(m.id).startsWith("pending-")));
      if (!preset) setText(message);
    } finally {
      setAsking(false);
      inputRef.current?.focus();
    }
  };

  const clear = async () => {
    try {
      await api.delete("/me/assistant");
      setThread([]);
      toast.success("Conversation cleared.");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  if (!thread) return <Skeleton className="h-[70vh] w-full rounded-2xl bg-surface-1" />;

  const isMember = audience === "member";

  return (
    <div
      className="obx-glass relative flex h-[calc(100dvh-15rem)] min-h-[26rem] flex-col overflow-hidden rounded-2xl md:h-[72vh]"
      data-testid="portal-assistant"
    >
      <div className="obx-aurora flex shrink-0 items-center gap-2 border-b border-white/10 px-4 py-2.5">
        <Sparkles className="relative z-10 h-3.5 w-3.5 text-primary" />
        <p className="relative z-10 font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
          {isMember ? "Your assistant · private to you" : "Obrinex assistant · knows your account"}
        </p>
        {thread.length > 0 && (
          <button
            onClick={clear}
            data-testid="portal-assistant-clear"
            title="Clear this conversation"
            className="relative z-10 ml-auto flex items-center gap-1 text-[10px] text-carbon transition-colors hover:text-danger"
          >
            <Trash2 className="h-3 w-3" /> Clear
          </button>
        )}
      </div>

      <div className="scrollbar-thin flex-1 space-y-3 overflow-y-auto px-3 py-4 sm:px-4">
        {thread.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center px-4 text-center">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5, ease: EASE }}
              className="obx-holo obx-glass relative flex h-16 w-16 items-center justify-center overflow-hidden rounded-2xl"
            >
              <Sparkles className="relative z-10 h-6 w-6 text-primary" />
            </motion.div>

            <h2 className="mt-4 font-display text-lg font-semibold tracking-tight">
              {isMember ? "Ask it anything" : "Ask about your account, or anything else"}
            </h2>
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-carbon">
              <ShieldCheck className="h-3 w-3 shrink-0" />
              {isMember
                ? "It knows your membership. It cannot see other members' details."
                : "It knows your projects, invoices and tickets. It cannot see other clients."}
            </p>

            <div className="mt-5 grid w-full max-w-md gap-2 sm:grid-cols-2">
              {openers.map((o, i) => (
                <motion.button
                  key={o}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 + i * 0.06, ease: EASE }}
                  onClick={() => ask(o)}
                  data-testid={`portal-assistant-opener-${i}`}
                  className="obx-glass obx-lift obx-sheen rounded-xl px-3 py-2.5 text-left text-xs leading-snug text-ash"
                >
                  {o}
                </motion.button>
              ))}
            </div>
          </div>
        )}

        <AnimatePresence initial={false}>
          {thread.map((m) => (
            <motion.div
              key={m.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: EASE }}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[90%] break-words rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed sm:max-w-[80%] ${
                  m.role === "user"
                    ? "border border-primary/25 bg-primary/[0.12]"
                    : "obx-glass"
                }`}
              >
                {m.role === "user" ? (
                  <p className="whitespace-pre-line">{m.content}</p>
                ) : (
                  <RichText text={m.content} />
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {asking && (
          <div className="flex justify-start">
            <div className="obx-glass obx-typing rounded-2xl px-4 py-3 text-primary">
              <span /><span /><span />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {thread.length > 0 && openers.length > 0 && !asking && (
        <div className="scrollbar-thin flex shrink-0 gap-2 overflow-x-auto border-t border-white/[0.07] px-3 py-2">
          <RefreshCw className="mt-1.5 h-3 w-3 shrink-0 text-carbon" />
          {openers.map((o) => (
            <button
              key={o}
              onClick={() => ask(o)}
              className="shrink-0 rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-graphite transition-colors hover:border-primary/40 hover:text-primary"
            >
              {o}
            </button>
          ))}
        </div>
      )}

      <div className="shrink-0 border-t border-white/10 p-2.5 sm:p-3">
        <div className="obx-glass flex items-end gap-2 rounded-xl p-1.5 focus-within:border-primary/40">
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
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); }
            }}
            placeholder={isMember ? "Ask your assistant…" : "Ask about your account…"}
            data-testid="portal-assistant-input"
            className="max-h-[140px] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-carbon"
          />
          <button
            onClick={() => ask()}
            disabled={asking || !text.trim()}
            data-testid="portal-assistant-send"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-background transition-opacity disabled:opacity-30"
          >
            {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}

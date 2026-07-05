import { useState, useRef, useEffect } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Sparkles, Send, Loader2, Bot, User as UserIcon } from "lucide-react";
import { API } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

const SUGGESTIONS = [
  "Summarize this week's pipeline activity",
  "Which deals are most likely to close?",
  "Draft a follow-up email for a stalled lead",
  "What's our current outstanding revenue?",
];

export default function AIAssistant({ open, onOpenChange }) {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = async (text) => {
    const msg = text ?? input;
    if (!msg.trim() || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: msg }, { role: "assistant", content: "" }]);
    setLoading(true);
    try {
      const res = await fetch(`${API}/ai/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ message: msg, session_id: "default" }),
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = JSON.parse(line.slice(6));
          if (payload.delta) {
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = { role: "assistant", content: next[next.length - 1].content + payload.delta };
              return next;
            });
          }
        }
      }
    } catch (e) {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: "assistant", content: "Sorry, I ran into an error. Please try again." };
        return next;
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid="ai-assistant-panel" className="w-full sm:max-w-md flex flex-col p-0 bg-surface-1 border-white/10">
        <SheetHeader className="p-4 border-b border-white/10">
          <SheetTitle className="flex items-center gap-2 font-display">
            <Sparkles className="h-4 w-4" /> AI Assistant
          </SheetTitle>
        </SheetHeader>

        <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-4" data-testid="ai-assistant-messages">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-2 border border-white/10">
                <Bot className="h-5 w-5 text-graphite" />
              </div>
              <p className="text-sm text-graphite max-w-xs">
                Ask me to summarize meetings, draft emails, write proposals, analyze sales, or answer questions about your agency data.
              </p>
              <div className="grid gap-2 w-full">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    data-testid={`ai-suggestion-${s.slice(0, 10).replace(/\s+/g, "-").toLowerCase()}`}
                    onClick={() => send(s)}
                    className="rounded-lg border border-white/10 bg-surface-2 px-3 py-2 text-left text-xs text-ash hover:border-white/20 hover:text-foreground transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex gap-2 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              {m.role === "assistant" && (
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-2 border border-white/10">
                  <Bot className="h-3.5 w-3.5" />
                </div>
              )}
              <div
                data-testid={`ai-message-${m.role}`}
                className={`max-w-[80%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap ${
                  m.role === "user" ? "bg-foreground text-background" : "bg-surface-2 text-foreground border border-white/10"
                }`}
              >
                {m.content || (loading && i === messages.length - 1 ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "")}
              </div>
            </div>
          ))}
        </div>

        <div className="border-t border-white/10 p-3">
          <div className="flex items-end gap-2">
            <Textarea
              data-testid="ai-assistant-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder="Ask AgencyOS AI..."
              className="min-h-[40px] max-h-32 resize-none bg-surface-2 border-white/10"
            />
            <Button data-testid="ai-assistant-send-btn" size="icon" onClick={() => send()} disabled={loading}>
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

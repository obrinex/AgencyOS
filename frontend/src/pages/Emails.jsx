import { useEffect, useState } from "react";
import { Mail, Sparkles, Send, Loader2, ChevronDown, History } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { format } from "date-fns";
import { toast } from "sonner";

export default function Emails() {
  const [history, setHistory] = useState(null);
  const [recipients, setRecipients] = useState([]);
  const [instruction, setInstruction] = useState("");
  const [tone, setTone] = useState("professional");
  const [to, setTo] = useState("");
  const [toName, setToName] = useState("");
  const [draft, setDraft] = useState(null); // {subject, body}
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);
  const [expanded, setExpanded] = useState(null);

  const load = async () => {
    const [h, r] = await Promise.all([api.get("/emails"), api.get("/emails/recipients")]);
    setHistory(h.data);
    setRecipients(r.data);
  };

  useEffect(() => { load(); }, []);

  const generateDraft = async () => {
    if (!instruction.trim()) { toast.error("Tell the AI what the email should say"); return; }
    setDrafting(true);
    try {
      const { data } = await api.post("/emails/draft", {
        instruction, tone,
        recipient_name: toName || null,
      });
      setDraft(data);
      toast.success("Draft ready — review and edit before sending");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setDrafting(false);
    }
  };

  const sendEmail = async () => {
    if (!to) { toast.error("Choose or enter a recipient email"); return; }
    setSending(true);
    try {
      await api.post("/emails/send", { to, subject: draft.subject, body: draft.body, recipient_name: toName || null });
      toast.success(`Email sent to ${to}`);
      setDraft(null);
      setInstruction("");
      setTo("");
      setToName("");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSending(false);
    }
  };

  const pickRecipient = (email) => {
    setTo(email);
    const r = recipients.find((x) => x.email === email);
    setToName(r?.name || "");
  };

  if (!history) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6 space-y-5" data-testid="emails-page">
      <PageHeader title="Emails" description="Tell the AI what to say — it drafts, you approve, it sends" />

      <div className="grid lg:grid-cols-[1fr_360px] gap-5">
        <div className="space-y-4">
          <Card className="p-5 bg-surface-1 border-white/10 space-y-4" data-testid="compose-card">
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" /> 1 · What should this email say?</p>
            <Textarea
              data-testid="email-instruction"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              rows={4}
              placeholder={'e.g. "Tell Ravi from ShopNow that the chatbot is live, thank him for his patience, and ask for a review call this week"'}
              className="bg-surface-2 border-white/10"
            />
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1 w-40">
                <Label>Tone</Label>
                <Select value={tone} onValueChange={setTone}>
                  <SelectTrigger data-testid="email-tone" className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["professional", "friendly", "formal", "apologetic", "persuasive", "urgent"].map((t) => <SelectItem key={t} value={t}>{t[0].toUpperCase() + t.slice(1)}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <Button data-testid="generate-draft-btn" onClick={generateDraft} disabled={drafting} className="gap-1.5">
                {drafting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                {drafting ? "Drafting…" : draft ? "Regenerate Draft" : "Draft with AI"}
              </Button>
            </div>
          </Card>

          {draft && (
            <Card className="p-5 bg-surface-1 border-white/10 space-y-4" data-testid="draft-card">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">2 · Review, edit & approve</p>
              <div className="grid sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>To (client email) *</Label>
                  {recipients.length > 0 ? (
                    <Select value={to} onValueChange={pickRecipient}>
                      <SelectTrigger data-testid="email-to-select" className="bg-surface-2 border-white/10"><SelectValue placeholder="Pick a client / contact / lead" /></SelectTrigger>
                      <SelectContent>
                        {recipients.map((r) => <SelectItem key={r.email} value={r.email}>{r.name ? `${r.name} · ` : ""}{r.email}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  ) : null}
                  <Input data-testid="email-to-input" type="email" value={to} onChange={(e) => setTo(e.target.value)} placeholder="or type an email address" className="bg-surface-2 border-white/10 mt-1" />
                </div>
                <div className="space-y-1"><Label>Subject</Label><Input data-testid="email-subject" value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              </div>
              <div className="space-y-1">
                <Label>Body (fully editable)</Label>
                <Textarea data-testid="email-body" value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} rows={12} className="bg-surface-2 border-white/10" />
              </div>
              <div className="flex items-center justify-between">
                <p className="text-xs text-graphite">Nothing is sent until you click Send.</p>
                <Button data-testid="send-email-btn" onClick={sendEmail} disabled={sending} className="gap-1.5">
                  {sending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                  {sending ? "Sending…" : "Approve & Send"}
                </Button>
              </div>
            </Card>
          )}
        </div>

        <Card className="p-4 bg-surface-1 border-white/10 h-fit" data-testid="email-history">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite mb-3 flex items-center gap-1.5"><History className="h-3.5 w-3.5" /> Sent Emails</p>
          {history.length === 0 ? (
            <p className="text-xs text-graphite py-6 text-center">Nothing sent yet</p>
          ) : (
            <div className="space-y-1.5 max-h-[70vh] overflow-y-auto pr-1">
              {history.map((m) => (
                <button key={m.id} onClick={() => setExpanded(expanded === m.id ? null : m.id)}
                        className="w-full text-left rounded-lg bg-surface-2 border border-white/5 hover:border-white/20 p-3 transition-colors">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium truncate">{m.subject}</p>
                    <ChevronDown className={`h-3.5 w-3.5 text-graphite shrink-0 transition-transform ${expanded === m.id ? "rotate-180" : ""}`} />
                  </div>
                  <p className="text-xs text-graphite font-mono mt-0.5">to {m.to} · {format(new Date(m.created_at), "MMM d, h:mm a")}</p>
                  {expanded === m.id && <p className="text-xs text-ash whitespace-pre-line mt-2 border-t border-white/10 pt-2">{m.body}</p>}
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

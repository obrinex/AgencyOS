import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Sparkles, Save, Loader2, Copy, Send, CheckCircle2, XCircle } from "lucide-react";
import api from "@/lib/api";
import { API } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatApiError } from "@/lib/api";
import { toast } from "sonner";

const STATUSES = ["draft", "sent", "viewed", "accepted", "rejected"];

export default function ProposalDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [proposal, setProposal] = useState(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [scope, setScope] = useState("");
  const [shareEmail, setShareEmail] = useState("");
  const [sharing, setSharing] = useState(false);

  const load = async () => {
    const { data } = await api.get(`/proposals/${id}`);
    setProposal(data);
    setTitle(data.title);
    setContent(data.content);
  };

  useEffect(() => { load(); }, [id]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/proposals/${id}`, { title, content });
      toast.success("Proposal saved");
      load();
    } finally {
      setSaving(false);
    }
  };

  const changeStatus = async (status) => {
    await api.put(`/proposals/${id}`, { status });
    load();
  };

  const shareLink = proposal ? `${window.location.origin}/proposal/${proposal.share_token}` : "";

  const copyLink = () => {
    navigator.clipboard.writeText(shareLink);
    toast.success("Share link copied");
  };

  const shareViaEmail = async () => {
    if (!shareEmail.trim()) { toast.error("Enter a recipient email"); return; }
    setSharing(true);
    try {
      await api.post(`/proposals/${id}/share-email`, { email: shareEmail });
      toast.success("Proposal emailed to client");
      setShareEmail("");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSharing(false);
    }
  };

  const generateWithAI = async () => {
    if (!scope.trim()) { toast.error("Describe the scope of work first"); return; }
    setGenerating(true);
    setContent("");
    try {
      const res = await fetch(`${API}/ai/generate-proposal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ client_or_lead_name: title, scope }),
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
          if (payload.delta) setContent((prev) => prev + payload.delta);
        }
      }
    } finally {
      setGenerating(false);
    }
  };

  if (!proposal) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-4" data-testid="proposal-detail-page">
      <button onClick={() => navigate("/proposals")} className="flex items-center gap-1.5 text-sm text-graphite hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Proposals
      </button>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Input data-testid="proposal-title-input" value={title} onChange={(e) => setTitle(e.target.value)} className="text-lg font-display font-bold bg-surface-1 border-white/10 max-w-md" />
        <div className="flex items-center gap-2">
          <Select value={proposal.status} onValueChange={changeStatus}>
            <SelectTrigger data-testid="proposal-status-select" className="w-36 bg-surface-1 border-white/10"><SelectValue /></SelectTrigger>
            <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
          </Select>
          <Button data-testid="save-proposal-btn" size="sm" onClick={save} disabled={saving} className="gap-1.5">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Save
          </Button>
        </div>
      </div>

      <div className="rounded-xl border border-white/10 bg-surface-1 p-4 space-y-2">
        <p className="font-mono text-[10px] uppercase text-graphite">AI Generate</p>
        <div className="flex gap-2">
          <Input data-testid="proposal-ai-scope-input" placeholder="Describe scope of work, e.g. AI voice agent + CRM automation" value={scope} onChange={(e) => setScope(e.target.value)} className="bg-surface-2 border-white/10" />
          <Button data-testid="generate-proposal-ai-btn" onClick={generateWithAI} disabled={generating} variant="outline" className="border-white/10 gap-1.5 shrink-0">
            {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Generate
          </Button>
        </div>
      </div>

      <div className="rounded-xl border border-white/10 bg-surface-1 p-4 space-y-3">
        <p className="font-mono text-[10px] uppercase text-graphite">Share & E-Signature</p>
        {proposal.status === "accepted" || proposal.status === "rejected" ? (
          <p className={`flex items-center gap-1.5 text-sm ${proposal.status === "accepted" ? "text-success" : "text-danger"}`} data-testid="proposal-signature-status">
            {proposal.status === "accepted" ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
            {proposal.status === "accepted" ? "Accepted" : "Rejected"} by {proposal.signature_name} ({proposal.signer_email})
          </p>
        ) : (
          <>
            <div className="flex gap-2">
              <Input readOnly value={shareLink} data-testid="proposal-share-link" className="bg-surface-2 border-white/10 font-mono text-xs" />
              <Button size="icon" variant="outline" className="border-white/10 shrink-0" onClick={copyLink} data-testid="proposal-copy-link-btn"><Copy className="h-3.5 w-3.5" /></Button>
            </div>
            <div className="flex gap-2">
              <Input placeholder="client@company.com" value={shareEmail} onChange={(e) => setShareEmail(e.target.value)} data-testid="proposal-share-email-input" className="bg-surface-2 border-white/10" />
              <Button onClick={shareViaEmail} disabled={sharing} className="gap-1.5 shrink-0" data-testid="proposal-share-email-btn">
                {sharing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Send
              </Button>
            </div>
          </>
        )}
      </div>

      <Textarea
        data-testid="proposal-content-textarea"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        className="min-h-[420px] bg-surface-1 border-white/10 font-mono text-sm leading-relaxed"
      />
    </div>
  );
}

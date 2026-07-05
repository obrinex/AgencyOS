import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2, FileText } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

export default function PublicProposal() {
  const { token } = useParams();
  const [proposal, setProposal] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get(`/public/proposals/${token}`);
      setProposal(data);
    } catch (e) {
      setNotFound(true);
    }
  };

  useEffect(() => { load(); }, [token]);

  const respond = async (accept) => {
    if (!name.trim() || !email.trim()) { toast.error("Enter your full name and email to sign"); return; }
    setSubmitting(true);
    try {
      const { data } = await api.post(`/public/proposals/${token}/sign`, { signature_name: name, signer_email: email, accept });
      setProposal(data);
      toast.success(accept ? "Proposal accepted!" : "Proposal declined");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSubmitting(false);
    }
  };

  if (notFound) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center text-center px-4" data-testid="public-proposal-not-found">
        <p className="text-graphite">This proposal link is invalid or has expired.</p>
      </div>
    );
  }

  if (!proposal) {
    return <div className="min-h-screen bg-background flex items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-graphite" /></div>;
  }

  const finalized = proposal.status === "accepted" || proposal.status === "rejected";

  return (
    <div className="min-h-screen bg-background py-10 px-4" data-testid="public-proposal-page">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-2 mb-6">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-foreground text-background font-display font-bold text-sm">O</div>
          <span className="font-mono text-xs text-graphite tracking-widest">AGENCYOS &middot; OBRINEX</span>
        </div>

        <div className="rounded-2xl border border-white/10 bg-surface-1 p-8">
          <div className="flex items-center gap-2 mb-4">
            <FileText className="h-5 w-5 text-graphite" />
            <h1 className="font-display text-2xl font-bold">{proposal.title}</h1>
          </div>
          <pre className="whitespace-pre-wrap font-sans text-sm text-ash leading-relaxed" data-testid="public-proposal-content">{proposal.content}</pre>

          <div className="mt-8 pt-6 border-t border-white/10">
            {finalized ? (
              <p className={`flex items-center gap-2 text-sm font-medium ${proposal.status === "accepted" ? "text-success" : "text-danger"}`} data-testid="public-proposal-final-status">
                {proposal.status === "accepted" ? <CheckCircle2 className="h-5 w-5" /> : <XCircle className="h-5 w-5" />}
                {proposal.status === "accepted" ? "Accepted" : "Declined"} by {proposal.signature_name} on {new Date(proposal.signed_at).toLocaleDateString()}
              </p>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-graphite">Review this proposal, then type your name and email to electronically sign and respond.</p>
                <div className="grid sm:grid-cols-2 gap-3">
                  <div className="space-y-1"><Label>Full Name</Label><Input data-testid="public-signature-name" value={name} onChange={(e) => setName(e.target.value)} className="bg-surface-2 border-white/10 font-display italic" /></div>
                  <div className="space-y-1"><Label>Email</Label><Input data-testid="public-signature-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="bg-surface-2 border-white/10" /></div>
                </div>
                <div className="flex gap-2 pt-1">
                  <Button data-testid="public-proposal-accept-btn" onClick={() => respond(true)} disabled={submitting} className="gap-1.5"><CheckCircle2 className="h-4 w-4" /> Accept Proposal</Button>
                  <Button data-testid="public-proposal-reject-btn" onClick={() => respond(false)} disabled={submitting} variant="outline" className="border-white/10 gap-1.5"><XCircle className="h-4 w-4" /> Decline</Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

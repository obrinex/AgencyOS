import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { FileSignature, FileDown, CheckCircle2, PenLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { format } from "date-fns";
import { formatApiError } from "@/lib/api";

const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api` });

export default function PublicAgreement() {
  const { token } = useParams();
  const [agreement, setAgreement] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [form, setForm] = useState({ signature_name: "", signer_email: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/public/agreements/${token}`)
      .then((r) => setAgreement(r.data))
      .catch(() => setNotFound(true));
  }, [token]);

  const sign = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const { data } = await api.post(`/public/agreements/${token}/sign`, { ...form, accept: true });
      setAgreement({ ...agreement, ...data });
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
    } finally {
      setSubmitting(false);
    }
  };

  const downloadPdf = () => {
    window.open(`${process.env.REACT_APP_BACKEND_URL || ""}/api/public/agreements/${token}/pdf`, "_blank");
  };

  if (notFound) {
    return <div className="min-h-screen bg-background flex items-center justify-center p-6"><p className="text-graphite">This agreement doesn't exist or the link has expired.</p></div>;
  }
  if (!agreement) {
    return <div className="min-h-screen bg-background flex items-center justify-center"><p className="text-graphite font-mono text-sm">Loading…</p></div>;
  }

  const signed = agreement.status === "signed";
  const symbol = agreement.currency || "INR";

  return (
    <div className="min-h-screen bg-background text-foreground p-6 flex justify-center" data-testid="public-agreement-page">
      <div className="max-w-2xl w-full">
        <div className="text-center mb-8 mt-6">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-foreground text-background">
            <FileSignature className="h-5 w-5" />
          </div>
          <h1 className="font-display text-2xl font-bold">{agreement.title}</h1>
          <p className="text-sm text-graphite mt-1">Service Agreement · {agreement.agency_name} × {agreement.client_name}</p>
        </div>

        <Card className="p-6 bg-surface-1 border-white/10 space-y-5">
          <div className="grid sm:grid-cols-2 gap-4 text-sm">
            <div><p className="font-mono text-[10px] uppercase text-graphite mb-1">Service Provider</p><p>{agreement.agency_name}</p></div>
            <div><p className="font-mono text-[10px] uppercase text-graphite mb-1">Client</p><p>{agreement.client_name}</p></div>
            {agreement.start_date && <div><p className="font-mono text-[10px] uppercase text-graphite mb-1">Start Date</p><p>{format(new Date(agreement.start_date), "MMM d, yyyy")}</p></div>}
            {agreement.amount != null && <div><p className="font-mono text-[10px] uppercase text-graphite mb-1">Contract Value</p><p className="font-mono font-semibold">{symbol}{Number(agreement.amount).toLocaleString()}</p></div>}
          </div>

          {agreement.scope && (
            <div>
              <p className="font-mono text-[10px] uppercase text-graphite mb-1.5">Scope of Work</p>
              <div className="text-sm text-ash whitespace-pre-line rounded-lg bg-surface-2 border border-white/10 p-4">{agreement.scope}</div>
            </div>
          )}
          {agreement.payment_terms && (
            <div>
              <p className="font-mono text-[10px] uppercase text-graphite mb-1.5">Payment Terms</p>
              <p className="text-sm text-ash">{agreement.payment_terms}</p>
            </div>
          )}
          <p className="text-xs text-graphite">The full agreement — including confidentiality, intellectual property, termination, liability, and governing-law clauses — is in the PDF below. By signing you accept all its terms.</p>

          <Button variant="outline" className="gap-1.5 border-white/10 w-full" onClick={downloadPdf} data-testid="public-agreement-pdf-btn">
            <FileDown className="h-4 w-4" /> View Full Agreement (PDF)
          </Button>

          {signed ? (
            <div className="rounded-lg bg-success/10 border border-success/30 p-4 text-center" data-testid="agreement-signed-state">
              <CheckCircle2 className="h-6 w-6 text-success mx-auto mb-2" />
              <p className="text-sm font-medium text-success">Signed by {agreement.signature_name}</p>
              {agreement.signed_at && <p className="text-xs text-graphite mt-1">{format(new Date(agreement.signed_at), "MMMM d, yyyy 'at' h:mm a")}</p>}
            </div>
          ) : (
            <form onSubmit={sign} className="space-y-3 border-t border-white/10 pt-5">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">Sign this agreement</p>
              <div className="grid sm:grid-cols-2 gap-3">
                <div className="space-y-1"><Label>Full Legal Name *</Label><Input data-testid="agreement-sign-name" required value={form.signature_name} onChange={(e) => setForm({ ...form, signature_name: e.target.value })} className="bg-surface-2 border-white/10 font-display italic" /></div>
                <div className="space-y-1"><Label>Email *</Label><Input data-testid="agreement-sign-email" type="email" required value={form.signer_email} onChange={(e) => setForm({ ...form, signer_email: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              </div>
              {error && <p className="text-xs text-danger">{error}</p>}
              <Button type="submit" disabled={submitting} className="w-full gap-1.5" data-testid="agreement-sign-submit">
                <PenLine className="h-4 w-4" /> {submitting ? "Signing…" : "Accept & Sign Agreement"}
              </Button>
              <p className="text-[11px] text-graphite text-center">Typing your name above constitutes a legally binding electronic signature.</p>
            </form>
          )}
        </Card>

        <p className="text-center font-mono text-[10px] text-carbon mt-6 tracking-widest uppercase">Powered by {agreement.agency_name}</p>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Send, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { formatApiError } from "@/lib/api";

const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api` });
const emptyForm = { name: "", email: "", company: "", phone: "", budget: "", message: "" };

export default function LeadCapture() {
  const { slug } = useParams();
  const [info, setInfo] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/public/leadform/${slug}`)
      .then((r) => setInfo(r.data))
      .catch(() => setNotFound(true));
  }, [slug]);

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api.post(`/public/leadform/${slug}`, {
        ...form,
        budget: form.budget ? parseFloat(form.budget) : null,
      });
      setDone(true);
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
    } finally {
      setSubmitting(false);
    }
  };

  if (notFound) {
    return <div className="min-h-screen bg-background flex items-center justify-center p-6"><p className="text-graphite">This form doesn't exist or has been disabled.</p></div>;
  }
  if (!info) {
    return <div className="min-h-screen bg-background flex items-center justify-center"><p className="text-graphite font-mono text-sm">Loading…</p></div>;
  }

  if (done) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6" data-testid="leadform-done">
        <Card className="max-w-md w-full p-8 bg-surface-1 border-white/10 text-center">
          <CheckCircle2 className="h-12 w-12 text-success mx-auto mb-4" />
          <h1 className="font-display text-xl font-bold mb-2">Thanks, {form.name.split(" ")[0]}!</h1>
          <p className="text-sm text-ash">Your inquiry has reached the {info.company_name} team. We'll get back to you within 24 hours.</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground p-6 flex justify-center" data-testid="leadform-page">
      <div className="max-w-lg w-full">
        <div className="text-center mb-8 mt-6">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-foreground text-background font-display font-bold">
            {(info.company_name || "O")[0]}
          </div>
          <h1 className="font-display text-2xl font-bold">{info.title}</h1>
          {info.description && <p className="text-sm text-ash mt-2 max-w-md mx-auto">{info.description}</p>}
        </div>

        <Card className="p-6 bg-surface-1 border-white/10">
          <form onSubmit={submit} className="space-y-3">
            <div className="grid sm:grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Your Name *</Label><Input data-testid="leadform-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Email *</Label><Input data-testid="leadform-email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            </div>
            <div className="grid sm:grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Company *</Label><Input data-testid="leadform-company" required value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Phone</Label><Input data-testid="leadform-phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            </div>
            <div className="space-y-1"><Label>Approximate Budget (₹)</Label><Input data-testid="leadform-budget" type="number" min="0" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1"><Label>Tell us about your project</Label><Textarea data-testid="leadform-message" rows={4} value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            {error && <p className="text-xs text-danger">{error}</p>}
            <Button data-testid="leadform-submit" type="submit" disabled={submitting} className="w-full gap-1.5">
              <Send className="h-4 w-4" /> {submitting ? "Sending…" : "Send Inquiry"}
            </Button>
          </form>
        </Card>

        <p className="text-center font-mono text-[10px] text-carbon mt-6 tracking-widest uppercase">Powered by {info.company_name}</p>
      </div>
    </div>
  );
}

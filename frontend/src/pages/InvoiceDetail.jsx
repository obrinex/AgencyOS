import { useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Send, CreditCard, Loader2 } from "lucide-react";
import api from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { INVOICE_STATUS_CONFIG } from "@/lib/statusConfig";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/contexts/AuthContext";
import { format } from "date-fns";
import { toast } from "sonner";

export default function InvoiceDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [invoice, setInvoice] = useState(null);
  const [params] = useSearchParams();
  const [paying, setPaying] = useState(false);
  const [polling, setPolling] = useState(false);

  const load = async () => {
    const { data } = await api.get(`/invoices/${id}`);
    setInvoice(data);
  };

  useEffect(() => { load(); }, [id]);

  useEffect(() => {
    const sessionId = params.get("session_id");
    if (sessionId) pollStatus(sessionId);
  }, [params]);

  const pollStatus = async (sessionId, attempts = 0) => {
    if (attempts >= 5) {
      toast.error("Payment status check timed out.");
      setPolling(false);
      return;
    }
    setPolling(true);
    try {
      const { data } = await api.get(`/invoices/checkout/status/${sessionId}`);
      if (data.payment_status === "paid") {
        toast.success("Payment successful!");
        setPolling(false);
        load();
        return;
      } else if (data.status === "expired") {
        toast.error("Payment session expired.");
        setPolling(false);
        return;
      }
      setTimeout(() => pollStatus(sessionId, attempts + 1), 2000);
    } catch (e) {
      setPolling(false);
    }
  };

  const payNow = async () => {
    setPaying(true);
    try {
      const { data } = await api.post(`/invoices/${id}/checkout`, {}, { headers: { Origin: window.location.origin } });
      window.location.href = data.url;
    } catch (e) {
      toast.error("Failed to start checkout");
      setPaying(false);
    }
  };

  const sendInvoice = async () => {
    await api.post(`/invoices/${id}/send`);
    toast.success("Invoice sent to client");
    load();
  };

  if (!invoice) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-5" data-testid="invoice-detail-page">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-sm text-graphite hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back
      </button>

      <Card className="p-6 bg-surface-1 border-white/10">
        <div className="flex items-start justify-between mb-6">
          <div>
            <p className="font-mono text-lg font-bold">{invoice.invoice_number}</p>
            <p className="text-xs text-graphite mt-1">Issued {format(new Date(invoice.issue_date), "MMM d, yyyy")}</p>
            <p className="text-xs text-graphite">Due {format(new Date(invoice.due_date), "MMM d, yyyy")}</p>
          </div>
          <StatusBadge config={INVOICE_STATUS_CONFIG} value={invoice.status} testId="invoice-status-badge" />
        </div>

        {invoice.client && (
          <div className="mb-6 pb-6 border-b border-white/10">
            <p className="font-mono text-[10px] uppercase text-graphite mb-1">Billed To</p>
            <p className="font-medium">{invoice.client.company_name}</p>
          </div>
        )}

        <div className="space-y-2 mb-6">
          {invoice.line_items.map((li, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <span>{li.description} <span className="text-graphite">× {li.quantity}</span></span>
              <span className="font-mono">${(li.quantity * li.price).toLocaleString()}</span>
            </div>
          ))}
        </div>

        <div className="space-y-1.5 pt-4 border-t border-white/10">
          <div className="flex justify-between text-sm text-graphite"><span>Subtotal</span><span className="font-mono">${invoice.subtotal.toLocaleString()}</span></div>
          <div className="flex justify-between text-sm text-graphite"><span>Tax</span><span className="font-mono">${(invoice.tax || 0).toLocaleString()}</span></div>
          <div className="flex justify-between text-lg font-bold pt-1"><span>Total</span><span className="font-mono">${invoice.total.toLocaleString()}</span></div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {user.role !== "client" && invoice.status === "draft" && (
            <Button data-testid="send-invoice-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={sendInvoice}><Send className="h-3.5 w-3.5" /> Send to Client</Button>
          )}
          {invoice.status !== "paid" && invoice.status !== "cancelled" && (
            <Button data-testid="pay-invoice-btn" size="sm" className="gap-1.5" onClick={payNow} disabled={paying || polling}>
              {paying || polling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CreditCard className="h-3.5 w-3.5" />}
              {polling ? "Confirming payment..." : "Pay Now"}
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}

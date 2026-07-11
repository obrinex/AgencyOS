import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Send, CreditCard, Loader2, FileDown, Link2, CheckCircle2, CircleDashed, CircleX } from "lucide-react";
import api, { downloadFile } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { INVOICE_STATUS_CONFIG } from "@/lib/statusConfig";
import { formatMoney } from "@/lib/currency";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/contexts/AuthContext";
import { format } from "date-fns";
import { toast } from "sonner";

export default function InvoiceDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [invoice, setInvoice] = useState(null);
  const [paying, setPaying] = useState(false);
  const [sending, setSending] = useState(false);
  const [showLinkInput, setShowLinkInput] = useState(false);
  const [paymentLink, setPaymentLink] = useState("");
  const [recordingStatus, setRecordingStatus] = useState("");

  const load = async () => {
    const { data } = await api.get(`/invoices/${id}`);
    setInvoice(data);
  };

  useEffect(() => { load(); }, [id]);

  // Client: if admin set a payment link → open it directly; otherwise silently notify admin
  const requestPayment = async () => {
    if (invoice.payment_link) {
      window.open(invoice.payment_link, "_blank", "noopener,noreferrer");
      return;
    }
    setPaying(true);
    try {
      await api.post(`/invoices/${id}/request-payment`, {});
      toast.success("Request sent. You will receive a payment link in your inbox. Please check your spam folder if needed.");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to send request");
    } finally {
      setPaying(false);
    }
  };

  // Admin: send a custom payment link to client's email
  const sendPaymentLink = async () => {
    if (!paymentLink.trim()) {
      toast.error("Please enter a payment link first");
      return;
    }
    setSending(true);
    try {
      await api.post(`/invoices/${id}/send-payment-link`, { payment_link: paymentLink.trim() });
      toast.success("Payment link sent successfully!");
      setShowLinkInput(false);
      setPaymentLink("");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to send payment link");
    } finally {
      setSending(false);
    }
  };

  const sendInvoice = async () => {
    try {
      await api.post(`/invoices/${id}/send`);
      toast.success("Invoice sent to client.");
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to send invoice");
    }
  };

  const downloadPdf = async () => {
    try {
      await downloadFile(`/invoices/${id}/pdf`, `${invoice.invoice_number}.pdf`);
    } catch (e) {
      toast.error("Failed to download PDF");
    }
  };

  const recordPaymentStatus = async (status) => {
    setRecordingStatus(status);
    try {
      await api.post(`/invoices/${id}/payment-status`, { status });
      toast.success(`Payment recorded as ${status === "failed" ? "failed / loss" : status}`);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to record payment status");
    } finally {
      setRecordingStatus("");
    }
  };

  if (!invoice) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  const canAct = invoice.status !== "paid" && invoice.status !== "cancelled";

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
            {invoice.currency && invoice.currency !== "INR" && (
              <p className="text-xs font-mono text-graphite mt-1">
                Currency: {invoice.currency} · Rate: 1 {invoice.currency} = INR {invoice.conversion_rate}
              </p>
            )}
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
              <span className="font-mono">{formatMoney(li.quantity * li.price, invoice.currency)}</span>
            </div>
          ))}
        </div>

        <div className="space-y-1.5 pt-4 border-t border-white/10">
          <div className="flex justify-between text-sm text-graphite">
            <span>Subtotal</span><span className="font-mono">{formatMoney(invoice.subtotal, invoice.currency)}</span>
          </div>
          <div className="flex justify-between text-sm text-graphite">
            <span>Tax</span><span className="font-mono">{formatMoney(invoice.tax || 0, invoice.currency)}</span>
          </div>
          <div className="flex justify-between text-lg font-bold pt-1">
            <span>Total</span><span className="font-mono">{formatMoney(invoice.total, invoice.currency)}</span>
          </div>
        </div>

        {/* Action buttons */}
        <div className="mt-6 flex flex-wrap gap-2">
          <Button data-testid="download-invoice-pdf-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={downloadPdf}>
            <FileDown className="h-3.5 w-3.5" /> Download PDF
          </Button>

          {/* Admin actions */}
          {user.role !== "client" && canAct && (
            <>
              <Button data-testid="send-invoice-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={sendInvoice}>
                <Send className="h-3.5 w-3.5" /> Send Invoice
              </Button>
              <Button
                data-testid="send-payment-link-btn"
                size="sm"
                variant="outline"
                className="gap-1.5 border-white/10"
                onClick={() => setShowLinkInput(!showLinkInput)}
              >
                <Link2 className="h-3.5 w-3.5" />
                {showLinkInput ? "Cancel" : "Send Payment Link"}
              </Button>
            </>
          )}

          {user.role !== "client" && (
            <>
              <Button data-testid="mark-invoice-paid-btn" size="sm" variant="outline" className="gap-1.5 border-success/40 text-success hover:text-success" onClick={() => recordPaymentStatus("paid")} disabled={Boolean(recordingStatus)}>
                {recordingStatus === "paid" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />} Mark as Paid
              </Button>
              <Button data-testid="mark-invoice-pending-btn" size="sm" variant="outline" className="gap-1.5 border-warning/40 text-warning hover:text-warning" onClick={() => recordPaymentStatus("pending")} disabled={Boolean(recordingStatus)}>
                {recordingStatus === "pending" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CircleDashed className="h-3.5 w-3.5" />} Mark Pending / Delayed
              </Button>
              <Button data-testid="mark-invoice-failed-btn" size="sm" variant="outline" className="gap-1.5 border-danger/40 text-danger hover:text-danger" onClick={() => recordPaymentStatus("failed")} disabled={Boolean(recordingStatus)}>
                {recordingStatus === "failed" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CircleX className="h-3.5 w-3.5" />} Record as Loss
              </Button>
            </>
          )}

          {/* Client action */}
          {user.role === "client" && canAct && (
            <Button data-testid="pay-invoice-btn" size="sm" className="gap-1.5" onClick={requestPayment} disabled={paying}>
              {paying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CreditCard className="h-3.5 w-3.5" />}
              {invoice.payment_link ? "Pay Now →" : "Click to Pay"}
            </Button>
          )}
        </div>

        {/* Payment link ready notice for client */}
        {user.role === "client" && invoice.payment_link && canAct && (
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-success/10 border border-success/20 px-3 py-2">
            <CreditCard className="h-3.5 w-3.5 text-success shrink-0" />
            <p className="text-xs text-success">Your payment link is ready. Click <strong>Pay Now</strong> above to proceed, and please check your spam folder if the email is not in your inbox.</p>
          </div>
        )}

        {/* Admin: inline payment link input */}
        {user.role !== "client" && showLinkInput && (
          <div className="mt-4 p-4 rounded-lg bg-surface-2 border border-white/10 space-y-3">
            <p className="text-xs font-mono uppercase text-graphite tracking-wider">Send Custom Payment Link</p>
            <p className="text-xs text-graphite">Paste your payment link below (e.g. Razorpay, PayPal, bank transfer link). It will be emailed directly to the client.</p>
            <div className="flex gap-2">
              <Input
                data-testid="payment-link-input"
                value={paymentLink}
                onChange={(e) => setPaymentLink(e.target.value)}
                placeholder="https://your-payment-link.com/..."
                className="bg-surface-1 border-white/10 text-sm flex-1"
              />
              <Button
                data-testid="confirm-send-payment-link-btn"
                size="sm"
                className="gap-1.5 shrink-0"
                onClick={sendPaymentLink}
                disabled={sending || !paymentLink.trim()}
              >
                {sending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                Send
              </Button>
            </div>
            <p className="text-xs text-graphite/70 italic">
              Note: Please check your spam folder if the email is not delivered to you.
            </p>
          </div>
        )}

        <div className="mt-4 text-xs text-graphite border-t border-white/5 pt-3">
          Note: Please check your spam folder if the email is not delivered to you.
        </div>
      </Card>
    </div>
  );
}

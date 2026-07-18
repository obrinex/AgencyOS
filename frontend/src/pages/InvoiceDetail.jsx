import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Send, CreditCard, Loader2, FileDown, Link2, CheckCircle2, CircleDashed, CircleX } from "lucide-react";
import api, { downloadFile } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { INVOICE_STATUS_CONFIG } from "@/lib/statusConfig";
import { formatMoney } from "@/lib/currency";
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
  const [recordingStatus, setRecordingStatus] = useState("");

  const load = async () => {
    const { data } = await api.get(`/invoices/${id}`);
    setInvoice(data);
  };

  useEffect(() => { load(); }, [id]);

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
              <>
                <p className="text-xs font-mono text-graphite mt-1">
                  Currency: {invoice.currency} · Rate: 1 {invoice.currency} = INR{" "}
                  {Number(invoice.conversion_rate || 1).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  {invoice.conversion_rate_source && ` · ${invoice.conversion_rate_source}`}
                </p>
                <p className="text-[10px] text-carbon mt-0.5">Rate pinned when the invoice was issued.</p>
              </>
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

        {invoice.payment_claim && invoice.status !== "paid" && (
          <div className="mt-6 rounded-lg bg-info/10 border border-info/20 p-4 text-sm" data-testid="payment-claim-banner">
            <p className="font-medium text-info mb-1">Crypto payment submitted — needs your verification</p>
            <p className="text-xs text-ash">
              {invoice.payment_claim.payer_email} says they paid via {invoice.payment_claim.network}.
            </p>
            <p className="text-xs font-mono text-graphite mt-1 break-all">Tx: {invoice.payment_claim.tx_hash}</p>
            <p className="text-xs text-graphite mt-2">Check your wallet for the incoming transfer, then change the invoice status to <span className="text-foreground">Paid</span>.</p>
          </div>
        )}

        {/* Action buttons */}
        <div className="mt-6 flex flex-wrap gap-2">
          <Button
            data-testid="copy-pay-link-btn" size="sm" variant="outline" className="gap-1.5 border-white/10"
            onClick={async () => {
              try {
                const { data } = await api.get(`/invoices/${id}/payment-link`);
                await navigator.clipboard.writeText(`${window.location.origin}/pay/${data.payment_token}`);
                toast.success("Payment page link copied — share it with your client");
              } catch (err) {
                toast.error("Could not create the payment link");
              }
            }}
          >
            <Link2 className="h-3.5 w-3.5" /> Copy Pay Link
          </Button>
          <Button data-testid="download-invoice-pdf-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={downloadPdf}>
            <FileDown className="h-3.5 w-3.5" /> Download PDF
          </Button>

          {/* Admin actions */}
          {user.role !== "client" && canAct && (
            <>
              <Button data-testid="send-invoice-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={sendInvoice}>
                <Send className="h-3.5 w-3.5" /> Send Invoice
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

          {/* Client action — opens the payment page (Crypto / Other Methods) */}
          {user.role === "client" && canAct && invoice.payment_token && (
            <Button
              data-testid="pay-invoice-btn" size="sm"
              className="gap-1.5 bg-[#26A17B] hover:bg-[#1f8968] text-white"
              onClick={() => window.open(`/pay/${invoice.payment_token}`, "_blank", "noopener,noreferrer")}
            >
              <CreditCard className="h-3.5 w-3.5" /> Pay Invoice
            </Button>
          )}
        </div>

        {/* Client payment guidance */}
        {user.role === "client" && canAct && (
          <div className="mt-3 rounded-lg bg-surface-2 border border-white/10 px-3 py-2.5">
            <p className="text-xs text-ash">Click <strong>Pay Invoice</strong> to open your payment page, where you can pay instantly by <strong>card, UPI or net banking</strong> — or with <strong>crypto</strong>.</p>
          </div>
        )}
        {user.role === "client" && invoice.payment_claim && canAct && (
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-info/10 border border-info/20 px-3 py-2">
            <CheckCircle2 className="h-3.5 w-3.5 text-info shrink-0" />
            <p className="text-xs text-info">We've received your crypto payment submission and are verifying it. You'll get a confirmation shortly.</p>
          </div>
        )}

        <div className="mt-4 text-xs text-graphite border-t border-white/5 pt-3">
          Note: Please check your spam folder if the email is not delivered to you.
        </div>
      </Card>
    </div>
  );
}

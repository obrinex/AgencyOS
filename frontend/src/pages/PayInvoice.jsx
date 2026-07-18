import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Wallet, Copy, CheckCircle2, ExternalLink, ShieldCheck } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { formatApiError } from "@/lib/api";

const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api` });

function qrUrl(data) {
  return `https://api.qrserver.com/v1/create-qr-code/?size=180x180&bgcolor=24-24-26&color=244-244-245&data=${encodeURIComponent(data)}`;
}

export default function PayInvoice() {
  const { token } = useParams();
  const [params] = useSearchParams();
  const [info, setInfo] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [method, setMethod] = useState(params.get("method") === "other" ? "other" : "crypto");
  const [activeWallet, setActiveWallet] = useState(null);
  const [claim, setClaim] = useState({ tx_hash: "", payer_email: "", note: "" });
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  useEffect(() => {
    api.get(`/public/pay/${token}`)
      .then((r) => {
        setInfo(r.data);
        if (r.data.wallets?.length) setActiveWallet(r.data.wallets[0]);
        // The URL wins (emails deep-link a method); otherwise follow the
        // server's per-currency preference, then whatever can actually take money.
        const urlMethod = params.get("method");
        if (urlMethod === "crypto" && r.data.wallets?.length) setMethod("crypto");
        else if (urlMethod === "other") setMethod("other");
        else if (r.data.preferred_method === "crypto" && r.data.wallets?.length) setMethod("crypto");
        else if (r.data.payment_link) setMethod("other");
        else if (r.data.wallets?.length) setMethod("crypto");
        else setMethod("other");
      })
      .catch(() => setNotFound(true));
  }, [token]);

  const copy = (text) => { navigator.clipboard.writeText(text); toast.success("Address copied"); };

  const submitClaim = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.post(`/public/pay/${token}/claim`, { ...claim, network: activeWallet.label });
      setDone(true);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSubmitting(false);
    }
  };

  if (notFound) return <div className="min-h-screen bg-background flex items-center justify-center p-6"><p className="text-graphite">This payment page doesn't exist or has expired.</p></div>;
  if (!info) return <div className="min-h-screen bg-background flex items-center justify-center"><p className="text-graphite font-mono text-sm">Loading…</p></div>;

  const symbol = info.currency === "INR" ? "₹" : "$";

  if (done || info.payment_claimed) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6" data-testid="payment-claimed">
        <Card className="max-w-md w-full p-8 bg-surface-1 border-white/10 text-center">
          <CheckCircle2 className="h-12 w-12 text-success mx-auto mb-4" />
          <h1 className="font-display text-xl font-bold mb-2">Payment submitted</h1>
          <p className="text-sm text-ash">Thanks! {info.agency_name} is verifying your transaction for {info.kind === "link" ? info.invoice_number : `invoice ${info.invoice_number}`}. You'll receive a confirmation once it clears.</p>
        </Card>
      </div>
    );
  }

  if (info.status === "paid") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <Card className="max-w-md w-full p-8 bg-surface-1 border-white/10 text-center">
          <CheckCircle2 className="h-12 w-12 text-success mx-auto mb-4" />
          <h1 className="font-display text-xl font-bold mb-2">Already paid</h1>
          <p className="text-sm text-ash">{info.kind === "link" ? info.invoice_number : `Invoice ${info.invoice_number}`} has been settled. Thank you!</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground p-6 flex justify-center" data-testid="pay-invoice-page">
      <div className="max-w-lg w-full">
        <div className="text-center mb-8 mt-6">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-foreground text-background font-display font-bold">
            {(info.agency_name || "O")[0]}
          </div>
          <h1 className="font-display text-2xl font-bold">{info.kind === "link" ? info.invoice_number : `Invoice ${info.invoice_number}`}</h1>
          <p className="text-sm text-graphite mt-1">{info.client_name ? `for ${info.client_name} · ` : ""}from {info.agency_name}</p>
          <p className="font-display text-4xl font-bold mt-4">{symbol}{info.total.toLocaleString()}</p>
          {info.due_date && <p className="text-xs text-graphite font-mono mt-1">Due {info.due_date.slice(0, 10)}</p>}
          {info.note && <p className="text-sm text-ash mt-2">{info.note}</p>}
        </div>

        {info.wallets.length > 0 && (
          <div className="grid grid-cols-2 gap-2 mb-4" data-testid="method-tabs">
            <button
              data-testid="method-tab-crypto"
              onClick={() => setMethod("crypto")}
              className={`rounded-lg border py-3 text-sm font-semibold transition-colors ${method === "crypto" ? "border-foreground bg-surface-2" : "border-white/10 hover:border-white/30 text-graphite"}`}
            >
              🪙 Pay with Crypto
              {info.preferred_method === "crypto" && (
                <span className="block text-[10px] font-normal text-graphite mt-0.5">Recommended for {info.currency}</span>
              )}
            </button>
            <button
              data-testid="method-tab-other"
              onClick={() => setMethod("other")}
              className={`rounded-lg border py-3 text-sm font-semibold transition-colors ${method === "other" ? "border-foreground bg-surface-2" : "border-white/10 hover:border-white/30 text-graphite"}`}
            >
              💳 Other Methods
            </button>
          </div>
        )}

        {method === "other" && (
          <Card className="p-5 bg-surface-1 border-white/10" data-testid="other-methods-card">
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite mb-3">Pay with card, UPI, net banking & wallets</p>
            {info.payment_link ? (
              <div className="space-y-2">
                <p className="text-sm text-ash mb-3">Pay securely via Cashfree using your preferred method.</p>
                <a href={info.payment_link} target="_blank" rel="noreferrer" data-testid="click-to-pay-btn"
                   className="flex items-center justify-center gap-2 w-full rounded-lg bg-foreground text-background py-3 font-semibold text-sm hover:opacity-90 transition-opacity">
                  Pay Now <ExternalLink className="h-4 w-4" />
                </a>
                <Button data-testid="copy-payment-link-btn" variant="outline" className="w-full border-white/10 gap-1.5"
                        onClick={() => { navigator.clipboard.writeText(info.payment_link); toast.success("Payment link copied"); }}>
                  <Copy className="h-4 w-4" /> Copy Payment Link
                </Button>
                <p className="text-[11px] text-graphite text-center pt-1">Secured by Cashfree Payments</p>
              </div>
            ) : (
              /* No Cashfree link: either it is not set up, the currency is not
                 INR, or Cashfree is unreachable. Say so plainly and point at
                 whatever else can take the payment. */
              <div className="text-center py-4" data-testid="no-online-payment">
                <p className="text-sm text-ash">Online payment isn&rsquo;t available right now.</p>
                {info.wallets.length > 0 ? (
                  <Button variant="outline" className="mt-3 border-white/10" onClick={() => setMethod("crypto")} data-testid="switch-to-crypto-btn">
                    Pay with crypto instead
                  </Button>
                ) : (
                  <p className="text-xs text-graphite mt-2">Please contact {info.agency_name} for payment details.</p>
                )}
              </div>
            )}
          </Card>
        )}

        {method === "crypto" && info.wallets.length > 0 && (
          <Card className="p-5 bg-surface-1 border-white/10">
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite mb-3 flex items-center gap-1.5"><Wallet className="h-3.5 w-3.5" /> Pay with Crypto</p>
            <div className="flex flex-wrap gap-1.5 mb-4">
              {info.wallets.map((w) => (
                <button key={w.id} data-testid={`wallet-tab-${w.id}`} onClick={() => setActiveWallet(w)}
                        className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${activeWallet?.id === w.id ? "border-foreground bg-surface-2 font-semibold" : "border-white/10 hover:border-white/30"}`}>
                  {w.label}
                </button>
              ))}
            </div>
            {activeWallet && (
              <div className="space-y-4">
                <p className="text-xs text-graphite">{activeWallet.note}</p>
                <div className="flex justify-center">
                  <img src={qrUrl(activeWallet.address)} alt="Wallet QR code" width="180" height="180" className="rounded-lg border border-white/10" />
                </div>
                <div className="flex items-center gap-2">
                  <Input readOnly value={activeWallet.address} className="bg-surface-2 border-white/10 font-mono text-xs" />
                  <Button size="sm" variant="outline" className="border-white/10 shrink-0 gap-1" onClick={() => copy(activeWallet.address)}><Copy className="h-3.5 w-3.5" /> Copy</Button>
                </div>
                <div className="rounded-lg bg-warning/10 border border-warning/20 p-3 text-xs text-warning">
                  Send only on the network shown above. Sending on the wrong network can lose your funds.
                </div>

                <form onSubmit={submitClaim} className="space-y-3 border-t border-white/10 pt-4">
                  <p className="text-sm font-medium flex items-center gap-1.5"><ShieldCheck className="h-4 w-4 text-success" /> After paying, confirm your transfer</p>
                  <div className="space-y-1"><Label>Transaction Hash / ID *</Label><Input data-testid="claim-txhash" required value={claim.tx_hash} onChange={(e) => setClaim({ ...claim, tx_hash: e.target.value })} placeholder="Paste from your wallet's transaction details" className="bg-surface-2 border-white/10 font-mono text-xs" /></div>
                  <div className="space-y-1"><Label>Your Email *</Label><Input data-testid="claim-email" required type="email" value={claim.payer_email} onChange={(e) => setClaim({ ...claim, payer_email: e.target.value })} className="bg-surface-2 border-white/10" /></div>
                  <div className="space-y-1"><Label>Note (optional)</Label><Textarea data-testid="claim-note" value={claim.note} onChange={(e) => setClaim({ ...claim, note: e.target.value })} rows={2} className="bg-surface-2 border-white/10" /></div>
                  <Button data-testid="claim-submit" type="submit" disabled={submitting} className="w-full">{submitting ? "Submitting…" : "I've sent the payment"}</Button>
                </form>
              </div>
            )}
          </Card>
        )}

        <p className="text-center font-mono text-[10px] text-carbon mt-6 tracking-widest uppercase">Powered by {info.agency_name}</p>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Receipt, ChevronRight } from "lucide-react";
import api from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { INVOICE_STATUS_CONFIG } from "@/lib/statusConfig";
import { formatMoney } from "@/lib/currency";
import { Skeleton } from "@/components/ui/skeleton";

/** Invoices.
 *
 *  The number and the amount are the two things anyone came here for, so they
 *  are the two things that stay visible at every width; the status badge is the
 *  first thing to drop on a narrow phone, because it is also the row's colour.
 */
export default function PortalInvoices() {
  const [invoices, setInvoices] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/portal/invoices").then((r) => setInvoices(r.data)).catch(() => setInvoices([]));
  }, []);

  if (!invoices) {
    return <div className="p-4 sm:p-6"><Skeleton className="h-64 w-full rounded-2xl bg-surface-1" /></div>;
  }

  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-6" data-testid="portal-invoices-page">
      <header className="mb-5">
        <h1 className="font-display text-2xl font-bold tracking-tight">Invoices</h1>
        <p className="mt-1 text-sm text-graphite">
          {invoices.length === 0 ? "Nothing yet." : `${invoices.length} in total`}
        </p>
      </header>

      {invoices.length === 0 ? (
        <div className="obx-glass rounded-2xl px-6 py-14 text-center" data-testid="portal-invoices-empty">
          <div className="obx-holo obx-glass relative mx-auto flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl">
            <Receipt className="relative z-10 h-5 w-5 text-primary" />
          </div>
          <p className="mt-4 text-sm">No invoices yet.</p>
          <p className="mt-1 text-xs text-graphite">Anything billed will show up here.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {invoices.map((inv, i) => (
            <button
              key={inv.id}
              onClick={() => navigate(`/portal/invoices/${inv.id}`)}
              data-testid={`portal-invoice-row-${inv.id}`}
              style={{ animationDelay: `${i * 35}ms` }}
              className="obx-glass obx-lift obx-sheen obx-reveal flex w-full items-center gap-3 rounded-xl px-4 py-3.5 text-left"
            >
              <span className="obx-figure min-w-0 flex-1 truncate font-mono text-sm">
                {inv.invoice_number}
              </span>
              <span className="obx-figure shrink-0 font-mono text-sm font-medium">
                {formatMoney(inv.total, inv.currency)}
              </span>
              <span className="hidden shrink-0 sm:block">
                <StatusBadge config={INVOICE_STATUS_CONFIG} value={inv.status} />
              </span>
              <ChevronRight className="h-4 w-4 shrink-0 text-carbon" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

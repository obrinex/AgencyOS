import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Receipt } from "lucide-react";
import api from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { INVOICE_STATUS_CONFIG } from "@/lib/statusConfig";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function PortalInvoices() {
  const [invoices, setInvoices] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/portal/invoices").then((r) => setInvoices(r.data));
  }, []);

  if (!invoices) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="portal-invoices-page">
      <PageHeader title="Invoices" description={`${invoices.length} invoices`} />
      {invoices.length === 0 ? (
        <EmptyState icon={Receipt} title="No invoices yet" description="Invoices from your agency will show up here." testId="portal-invoices-empty" />
      ) : (
        <div className="space-y-2">
          {invoices.map((inv) => (
            <Card key={inv.id} onClick={() => navigate(`/portal/invoices/${inv.id}`)} data-testid={`portal-invoice-row-${inv.id}`} className="p-4 bg-surface-1 border-white/10 cursor-pointer hover:border-white/25 flex items-center justify-between">
              <span className="font-mono text-sm">{inv.invoice_number}</span>
              <span className="font-mono text-sm">${inv.total.toLocaleString()}</span>
              <StatusBadge config={INVOICE_STATUS_CONFIG} value={inv.status} />
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

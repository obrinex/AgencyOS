import { useEffect, useState } from "react";
import { FileSignature } from "lucide-react";
import api from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { format } from "date-fns";

export default function PortalContracts() {
  const [contracts, setContracts] = useState(null);

  useEffect(() => {
    api.get("/portal/contracts").then((r) => setContracts(r.data));
  }, []);

  if (!contracts) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="portal-contracts-page">
      <PageHeader title="Contracts" description={`${contracts.length} contracts`} />
      {contracts.length === 0 ? (
        <EmptyState icon={FileSignature} title="No contracts yet" description="Signed agreements with your agency will appear here." testId="portal-contracts-empty" />
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {contracts.map((c) => (
            <Card key={c.id} data-testid={`portal-contract-card-${c.id}`} className="p-4 bg-surface-1 border-white/10">
              <p className="font-medium">{c.title}</p>
              <p className="text-xs font-mono uppercase text-graphite mt-1">{c.status}</p>
              {c.renewal_date && <p className="text-xs text-graphite mt-1">Renews {format(new Date(c.renewal_date), "MMM d, yyyy")}</p>}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

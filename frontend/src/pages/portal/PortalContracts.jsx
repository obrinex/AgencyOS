import { useEffect, useState } from "react";
import { FileSignature, PenLine, CheckCircle2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { format } from "date-fns";
import { toast } from "sonner";

export default function PortalContracts() {
  const [contracts, setContracts] = useState(null);
  const [signTarget, setSignTarget] = useState(null);
  const [signatureName, setSignatureName] = useState("");

  const load = async () => {
    const { data } = await api.get("/portal/contracts");
    setContracts(data);
  };

  useEffect(() => { load(); }, []);

  const sign = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/portal/contracts/${signTarget.id}/sign`, { signature_name: signatureName });
      toast.success("Contract signed");
      setSignTarget(null);
      setSignatureName("");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

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
              {c.status === "signed" ? (
                <p className="mt-3 flex items-center gap-1.5 text-xs text-success"><CheckCircle2 className="h-3.5 w-3.5" /> Signed by {c.signature_name}</p>
              ) : (
                <Button size="sm" variant="outline" className="mt-3 border-white/10 gap-1.5" data-testid={`portal-sign-contract-${c.id}`} onClick={() => setSignTarget(c)}>
                  <PenLine className="h-3.5 w-3.5" /> Review & Sign
                </Button>
              )}
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!signTarget} onOpenChange={(o) => !o && setSignTarget(null)}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="portal-sign-contract-dialog">
          <DialogHeader><DialogTitle>Sign: {signTarget?.title}</DialogTitle></DialogHeader>
          <form onSubmit={sign} className="space-y-3">
            <p className="text-sm text-graphite">By typing your full name below, you agree this constitutes your electronic signature and acceptance of this contract.</p>
            <div className="space-y-1"><Label>Full Name *</Label><Input data-testid="portal-signature-input" required value={signatureName} onChange={(e) => setSignatureName(e.target.value)} className="bg-surface-2 border-white/10 font-display italic" placeholder="Type your full name" /></div>
            <DialogFooter><Button type="submit" data-testid="portal-signature-submit">Sign Contract</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Building2, CheckCircle2, Circle, KeyRound, Copy, Eye, RefreshCw } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { INVOICE_STATUS_CONFIG, PROJECT_STATUS_CONFIG, TICKET_STATUS_CONFIG } from "@/lib/statusConfig";
import { formatMoney } from "@/lib/currency";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

export default function ClientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [client, setClient] = useState(null);
  const [portalOpen, setPortalOpen] = useState(false);
  const [portalForm, setPortalForm] = useState({ email: "", name: "" });
  const [creds, setCreds] = useState(null);
  const [portalCredsOpen, setPortalCredsOpen] = useState(false);
  const [portalCreds, setPortalCreds] = useState(null);
  const [resettingPortalPassword, setResettingPortalPassword] = useState(false);

  const load = async () => {
    const { data } = await api.get(`/clients/${id}`);
    setClient(data);
  };

  useEffect(() => { load(); }, [id]);

  const toggleChecklist = async (index, done) => {
    await api.patch(`/clients/${id}/checklist`, { index, done: !done });
    load();
  };

  const createPortalUser = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.post(`/clients/${id}/portal-user`, portalForm);
      setCreds(data);
      toast.success("Portal account created");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const revokePortalAccess = async () => {
    await api.delete(`/clients/${id}/portal-user`);
    toast.success("Portal access revoked");
    load();
  };

  const viewPortalCredentials = async () => {
    try {
      const { data } = await api.get(`/clients/${id}/portal-user`);
      setPortalCreds(data);
      setPortalCredsOpen(true);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const resetPortalPassword = async () => {
    setResettingPortalPassword(true);
    try {
      const { data } = await api.post(`/clients/${id}/portal-user/reset-password`);
      setPortalCreds(data);
      setPortalCredsOpen(true);
      toast.success("Client portal password reset");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setResettingPortalPassword(false);
    }
  };

  const copyPortalCreds = async () => {
    if (!portalCreds) return;
    const lines = [`Email: ${portalCreds.email}`];
    if (portalCreds.temp_password) lines.push(`Password: ${portalCreds.temp_password}`);
    await navigator.clipboard.writeText(lines.join("\n"));
    toast.success(portalCreds.temp_password ? "Portal login copied" : "Portal login email copied");
  };

  if (!client) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5" data-testid="client-detail-page">
      <button onClick={() => navigate("/clients")} className="flex items-center gap-1.5 text-sm text-graphite hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Clients
      </button>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-surface-1 border border-white/10"><Building2 className="h-5 w-5 text-graphite" /></div>
          <div>
            <h1 className="font-display text-2xl font-bold">{client.company_name}</h1>
            <p className="text-sm text-graphite">{client.industry || "No industry set"}</p>
          </div>
        </div>
        {!client.portal_user_id && (
          <Button data-testid="create-portal-user-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={() => setPortalOpen(true)}>
            <KeyRound className="h-3.5 w-3.5" /> Create Portal Access
          </Button>
        )}
        {client.portal_user_id && (
          <div className="flex flex-wrap gap-2">
            <Button data-testid="view-portal-user-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={viewPortalCredentials}>
              <Eye className="h-3.5 w-3.5" /> View Login
            </Button>
            <Button data-testid="reset-portal-password-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={resetPortalPassword} disabled={resettingPortalPassword}>
              <RefreshCw className={`h-3.5 w-3.5 ${resettingPortalPassword ? "animate-spin" : ""}`} /> Reset Password
            </Button>
            <Button data-testid="revoke-portal-user-btn" size="sm" variant="outline" className="gap-1.5 border-white/10 text-danger hover:text-danger" onClick={revokePortalAccess}>
              <KeyRound className="h-3.5 w-3.5" /> Revoke Portal Access
            </Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Revenue</p><p className="font-display text-xl font-bold text-success">{formatMoney(client.revenue_generated)}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Outstanding</p><p className="font-display text-xl font-bold text-warning">{formatMoney(client.outstanding_amount)}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">LTV</p><p className="font-display text-xl font-bold">{formatMoney(client.ltv)}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Health Score</p><p className="font-display text-xl font-bold">{client.health_score ?? 100}</p></Card>
      </div>

      <Tabs defaultValue="onboarding">
        <TabsList className="bg-surface-1 border border-white/10 flex-wrap h-auto">
          <TabsTrigger value="onboarding" data-testid="tab-onboarding">Onboarding</TabsTrigger>
          <TabsTrigger value="projects" data-testid="tab-projects">Projects</TabsTrigger>
          <TabsTrigger value="invoices" data-testid="tab-invoices">Invoices</TabsTrigger>
          <TabsTrigger value="contacts" data-testid="tab-contacts">Contacts</TabsTrigger>
          <TabsTrigger value="tickets" data-testid="tab-tickets">Tickets</TabsTrigger>
          <TabsTrigger value="contracts" data-testid="tab-contracts">Contracts</TabsTrigger>
        </TabsList>

        <TabsContent value="onboarding" className="mt-4 space-y-2">
          {client.onboarding_checklist?.map((item, i) => (
            <div key={i} data-testid={`checklist-item-${i}`} onClick={() => toggleChecklist(i, item.done)} className="flex items-center gap-2 rounded-lg border border-white/10 bg-surface-1 px-3 py-2 cursor-pointer hover:border-white/20">
              {item.done ? <CheckCircle2 className="h-4 w-4 text-success" /> : <Circle className="h-4 w-4 text-graphite" />}
              <span className={item.done ? "text-ash line-through" : "text-foreground"}>{item.title}</span>
            </div>
          ))}
        </TabsContent>

        <TabsContent value="projects" className="mt-4 space-y-2">
          {client.projects?.length === 0 && <p className="text-sm text-graphite py-6 text-center">No projects yet</p>}
          {client.projects?.map((p) => (
            <div key={p.id} onClick={() => navigate(`/projects/${p.id}`)} className="flex items-center justify-between rounded-lg border border-white/10 bg-surface-1 px-3 py-2.5 cursor-pointer hover:border-white/20">
              <span className="text-sm">{p.name}</span>
              <StatusBadge config={PROJECT_STATUS_CONFIG} value={p.status} />
            </div>
          ))}
        </TabsContent>

        <TabsContent value="invoices" className="mt-4 space-y-2">
          {client.invoices?.length === 0 && <p className="text-sm text-graphite py-6 text-center">No invoices yet</p>}
          {client.invoices?.map((inv) => (
            <div key={inv.id} onClick={() => navigate(`/invoices/${inv.id}`)} className="flex items-center justify-between rounded-lg border border-white/10 bg-surface-1 px-3 py-2.5 cursor-pointer hover:border-white/20">
              <span className="text-sm font-mono">{inv.invoice_number}</span>
              <span className="text-sm font-mono">{formatMoney(inv.total, inv.currency)}</span>
              <StatusBadge config={INVOICE_STATUS_CONFIG} value={inv.status} />
            </div>
          ))}
        </TabsContent>

        <TabsContent value="contacts" className="mt-4 space-y-2">
          {client.contacts?.length === 0 && <p className="text-sm text-graphite py-6 text-center">No contacts linked</p>}
          {client.contacts?.map((c) => (
            <div key={c.id} className="rounded-lg border border-white/10 bg-surface-1 px-3 py-2.5">
              <p className="text-sm">{c.name}</p>
              <p className="text-xs text-graphite">{c.position} · {c.email}</p>
            </div>
          ))}
        </TabsContent>

        <TabsContent value="tickets" className="mt-4 space-y-2">
          {client.tickets?.length === 0 && <p className="text-sm text-graphite py-6 text-center">No support tickets</p>}
          {client.tickets?.map((t) => (
            <div key={t.id} onClick={() => navigate(`/support/${t.id}`)} className="flex items-center justify-between rounded-lg border border-white/10 bg-surface-1 px-3 py-2.5 cursor-pointer hover:border-white/20">
              <span className="text-sm">{t.subject}</span>
              <StatusBadge config={TICKET_STATUS_CONFIG} value={t.status} />
            </div>
          ))}
        </TabsContent>

        <TabsContent value="contracts" className="mt-4 space-y-2">
          {client.contracts?.length === 0 && <p className="text-sm text-graphite py-6 text-center">No contracts yet</p>}
          {client.contracts?.map((c) => (
            <div key={c.id} className="rounded-lg border border-white/10 bg-surface-1 px-3 py-2.5 flex items-center justify-between">
              <span className="text-sm">{c.title}</span>
              <span className="text-xs font-mono text-graphite uppercase">{c.status}</span>
            </div>
          ))}
        </TabsContent>
      </Tabs>

      <Dialog open={portalOpen} onOpenChange={(o) => { setPortalOpen(o); if (!o) setCreds(null); }}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-portal-dialog">
          <DialogHeader><DialogTitle>Create Client Portal Access</DialogTitle></DialogHeader>
          {!creds ? (
            <form onSubmit={createPortalUser} className="space-y-3">
              <div className="space-y-1"><Label>Contact Name</Label><Input data-testid="portal-form-name" required value={portalForm.name} onChange={(e) => setPortalForm({ ...portalForm, name: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Email</Label><Input data-testid="portal-form-email" type="email" required value={portalForm.email} onChange={(e) => setPortalForm({ ...portalForm, email: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <DialogFooter><Button type="submit" data-testid="portal-form-submit">Create Access</Button></DialogFooter>
            </form>
          ) : (
            <div className="space-y-3" data-testid="portal-credentials-result">
              <p className="text-sm text-ash">Share these credentials securely with your client:</p>
              <div className="rounded-lg bg-surface-2 border border-white/10 p-3 font-mono text-sm space-y-1">
                <p>Email: {creds.email}</p>
                <p>Password: {creds.temp_password}</p>
              </div>
              <p className="text-xs text-graphite">These credentials are stored here for portal access. No email is sent automatically.</p>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={portalCredsOpen} onOpenChange={setPortalCredsOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="portal-login-dialog">
          <DialogHeader><DialogTitle>Client Portal Login</DialogTitle></DialogHeader>
          {portalCreds && (
            <div className="space-y-3">
              <div className="rounded-lg bg-surface-2 border border-white/10 p-3 font-mono text-sm space-y-1">
                <p>Email: {portalCreds.email}</p>
                <p>Password: {portalCreds.temp_password || "No stored password yet. Use Reset Password to generate one here."}</p>
              </div>
              {portalCreds.password_updated_at && (
                <p className="text-xs text-graphite">Last generated: {new Date(portalCreds.password_updated_at).toLocaleString()}</p>
              )}
              <DialogFooter>
                <Button type="button" variant="outline" className="gap-1.5 border-white/10" onClick={copyPortalCreds}>
                  <Copy className="h-3.5 w-3.5" /> Copy
                </Button>
              </DialogFooter>
              <p className="text-xs text-graphite text-center pt-1">No email is sent automatically for portal password resets.</p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

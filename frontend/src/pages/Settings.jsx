import { useEffect, useState } from "react";
import PageHeader from "@/components/PageHeader";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/contexts/AuthContext";
import { Switch } from "@/components/ui/switch";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";
import { Plus, ShieldCheck } from "lucide-react";

export default function Settings() {
  const { user, refetch } = useAuth();
  const [company, setCompany] = useState(null);
  const [team, setTeam] = useState(null);
  const [logs, setLogs] = useState(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: "", name: "", role: "team_member" });
  const [inviteResult, setInviteResult] = useState(null);
  const [twoFA, setTwoFA] = useState({ enabled: user?.two_fa_enabled, setupData: null, code: "" });

  const load = async () => {
    const [c, t] = await Promise.all([api.get("/settings/company"), api.get("/settings/team")]);
    setCompany(c.data);
    setTeam(t.data);
    if (user?.role === "admin") {
      const l = await api.get("/settings/audit-logs?limit=50");
      setLogs(l.data);
    }
  };

  useEffect(() => { load(); }, []);

  const saveCompany = async () => {
    await api.put("/settings/company", company);
    toast.success("Company settings saved");
  };

  const invite = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.post("/settings/team", inviteForm);
      setInviteResult(data);
      toast.success("Team member invited");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const setup2FA = async () => {
    const { data } = await api.post("/auth/2fa/setup");
    setTwoFA((s) => ({ ...s, setupData: data }));
  };

  const enable2FA = async () => {
    try {
      await api.post("/auth/2fa/enable", { code: twoFA.code });
      toast.success("2FA enabled");
      setTwoFA({ enabled: true, setupData: null, code: "" });
      refetch();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const disable2FA = async () => {
    await api.post("/auth/2fa/disable");
    setTwoFA({ enabled: false, setupData: null, code: "" });
    refetch();
    toast.success("2FA disabled");
  };

  if (!company || !team) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="settings-page">
      <PageHeader title="Settings" description="Company, team, security & billing" />
      <Tabs defaultValue="company">
        <TabsList className="bg-surface-1 border border-white/10 flex-wrap h-auto">
          <TabsTrigger value="company" data-testid="settings-tab-company">Company</TabsTrigger>
          <TabsTrigger value="team" data-testid="settings-tab-team">Team</TabsTrigger>
          <TabsTrigger value="security" data-testid="settings-tab-security">Security</TabsTrigger>
          {user?.role === "admin" && <TabsTrigger value="audit" data-testid="settings-tab-audit">Audit Logs</TabsTrigger>}
        </TabsList>

        <TabsContent value="company" className="mt-4 max-w-md space-y-3">
          <div className="space-y-1"><Label>Company Name</Label><Input data-testid="settings-company-name" value={company.company_name || ""} onChange={(e) => setCompany({ ...company, company_name: e.target.value })} className="bg-surface-1 border-white/10" /></div>
          <div className="space-y-1"><Label>Custom Domain</Label><Input data-testid="settings-custom-domain" value={company.custom_domain || ""} onChange={(e) => setCompany({ ...company, custom_domain: e.target.value })} placeholder="app.youragency.com" className="bg-surface-1 border-white/10" /></div>
          <div className="space-y-1"><Label>Currency</Label>
            <Select value={company.currency || "INR"} onValueChange={(v) => setCompany({ ...company, currency: v })}>
              <SelectTrigger data-testid="settings-currency" className="bg-surface-1 border-white/10"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="INR">INR - Base Currency</SelectItem><SelectItem value="USD">USD</SelectItem></SelectContent>
            </Select>
            <p className="text-xs text-graphite mt-1">All finance totals across the app are aggregated in this base currency. Individual invoices/expenses can still be recorded in a different currency with a custom conversion rate.</p>
          </div>
          <Button data-testid="save-company-settings-btn" onClick={saveCompany} size="sm">Save Changes</Button>
        </TabsContent>

        <TabsContent value="team" className="mt-4 space-y-3">
          <div className="flex justify-end">
            <Button data-testid="open-invite-team-btn" size="sm" className="gap-1.5" onClick={() => { setInviteOpen(true); setInviteResult(null); }}><Plus className="h-3.5 w-3.5" /> Invite Member</Button>
          </div>
          <div className="space-y-2">
            {team.map((m) => (
              <Card key={m.id} data-testid={`team-member-${m.id}`} className="p-3 bg-surface-1 border-white/10 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">{m.name}</p>
                  <p className="text-xs text-graphite">{m.email}</p>
                </div>
                <span className="font-mono text-[10px] uppercase text-ash">{m.role}</span>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="security" className="mt-4 max-w-md space-y-4">
          <Card className="p-4 bg-surface-1 border-white/10">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> Two-Factor Authentication</p>
                <p className="text-xs text-graphite mt-1">Add an extra layer of security to your account</p>
              </div>
              <Switch data-testid="2fa-toggle" checked={!!twoFA.enabled} onCheckedChange={(v) => (v ? setup2FA() : disable2FA())} />
            </div>
            {twoFA.setupData && (
              <div className="mt-4 space-y-3 border-t border-white/10 pt-4">
                <p className="text-xs text-graphite">Scan this in your authenticator app, then enter the code:</p>
                <p className="font-mono text-xs break-all bg-surface-2 rounded p-2">{twoFA.setupData.secret}</p>
                <InputOTP maxLength={6} value={twoFA.code} onChange={(v) => setTwoFA((s) => ({ ...s, code: v }))} data-testid="2fa-setup-code-input">
                  <InputOTPGroup>{[0, 1, 2, 3, 4, 5].map((i) => <InputOTPSlot key={i} index={i} className="border-white/10 bg-surface-2" />)}</InputOTPGroup>
                </InputOTP>
                <Button data-testid="2fa-enable-submit" size="sm" onClick={enable2FA} disabled={twoFA.code.length < 6}>Enable 2FA</Button>
              </div>
            )}
          </Card>
        </TabsContent>

        {user?.role === "admin" && (
          <TabsContent value="audit" className="mt-4 space-y-2">
            {logs?.map((l) => (
              <div key={l.id} className="flex items-center justify-between text-sm rounded-lg border border-white/10 bg-surface-1 px-3 py-2">
                <span className="font-mono text-xs">{l.action}</span>
                <span className="text-[10px] font-mono text-carbon">{formatDistanceToNow(new Date(l.created_at), { addSuffix: true })}</span>
              </div>
            ))}
            {logs?.length === 0 && <p className="text-sm text-graphite text-center py-6">No audit logs yet</p>}
          </TabsContent>
        )}
      </Tabs>

      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="invite-team-dialog">
          <DialogHeader><DialogTitle>Invite Team Member</DialogTitle></DialogHeader>
          {!inviteResult ? (
            <form onSubmit={invite} className="space-y-3">
              <div className="space-y-1"><Label>Name</Label><Input data-testid="invite-form-name" required value={inviteForm.name} onChange={(e) => setInviteForm({ ...inviteForm, name: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Email</Label><Input data-testid="invite-form-email" type="email" required value={inviteForm.email} onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <DialogFooter><Button type="submit" data-testid="invite-form-submit">Send Invite</Button></DialogFooter>
              <div className="text-xs text-graphite text-center pt-1">
                Note: Please check your spam folder if the email is not delivered to you.
              </div>
            </form>
          ) : (
            <div className="space-y-2" data-testid="invite-credentials-result">
              <p className="text-sm text-ash">Share these credentials securely:</p>
              <div className="rounded-lg bg-surface-2 border border-white/10 p-3 font-mono text-sm">
                <p>Email: {inviteResult.email}</p>
                <p>Password: {inviteResult.temp_password}</p>
              </div>
              <div className="text-xs text-graphite text-center pt-1">
                Note: Please check your spam folder if the email is not delivered to you.
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

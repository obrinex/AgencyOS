import { useEffect, useState } from "react";
import PageHeader from "@/components/PageHeader";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
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
import { Plus, ShieldCheck, Trash2, KeyRound, Palette, Upload, Send, RotateCcw } from "lucide-react";
import { DialogDescription } from "@/components/ui/dialog";
import { Switch as UISwitch } from "@/components/ui/switch";

const PERMISSION_MODULES = [
  { key: "crm", label: "Pipeline & Leads" },
  { key: "emails", label: "Emails" },
  { key: "documents", label: "Proposals & Contracts" },
  { key: "clients", label: "Clients" },
  { key: "projects", label: "Projects & Tasks" },
  { key: "support", label: "Support Desk" },
  { key: "calendar", label: "Calendar" },
  { key: "finance", label: "Finance & Invoices" },
  { key: "knowledge", label: "Knowledge Base" },
  { key: "vault", label: "Password Vault" },
  { key: "files", label: "Files" },
  { key: "notes", label: "Notes" },
  { key: "analytics", label: "Analytics & Automations" },
];

export default function Settings() {
  const { user, refetch } = useAuth();
  const [company, setCompany] = useState(null);
  const [team, setTeam] = useState(null);
  const [logs, setLogs] = useState(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: "", name: "", role: "team_member" });
  const [inviteResult, setInviteResult] = useState(null);
  const [twoFA, setTwoFA] = useState({ enabled: user?.two_fa_enabled, setupData: null, code: "" });

  const [payments, setPayments] = useState(null);
  const [brand, setBrand] = useState(null);
  const [brandDefaults, setBrandDefaults] = useState(null);
  const [previewHtml, setPreviewHtml] = useState("");
  const [uploadingLogo, setUploadingLogo] = useState(false);

  const load = async () => {
    const [c, t, p, b] = await Promise.all([
      api.get("/settings/company"), api.get("/settings/team"),
      api.get("/settings/payments"), api.get("/settings/email-template"),
    ]);
    setCompany(c.data);
    setTeam(t.data);
    setPayments(p.data);
    setBrand(b.data.brand);
    setBrandDefaults(b.data.defaults);
    refreshPreview();
    if (user?.role === "admin") {
      const l = await api.get("/settings/audit-logs?limit=50");
      setLogs(l.data);
    }
  };

  const refreshPreview = async () => {
    try {
      const { data } = await api.get("/settings/email-template/preview");
      setPreviewHtml(data.html);
    } catch { /* preview is best-effort */ }
  };

  const saveBrand = async () => {
    try {
      const { data } = await api.put("/settings/email-template", brand);
      setBrand(data.brand);
      await refreshPreview();
      toast.success("Email branding saved");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const uploadLogo = async (file) => {
    if (!file) return;
    setUploadingLogo(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/settings/email-template/logo", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setBrand((b) => ({ ...b, logo_url: data.logo_url, show_logo: true }));
      await refreshPreview();
      toast.success("Logo uploaded");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setUploadingLogo(false);
    }
  };

  const sendTestEmail = async () => {
    try {
      // persist current edits first so the test reflects them
      await api.put("/settings/email-template", brand);
      const { data } = await api.post("/settings/email-template/test", {});
      toast.success(data.message);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const COLOR_KEYS = ["bg_color", "card_color", "text_color", "muted_color", "accent_color", "accent_text_color", "border_color", "box_color"];
  const applyPreset = (preset) => {
    const light = {
      bg_color: "#F4F2ED", card_color: "#FFFFFF", text_color: "#141414", muted_color: "#6B6B70",
      accent_color: "#141414", accent_text_color: "#FFFFFF", border_color: "#E4E1DA", box_color: "#F4F2ED",
    };
    // "dark" pulls color keys from server defaults; both presets touch colors only (logo/name/footer untouched)
    const colors = preset === "light" ? light : Object.fromEntries(COLOR_KEYS.map((k) => [k, brandDefaults?.[k]]));
    setBrand((b) => ({ ...b, ...colors }));
  };

  useEffect(() => { load(); }, []);

  const saveCompany = async () => {
    await api.put("/settings/company", company);
    toast.success("Company settings saved");
  };

  const savePayments = async () => {
    try {
      const { data } = await api.put("/settings/payments", payments);
      setPayments(data);
      toast.success("Payment settings saved — new invoices will include these payment options");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const [removeTarget, setRemoveTarget] = useState(null);
  const [permTarget, setPermTarget] = useState(null);
  const [permSelection, setPermSelection] = useState([]);

  const openPermissions = (member) => {
    setPermTarget(member);
    setPermSelection(member.permissions || []);
  };

  const savePermissions = async () => {
    try {
      await api.put(`/settings/team/${permTarget.id}`, { permissions: permSelection });
      toast.success(permSelection.length === 0
        ? `${permTarget.name} now has full access`
        : `${permTarget.name} limited to ${permSelection.length} module(s)`);
      setPermTarget(null);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const changeRole = async (memberId, role) => {
    try {
      await api.put(`/settings/team/${memberId}`, { role });
      toast.success("Role updated");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const removeMember = async () => {
    try {
      await api.delete(`/settings/team/${removeTarget.id}`);
      toast.success(`${removeTarget.name} removed from the team`);
      setRemoveTarget(null);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
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
          <TabsTrigger value="payments" data-testid="settings-tab-payments">Payments</TabsTrigger>
          <TabsTrigger value="branding" data-testid="settings-tab-branding">Email Branding</TabsTrigger>
          <TabsTrigger value="security" data-testid="settings-tab-security">Security</TabsTrigger>
          {user?.role === "admin" && <TabsTrigger value="audit" data-testid="settings-tab-audit">Audit Logs</TabsTrigger>}
        </TabsList>

        <TabsContent value="branding" className="mt-4">
          {brand && (
            <div className="grid lg:grid-cols-[420px_1fr] gap-6" data-testid="branding-panel">
              {/* editor */}
              <div className="space-y-5">
                <Card className="p-4 bg-surface-1 border-white/10 space-y-3">
                  <p className="text-sm font-medium flex items-center gap-2"><Palette className="h-4 w-4" /> Logo & Identity</p>
                  <div className="flex items-center gap-3">
                    <div className="h-14 w-14 rounded-lg border border-white/10 bg-surface-2 flex items-center justify-center overflow-hidden shrink-0">
                      {brand.logo_url ? <img src={brand.logo_url} alt="logo" className="max-h-12 max-w-12 object-contain" /> : <span className="text-[10px] text-graphite">no logo</span>}
                    </div>
                    <div className="flex-1 space-y-2">
                      <label className="inline-flex items-center gap-1.5 text-xs cursor-pointer rounded-md border border-white/10 px-2.5 py-1.5 hover:bg-surface-2">
                        <Upload className="h-3 w-3" /> {uploadingLogo ? "Uploading…" : "Upload logo"}
                        <input data-testid="logo-upload" type="file" accept="image/*" className="hidden" onChange={(e) => uploadLogo(e.target.files?.[0])} disabled={uploadingLogo} />
                      </label>
                      <div className="flex items-center gap-2">
                        <UISwitch data-testid="show-logo-toggle" checked={!!brand.show_logo} onCheckedChange={(v) => setBrand({ ...brand, show_logo: v })} />
                        <span className="text-xs text-graphite">Show logo (off = show name as text)</span>
                      </div>
                    </div>
                  </div>
                  <div className="space-y-1"><Label>Logo URL</Label><Input data-testid="brand-logo-url" value={brand.logo_url || ""} onChange={(e) => setBrand({ ...brand, logo_url: e.target.value })} placeholder="https://obrinex.space/brand/monogram-paper.png" className="bg-surface-2 border-white/10 font-mono text-xs" /><p className="text-[11px] text-graphite">Upload above, or paste a public image URL (e.g. your website logo).</p></div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1"><Label>Brand Name</Label><Input data-testid="brand-name" value={brand.brand_name || ""} onChange={(e) => setBrand({ ...brand, brand_name: e.target.value })} className="bg-surface-2 border-white/10" /></div>
                    <div className="space-y-1"><Label>Tagline</Label><Input data-testid="brand-tagline" value={brand.tagline || ""} onChange={(e) => setBrand({ ...brand, tagline: e.target.value })} className="bg-surface-2 border-white/10" /></div>
                  </div>
                </Card>

                <Card className="p-4 bg-surface-1 border-white/10 space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">Colors</p>
                    <div className="flex gap-1.5">
                      <button data-testid="preset-dark" onClick={() => applyPreset("dark")} className="text-[11px] rounded-md border border-white/10 px-2 py-1 hover:bg-surface-2">Dark (brand)</button>
                      <button data-testid="preset-light" onClick={() => applyPreset("light")} className="text-[11px] rounded-md border border-white/10 px-2 py-1 hover:bg-surface-2">Light</button>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { key: "bg_color", label: "Background" },
                      { key: "card_color", label: "Card" },
                      { key: "text_color", label: "Text" },
                      { key: "muted_color", label: "Muted text" },
                      { key: "accent_color", label: "Accent / buttons" },
                      { key: "accent_text_color", label: "Button text" },
                      { key: "border_color", label: "Borders" },
                      { key: "box_color", label: "Info boxes" },
                    ].map((c) => (
                      <div key={c.key} className="space-y-1">
                        <Label className="text-xs">{c.label}</Label>
                        <div className="flex items-center gap-2">
                          <input type="color" data-testid={`color-${c.key}`} value={brand[c.key] || "#000000"} onChange={(e) => setBrand({ ...brand, [c.key]: e.target.value })} className="h-8 w-9 rounded border border-white/10 bg-transparent cursor-pointer shrink-0" />
                          <Input value={brand[c.key] || ""} onChange={(e) => setBrand({ ...brand, [c.key]: e.target.value })} className="bg-surface-2 border-white/10 font-mono text-xs h-8" />
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>

                <Card className="p-4 bg-surface-1 border-white/10 space-y-3">
                  <p className="text-sm font-medium">Footer</p>
                  <div className="space-y-1"><Label>Footer Text</Label><Input data-testid="brand-footer" value={brand.footer_text || ""} onChange={(e) => setBrand({ ...brand, footer_text: e.target.value })} className="bg-surface-2 border-white/10" /></div>
                  <div className="space-y-1"><Label>Footer Note (small print)</Label><Input data-testid="brand-footer-note" value={brand.footer_note || ""} onChange={(e) => setBrand({ ...brand, footer_note: e.target.value })} className="bg-surface-2 border-white/10" /></div>
                </Card>

                <div className="flex flex-wrap items-center gap-2">
                  <Button data-testid="save-brand-btn" onClick={saveBrand}>Save Branding</Button>
                  <Button data-testid="preview-brand-btn" variant="outline" className="border-white/10 gap-1.5" onClick={refreshPreview}><RotateCcw className="h-3.5 w-3.5" /> Refresh Preview</Button>
                  <Button data-testid="test-email-btn" variant="outline" className="border-white/10 gap-1.5" onClick={sendTestEmail}><Send className="h-3.5 w-3.5" /> Send Test to Me</Button>
                </div>
              </div>

              {/* live preview */}
              <div className="space-y-2">
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">Live Preview (sample invoice email)</p>
                <div className="rounded-xl border border-white/10 overflow-hidden bg-white">
                  <iframe data-testid="email-preview" title="Email preview" srcDoc={previewHtml} className="w-full h-[560px] border-0" sandbox="" />
                </div>
                <p className="text-[11px] text-graphite">This shows exactly how the shell of every email looks. Click "Refresh Preview" after editing, or "Send Test to Me" to see it in your real inbox.</p>
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="company" className="mt-4 max-w-md space-y-3">
          <div className="space-y-1"><Label>Company Name</Label><Input data-testid="settings-company-name" value={company.company_name || ""} onChange={(e) => setCompany({ ...company, company_name: e.target.value })} className="bg-surface-1 border-white/10" /></div>
          <div className="space-y-1">
            <Label>Postal Address</Label>
            <Textarea
              data-testid="settings-company-address"
              value={company.address || ""}
              onChange={(e) => setCompany({ ...company, address: e.target.value })}
              rows={3}
              placeholder="Street, City, State, PIN"
              className="bg-surface-1 border-white/10 text-sm"
            />
            <p className="text-xs text-graphite mt-1">
              Appears in the footer of every outreach email. Commercial email law in
              most countries requires a real physical address, so the AI SDR
              <span className="text-warning"> will refuse to send without one</span> and
              park the message for review instead.
            </p>
          </div>
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

        <TabsContent value="payments" className="mt-4 max-w-xl space-y-5">
          {payments && (
            <>
              <Card className="p-4 bg-surface-1 border-white/10" data-testid="cashfree-card">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">Cashfree Payments</p>
                    <p className="text-xs text-graphite mt-1">
                      Card, UPI, net banking and wallets, in INR and USD. A payment link is
                      created automatically the first time a client opens an invoice, and the
                      invoice is marked paid the moment Cashfree confirms — nothing to send or
                      reconcile by hand.
                    </p>
                  </div>
                  <span
                    data-testid="cashfree-status"
                    className={`shrink-0 rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
                      payments.cashfree_configured
                        ? "bg-success/10 text-success border border-success/20"
                        : "bg-warning/10 text-warning border border-warning/20"
                    }`}
                  >
                    {payments.cashfree_configured ? payments.cashfree_env : "Not configured"}
                  </span>
                </div>
                {!payments.cashfree_configured && (
                  <p className="text-xs text-warning mt-3">
                    Set <span className="font-mono">CASHFREE_APP_ID</span> and{" "}
                    <span className="font-mono">CASHFREE_SECRET_KEY</span> in the backend environment,
                    then restart. Keys are never stored in the database.
                  </p>
                )}
                {payments.cashfree_configured && payments.cashfree_env === "sandbox" && (
                  <p className="text-xs text-warning mt-3">
                    Sandbox mode — payments are simulated and no money moves. Set{" "}
                    <span className="font-mono">CASHFREE_ENV=production</span> when you go live.
                  </p>
                )}
                <p className="text-xs text-graphite mt-3">
                  USD invoices open on <span className="text-foreground">crypto</span> by default — no FX
                  spread or international card fee — with Cashfree offered alongside. INR leads with Cashfree.
                  USD through Cashfree needs international payments enabled on your account; if it is not,
                  the page quietly falls back to crypto.
                </p>
              </Card>

              <Card className="p-4 bg-surface-1 border-white/10 space-y-3" data-testid="crypto-card">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Cryptocurrency Payments</p>
                    <p className="text-xs text-graphite">Clients get a "Pay with Crypto" page showing your wallet addresses with QR codes. Zero processor fees — payments go straight to your wallet.</p>
                  </div>
                  <Switch data-testid="crypto-toggle" checked={!!payments.crypto_enabled} onCheckedChange={(v) => setPayments({ ...payments, crypto_enabled: v })} />
                </div>
                <div className="space-y-3">
                  {[
                    { key: "usdt_trc20_address", label: "USDT · TRON (TRC-20)", badge: "RECOMMENDED · near-zero fees", placeholder: "T..." },
                    { key: "usdt_pol_address", label: "USDT · Polygon (POL)", badge: "very low fees", placeholder: "0x..." },
                    { key: "usdt_bep20_address", label: "USDT · BNB Chain (BEP-20)", badge: "low fees", placeholder: "0x..." },
                    { key: "eth_address", label: "Ethereum (ETH / ERC-20)", badge: null, placeholder: "0x... (optional)" },
                    { key: "btc_address", label: "Bitcoin (BTC)", badge: null, placeholder: "bc1... (optional)" },
                    { key: "sol_address", label: "Solana (SOL)", badge: "fast · minimal fees", placeholder: "So1... (optional)" },
                  ].map((w) => (
                    <div key={w.key} className="space-y-1">
                      <Label>{w.label} {w.badge && <span className="text-success font-mono text-[10px]">{w.badge.toUpperCase()}</span>}</Label>
                      <Input data-testid={w.key} value={payments[w.key] || ""} onChange={(e) => setPayments({ ...payments, [w.key]: e.target.value })} placeholder={w.placeholder} className="bg-surface-2 border-white/10 font-mono text-xs" />
                    </div>
                  ))}
                  <p className="text-xs text-warning">Note: Polygon, BNB Chain, and Ethereum addresses all start with 0x — they can even be the same address in Trust Wallet/MetaMask, but the client must send on the matching network. Only fill in networks you've confirmed in your wallet.</p>
                </div>
                <p className="text-xs text-graphite">Get free addresses from <span className="text-foreground">Trust Wallet</span> or <span className="text-foreground">MetaMask</span> — open the app, pick the coin/network, tap Receive, and copy the address here. Double-check the network matches (TRC-20 vs ERC-20).</p>
              </Card>

              <Button data-testid="save-payments-btn" onClick={savePayments} size="sm">Save Payment Settings</Button>
            </>
          )}
        </TabsContent>

        <TabsContent value="team" className="mt-4 space-y-3">
          <div className="flex justify-end">
            <Button data-testid="open-invite-team-btn" size="sm" className="gap-1.5" onClick={() => { setInviteOpen(true); setInviteResult(null); }}><Plus className="h-3.5 w-3.5" /> Invite Member</Button>
          </div>
          <div className="space-y-2">
            {team.map((m) => (
              <Card key={m.id} data-testid={`team-member-${m.id}`} className="p-3 bg-surface-1 border-white/10 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{m.name} {m.id === user?.id && <span className="font-mono text-[9px] text-graphite">(YOU)</span>}</p>
                  <p className="text-xs text-graphite truncate">{m.email}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {user?.role === "admin" && m.id !== user?.id ? (
                    <>
                      {m.role === "team_member" && (
                        <button
                          data-testid={`permissions-${m.id}`}
                          onClick={() => openPermissions(m)}
                          className="flex items-center gap-1 text-xs text-graphite hover:text-foreground border border-white/10 rounded-md px-2 py-1"
                          title="Regulate module access"
                        >
                          <KeyRound className="h-3 w-3" />
                          {m.permissions?.length ? `${m.permissions.length} modules` : "Full access"}
                        </button>
                      )}
                      <Select value={m.role} onValueChange={(v) => changeRole(m.id, v)}>
                        <SelectTrigger data-testid={`team-role-${m.id}`} className="w-32 h-7 text-xs bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="team_member">Team Member</SelectItem>
                          <SelectItem value="admin">Admin</SelectItem>
                        </SelectContent>
                      </Select>
                      <button
                        data-testid={`remove-member-${m.id}`}
                        onClick={() => setRemoveTarget(m)}
                        className="text-graphite hover:text-danger p-1"
                        title="Remove team member"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </>
                  ) : (
                    <span className="font-mono text-[10px] uppercase text-ash">{m.role === "team_member" ? "Team Member" : m.role}</span>
                  )}
                </div>
              </Card>
            ))}
          </div>

          <Dialog open={!!permTarget} onOpenChange={(o) => !o && setPermTarget(null)}>
            <DialogContent className="bg-surface-1 border-white/10 max-h-[85vh] overflow-y-auto" data-testid="permissions-dialog">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2"><KeyRound className="h-4 w-4" /> Permissions — {permTarget?.name}</DialogTitle>
                <DialogDescription>
                  Choose which modules {permTarget?.name} can use. With nothing selected, they have <span className="text-foreground">full access</span>. Restricted modules disappear from their sidebar and are blocked on the server.
                </DialogDescription>
              </DialogHeader>
              <div className="grid grid-cols-2 gap-2">
                {PERMISSION_MODULES.map((mod) => {
                  const on = permSelection.includes(mod.key);
                  return (
                    <button
                      key={mod.key}
                      data-testid={`perm-${mod.key}`}
                      onClick={() => setPermSelection(on ? permSelection.filter((p) => p !== mod.key) : [...permSelection, mod.key])}
                      className={`flex items-center justify-between rounded-lg border px-3 py-2 text-xs text-left transition-colors ${on ? "border-foreground bg-surface-2 font-medium" : "border-white/10 text-graphite hover:border-white/30"}`}
                    >
                      {mod.label}
                      <span className={`h-2 w-2 rounded-full shrink-0 ml-2 ${on ? "bg-success" : "bg-surface-3"}`} />
                    </button>
                  );
                })}
              </div>
              <div className="flex items-center justify-between">
                <button className="text-xs text-graphite hover:text-foreground" onClick={() => setPermSelection([])}>Reset to full access</button>
                <Button data-testid="save-permissions-btn" size="sm" onClick={savePermissions}>Save Permissions</Button>
              </div>
            </DialogContent>
          </Dialog>

          <Dialog open={!!removeTarget} onOpenChange={(o) => !o && setRemoveTarget(null)}>
            <DialogContent className="bg-surface-1 border-white/10" data-testid="remove-member-dialog">
              <DialogHeader>
                <DialogTitle>Remove team member?</DialogTitle>
                <DialogDescription>
                  <span className="text-foreground font-medium">{removeTarget?.name}</span> ({removeTarget?.email}) will immediately lose access to AgencyOS. Their past work (tasks, time logs, notes) stays in your records.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" className="border-white/10" onClick={() => setRemoveTarget(null)}>Cancel</Button>
                <Button variant="destructive" data-testid="confirm-remove-member-btn" onClick={removeMember}>Remove Member</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
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

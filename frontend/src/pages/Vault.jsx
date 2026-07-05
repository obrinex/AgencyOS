import { useEffect, useState } from "react";
import { Plus, Lock, Eye, EyeOff, Trash2, Copy } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

const TYPES = ["api_key", "password", "hosting", "domain", "ssh", "note"];
const emptyForm = { title: "", type: "password", username: "", password: "", url: "", notes: "" };

export default function Vault() {
  const [entries, setEntries] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [revealed, setRevealed] = useState({});

  const load = async () => {
    const { data } = await api.get("/vault");
    setEntries(data);
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/vault", form);
      toast.success("Entry secured in vault");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const reveal = async (id) => {
    if (revealed[id]) {
      setRevealed((r) => ({ ...r, [id]: null }));
      return;
    }
    const { data } = await api.post(`/vault/${id}/reveal`);
    setRevealed((r) => ({ ...r, [id]: data.password }));
  };

  const remove = async (id) => {
    await api.delete(`/vault/${id}`);
    load();
  };

  const copy = (text) => {
    navigator.clipboard.writeText(text);
    toast.success("Copied to clipboard");
  };

  if (!entries) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="vault-page">
      <PageHeader
        title="Password Vault"
        description="Encrypted credentials, API keys & secrets"
        actions={<Button data-testid="open-create-vault-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New Entry</Button>}
      />
      {entries.length === 0 ? (
        <EmptyState icon={Lock} title="Vault is empty" description="Securely store API keys, hosting logins, and client credentials." testId="vault-empty-state" />
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {entries.map((e) => (
            <Card key={e.id} data-testid={`vault-entry-${e.id}`} className="p-4 bg-surface-1 border-white/10">
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-medium">{e.title}</p>
                  <p className="text-xs font-mono uppercase text-graphite">{e.type}</p>
                </div>
                <button data-testid={`delete-vault-${e.id}`} onClick={() => remove(e.id)} className="text-graphite hover:text-danger"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
              {e.username && <p className="mt-2 text-sm text-ash">User: {e.username}</p>}
              {e.has_password && (
                <div className="mt-1 flex items-center gap-2">
                  <span className="font-mono text-sm text-ash">{revealed[e.id] || "••••••••••"}</span>
                  <button data-testid={`reveal-vault-${e.id}`} onClick={() => reveal(e.id)} className="text-graphite hover:text-foreground">
                    {revealed[e.id] ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                  {revealed[e.id] && <button onClick={() => copy(revealed[e.id])} className="text-graphite hover:text-foreground"><Copy className="h-3.5 w-3.5" /></button>}
                </div>
              )}
              {e.url && <p className="mt-1 text-xs text-info truncate">{e.url}</p>}
            </Card>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-vault-dialog">
          <DialogHeader><DialogTitle>New Vault Entry</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="space-y-1"><Label>Title *</Label><Input data-testid="vault-form-title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1">
              <Label>Type</Label>
              <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                <SelectTrigger data-testid="vault-form-type" className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                <SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Username</Label><Input data-testid="vault-form-username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Password</Label><Input data-testid="vault-form-password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            </div>
            <div className="space-y-1"><Label>URL</Label><Input data-testid="vault-form-url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <DialogFooter><Button type="submit" data-testid="vault-form-submit">Save Entry</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

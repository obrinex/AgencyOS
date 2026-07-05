import { useEffect, useState } from "react";
import { Plus, Users, Mail, Phone, Linkedin, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

const emptyForm = { name: "", company: "", position: "", email: "", phone: "", linkedin: "", timezone: "", birthday: "", notes: "" };

export default function Contacts() {
  const [contacts, setContacts] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const { data } = await api.get("/contacts");
    setContacts(data);
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/contacts", form);
      toast.success("Contact created");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    await api.delete(`/contacts/${id}`);
    load();
  };

  if (!contacts) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="contacts-page">
      <PageHeader
        title="Contacts"
        description={`${contacts.length} contacts across all companies`}
        actions={<Button data-testid="open-create-contact-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New Contact</Button>}
      />
      {contacts.length === 0 ? (
        <EmptyState icon={Users} title="No contacts yet" description="Add contacts to keep track of the people behind each company." testId="contacts-empty-state" />
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {contacts.map((c) => (
            <Card key={c.id} data-testid={`contact-card-${c.id}`} className="p-4 bg-surface-1 border-white/10">
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-medium">{c.name}</p>
                  <p className="text-xs text-graphite">{c.position} {c.company && `· ${c.company}`}</p>
                </div>
                <button data-testid={`delete-contact-${c.id}`} onClick={() => remove(c.id)} className="text-graphite hover:text-danger"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
              <div className="mt-3 space-y-1 text-xs text-ash">
                {c.email && <p className="flex items-center gap-1.5"><Mail className="h-3 w-3" /> {c.email}</p>}
                {c.phone && <p className="flex items-center gap-1.5"><Phone className="h-3 w-3" /> {c.phone}</p>}
                {c.linkedin && <p className="flex items-center gap-1.5"><Linkedin className="h-3 w-3" /> {c.linkedin}</p>}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-contact-dialog">
          <DialogHeader><DialogTitle>New Contact</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Name *</Label><Input data-testid="contact-form-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Company</Label><Input data-testid="contact-form-company" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Position</Label><Input data-testid="contact-form-position" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Email</Label><Input data-testid="contact-form-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Phone</Label><Input data-testid="contact-form-phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>LinkedIn</Label><Input data-testid="contact-form-linkedin" value={form.linkedin} onChange={(e) => setForm({ ...form, linkedin: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            </div>
            <DialogFooter><Button type="submit" data-testid="contact-form-submit" disabled={saving}>{saving ? "Creating..." : "Create Contact"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

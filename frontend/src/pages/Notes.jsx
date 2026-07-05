import { useEffect, useState } from "react";
import { Plus, Pin, PinOff, Trash2, StickyNote } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { formatDistanceToNow } from "date-fns";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const COLOR_STYLES = {
  default: "bg-surface-1 border-white/10",
  amber: "bg-amber-500/10 border-amber-500/30",
  green: "bg-emerald-500/10 border-emerald-500/30",
  blue: "bg-blue-500/10 border-blue-500/30",
  red: "bg-red-500/10 border-red-500/30",
  purple: "bg-purple-500/10 border-purple-500/30",
};

const COLORS = Object.keys(COLOR_STYLES);
const emptyForm = { title: "", content: "", color: "default" };

export default function Notes() {
  const [notes, setNotes] = useState(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);

  const load = async () => {
    const { data } = await api.get("/notes");
    setNotes(data);
  };

  useEffect(() => { load(); }, []);

  const openCreate = () => { setEditing(null); setForm(emptyForm); setOpen(true); };
  const openEdit = (note) => { setEditing(note); setForm({ title: note.title || "", content: note.content, color: note.color || "default" }); setOpen(true); };

  const save = async (e) => {
    e.preventDefault();
    try {
      if (editing) {
        await api.put(`/notes/${editing.id}`, form);
        toast.success("Note updated");
      } else {
        await api.post("/notes", form);
        toast.success("Note created");
      }
      setOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const togglePin = async (note) => {
    await api.put(`/notes/${note.id}`, { pinned: !note.pinned });
    load();
  };

  const remove = async (id) => {
    await api.delete(`/notes/${id}`);
    toast.success("Note deleted");
    load();
  };

  if (!notes) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  const pinned = notes.filter((n) => n.pinned);
  const others = notes.filter((n) => !n.pinned);

  const renderNote = (n) => (
    <Card
      key={n.id}
      data-testid={`note-card-${n.id}`}
      className={cn("p-4 border cursor-pointer hover:border-white/30 transition-colors flex flex-col gap-2 break-inside-avoid", COLOR_STYLES[n.color] || COLOR_STYLES.default)}
      onClick={() => openEdit(n)}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="font-display text-sm font-semibold truncate flex-1">{n.title || "Untitled"}</p>
        <div className="flex items-center gap-1 shrink-0">
          <button data-testid={`note-pin-${n.id}`} onClick={(e) => { e.stopPropagation(); togglePin(n); }} className="text-graphite hover:text-foreground">
            {n.pinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
          </button>
          <button data-testid={`note-delete-${n.id}`} onClick={(e) => { e.stopPropagation(); remove(n.id); }} className="text-graphite hover:text-danger">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      <p className="text-sm text-ash whitespace-pre-wrap line-clamp-6">{n.content}</p>
      <p className="text-[10px] font-mono text-carbon mt-auto pt-1">{formatDistanceToNow(new Date(n.updated_at), { addSuffix: true })}</p>
    </Card>
  );

  return (
    <div className="p-6 space-y-6" data-testid="notes-page">
      <PageHeader
        title="Notes"
        description="Your private notes — visible only to you"
        actions={<Button data-testid="open-create-note-btn" size="sm" className="gap-1.5" onClick={openCreate}><Plus className="h-3.5 w-3.5" /> New Note</Button>}
      />

      {notes.length === 0 ? (
        <EmptyState icon={StickyNote} title="No notes yet" description="Jot down anything private — ideas, reminders, drafts. Only you can see these." testId="notes-empty-state" />
      ) : (
        <div className="space-y-6">
          {pinned.length > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite mb-2">Pinned</p>
              <div className="columns-1 sm:columns-2 lg:columns-3 gap-4 space-y-4" data-testid="pinned-notes-list">
                {pinned.map(renderNote)}
              </div>
            </div>
          )}
          {others.length > 0 && (
            <div>
              {pinned.length > 0 && <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite mb-2">Others</p>}
              <div className="columns-1 sm:columns-2 lg:columns-3 gap-4 space-y-4" data-testid="other-notes-list">
                {others.map(renderNote)}
              </div>
            </div>
          )}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="note-form-dialog">
          <DialogHeader><DialogTitle>{editing ? "Edit Note" : "New Note"}</DialogTitle></DialogHeader>
          <form onSubmit={save} className="space-y-3">
            <div className="space-y-1"><Label>Title</Label><Input data-testid="note-form-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1"><Label>Content *</Label><Textarea data-testid="note-form-content" required rows={6} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1">
              <Label>Color</Label>
              <div className="flex items-center gap-2">
                {COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    data-testid={`note-color-${c}`}
                    onClick={() => setForm({ ...form, color: c })}
                    className={cn("h-6 w-6 rounded-full border transition-transform", COLOR_STYLES[c], form.color === c ? "scale-110 border-foreground" : "border-white/20")}
                  />
                ))}
              </div>
            </div>
            <DialogFooter>
              {editing && <Button type="button" variant="outline" className="border-white/10 mr-auto" data-testid="note-form-delete" onClick={() => { remove(editing.id); setOpen(false); }}>Delete</Button>}
              <Button type="submit" data-testid="note-form-submit">{editing ? "Save Changes" : "Create Note"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

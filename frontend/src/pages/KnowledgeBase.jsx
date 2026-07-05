import { useEffect, useState } from "react";
import { Plus, BookOpen, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";

const CATEGORIES = [
  { value: "wiki", label: "Internal Wiki" },
  { value: "prompt", label: "Prompt Library" },
  { value: "automation", label: "Automation Library" },
  { value: "sop", label: "SOP Library" },
  { value: "documentation", label: "Documentation" },
  { value: "template", label: "Templates" },
];

const emptyForm = { title: "", category: "wiki", content: "" };

export default function KnowledgeBase() {
  const [articles, setArticles] = useState(null);
  const [category, setCategory] = useState("all");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);

  const load = async () => {
    const { data } = await api.get("/kb");
    setArticles(data);
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/kb", form);
      toast.success("Article created");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const remove = async (id) => {
    await api.delete(`/kb/${id}`);
    load();
  };

  if (!articles) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  const filtered = category === "all" ? articles : articles.filter((a) => a.category === category);

  return (
    <div className="p-6" data-testid="knowledge-base-page">
      <PageHeader
        title="Knowledge Base"
        description="Wiki, SOPs, prompts & automation docs"
        actions={<Button data-testid="open-create-article-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New Article</Button>}
      />
      <Tabs value={category} onValueChange={setCategory} className="mb-4">
        <TabsList className="bg-surface-1 border border-white/10 flex-wrap h-auto">
          <TabsTrigger value="all" data-testid="kb-filter-all">All</TabsTrigger>
          {CATEGORIES.map((c) => <TabsTrigger key={c.value} value={c.value} data-testid={`kb-filter-${c.value}`}>{c.label}</TabsTrigger>)}
        </TabsList>
      </Tabs>

      {filtered.length === 0 ? (
        <EmptyState icon={BookOpen} title="No articles yet" description="Document your SOPs, prompts, and automation playbooks here." testId="kb-empty-state" />
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((a) => (
            <Card key={a.id} data-testid={`kb-article-${a.id}`} className="p-4 bg-surface-1 border-white/10">
              <div className="flex items-start justify-between">
                <p className="font-medium">{a.title}</p>
                <button data-testid={`delete-kb-${a.id}`} onClick={() => remove(a.id)} className="text-graphite hover:text-danger"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
              <p className="text-xs font-mono uppercase text-graphite mt-1">{a.category}</p>
              <p className="text-sm text-ash mt-2 line-clamp-3">{a.content}</p>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10 max-w-lg" data-testid="create-article-dialog">
          <DialogHeader><DialogTitle>New Article</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="space-y-1"><Label>Title *</Label><Input data-testid="article-form-title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1">
              <Label>Category</Label>
              <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                <SelectTrigger data-testid="article-form-category" className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1"><Label>Content</Label><Textarea data-testid="article-form-content" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} className="bg-surface-2 border-white/10 min-h-[160px]" /></div>
            <DialogFooter><Button type="submit" data-testid="article-form-submit">Create Article</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

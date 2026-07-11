import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Globe, Mail, Phone, MapPin, Building2, Send, Trash2, Sparkles, Copy, Loader2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { STAGE_CONFIG, STAGES_LIST, PRIORITY_CONFIG } from "@/lib/statusConfig";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatDistanceToNow } from "date-fns";
import { toast } from "sonner";

export default function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [lead, setLead] = useState(null);
  const [activities, setActivities] = useState([]);
  const [note, setNote] = useState("");
  const [drafting, setDrafting] = useState(false);

  const draftReply = async () => {
    setDrafting(true);
    try {
      await api.post(`/ai/leads/${id}/draft-reply`);
      toast.success("AI reply drafted");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setDrafting(false);
    }
  };

  const load = async () => {
    const [l, a] = await Promise.all([api.get(`/leads/${id}`), api.get(`/leads/${id}/activities`)]);
    setLead(l.data);
    setActivities(a.data);
  };

  useEffect(() => {
    load();
  }, [id]);

  const changeStage = async (stage) => {
    try {
      const { data } = await api.patch(`/leads/${id}/stage`, { stage });
      if (data.automation) toast.success("Deal won! Client, project & invoice auto-generated.", { duration: 5000 });
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const addNote = async () => {
    if (!note.trim()) return;
    await api.post(`/leads/${id}/activities`, { type: "note", content: note });
    setNote("");
    load();
  };

  const deleteLead = async () => {
    await api.delete(`/leads/${id}`);
    toast.success("Lead deleted");
    navigate("/crm");
  };

  if (!lead) {
    return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5" data-testid="lead-detail-page">
      <button onClick={() => navigate("/crm")} data-testid="back-to-pipeline" className="flex items-center gap-1.5 text-sm text-graphite hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Pipeline
      </button>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2"><Building2 className="h-5 w-5 text-graphite" />{lead.company}</h1>
          <div className="mt-2 flex items-center gap-2">
            <StatusBadge config={PRIORITY_CONFIG} value={lead.priority} testId="lead-priority-badge" />
            {lead.converted_client_id && (
              <Button size="sm" variant="link" className="h-auto p-0 text-info" onClick={() => navigate(`/clients/${lead.converted_client_id}`)}>View Client →</Button>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select value={lead.stage} onValueChange={changeStage}>
            <SelectTrigger data-testid="lead-stage-select" className="w-48 bg-surface-1 border-white/10"><SelectValue /></SelectTrigger>
            <SelectContent>{STAGES_LIST.map((s) => <SelectItem key={s} value={s}>{STAGE_CONFIG[s].label}</SelectItem>)}</SelectContent>
          </Select>
          <Button size="icon" variant="outline" className="border-white/10" data-testid="delete-lead-btn" onClick={deleteLead}><Trash2 className="h-4 w-4" /></Button>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        <Card className="p-4 bg-surface-1 border-white/10 space-y-2 text-sm">
          {lead.website && <p className="flex items-center gap-2 text-ash"><Globe className="h-3.5 w-3.5 text-graphite" /> {lead.website}</p>}
          {lead.email && <p className="flex items-center gap-2 text-ash"><Mail className="h-3.5 w-3.5 text-graphite" /> {lead.email}</p>}
          {lead.phone && <p className="flex items-center gap-2 text-ash"><Phone className="h-3.5 w-3.5 text-graphite" /> {lead.phone}</p>}
          {lead.location && <p className="flex items-center gap-2 text-ash"><MapPin className="h-3.5 w-3.5 text-graphite" /> {lead.location}</p>}
        </Card>
        <Card className="p-4 bg-surface-1 border-white/10 text-sm">
          <p className="font-mono text-[10px] uppercase text-graphite mb-1">Est. Revenue</p>
          <p className="font-display text-xl font-bold">${(lead.revenue || 0).toLocaleString()}</p>
        </Card>
        <Card className="p-4 bg-surface-1 border-white/10 text-sm">
          <p className="font-mono text-[10px] uppercase text-graphite mb-1">Score</p>
          <p className="font-display text-xl font-bold">{lead.score || 0}/100</p>
        </Card>
      </div>

      <Card className="p-4 bg-surface-1 border-white/10" data-testid="ai-reply-card">
        <div className="flex items-center justify-between mb-2">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" /> AI-Drafted Reply</p>
          <div className="flex items-center gap-2">
            {lead.ai_draft_reply && (
              <Button size="sm" variant="outline" className="h-7 text-xs gap-1 border-white/10" onClick={() => { navigator.clipboard.writeText(lead.ai_draft_reply); toast.success("Reply copied"); }}>
                <Copy className="h-3 w-3" /> Copy
              </Button>
            )}
            <Button data-testid="draft-reply-btn" size="sm" variant="outline" className="h-7 text-xs gap-1 border-white/10" onClick={draftReply} disabled={drafting}>
              {drafting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />} {lead.ai_draft_reply ? "Regenerate" : "Draft with AI"}
            </Button>
          </div>
        </div>
        {lead.ai_draft_reply ? (
          <p className="text-sm text-ash whitespace-pre-line">{lead.ai_draft_reply}</p>
        ) : (
          <p className="text-xs text-graphite">No draft yet — click "Draft with AI" and the assistant will write a personalized reply based on this lead's details.</p>
        )}
      </Card>

      <Tabs defaultValue="timeline">
        <TabsList className="bg-surface-1 border border-white/10">
          <TabsTrigger data-testid="tab-timeline" value="timeline">Timeline</TabsTrigger>
          <TabsTrigger data-testid="tab-notes" value="notes">Notes</TabsTrigger>
        </TabsList>
        <TabsContent value="timeline" className="mt-4">
          <div className="space-y-3" data-testid="lead-timeline">
            {activities.length === 0 && <p className="text-sm text-graphite py-6 text-center">No activity yet</p>}
            {activities.map((a) => (
              <div key={a.id} className="flex gap-3 text-sm">
                <span className="h-1.5 w-1.5 mt-1.5 rounded-full bg-info shrink-0" />
                <div>
                  <p className="text-ash">{a.content}</p>
                  <p className="text-[10px] font-mono text-carbon">{formatDistanceToNow(new Date(a.created_at), { addSuffix: true })} · {a.type}</p>
                </div>
              </div>
            ))}
          </div>
        </TabsContent>
        <TabsContent value="notes" className="mt-4 space-y-3">
          <Textarea data-testid="lead-note-input" placeholder="Add a note..." value={note} onChange={(e) => setNote(e.target.value)} className="bg-surface-2 border-white/10" />
          <Button data-testid="lead-note-submit" size="sm" onClick={addNote} className="gap-1.5"><Send className="h-3.5 w-3.5" /> Add Note</Button>
        </TabsContent>
      </Tabs>
    </div>
  );
}

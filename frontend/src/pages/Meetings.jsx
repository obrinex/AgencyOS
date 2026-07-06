import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Plus, Calendar as CalendarIcon, RefreshCw, Link2, Link2Off, Trash2, MapPin } from "lucide-react";
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
import { format } from "date-fns";
import { toast } from "sonner";

const emptyForm = { title: "", start_time: "", end_time: "", location: "Google Meet", notes: "" };

export default function Meetings() {
  const [meetings, setMeetings] = useState(null);
  const [google, setGoogle] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [syncing, setSyncing] = useState(false);
  const [params, setParams] = useSearchParams();

  const load = async () => {
    const [m, g] = await Promise.all([api.get("/meetings"), api.get("/meetings/google/status")]);
    setMeetings(m.data);
    setGoogle(g.data);
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    const status = params.get("google");
    if (status === "connected") toast.success("Google Calendar connected");
    if (status === "error") toast.error("Failed to connect Google Calendar");
    if (status) { params.delete("google"); setParams(params); load(); }
  }, [params]);

  const connectGoogle = async () => {
    try {
      const { data } = await api.get("/meetings/google/connect");
      window.location.href = data.authorization_url;
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const disconnectGoogle = async () => {
    await api.post("/meetings/google/disconnect");
    toast.success("Google Calendar disconnected");
    load();
  };

  const syncGoogle = async () => {
    setSyncing(true);
    try {
      const { data } = await api.post("/meetings/google/sync");
      toast.success(`Synced ${data.synced} event(s) from Google Calendar`);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSyncing(false);
    }
  };

  const createMeeting = async (e) => {
    e.preventDefault();
    try {
      await api.post("/meetings", {
        ...form,
        start_time: new Date(form.start_time).toISOString(),
        end_time: form.end_time ? new Date(form.end_time).toISOString() : null,
      });
      toast.success("Meeting scheduled");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const remove = async (id) => {
    await api.delete(`/meetings/${id}`);
    toast.success("Meeting deleted");
    load();
  };

  if (!meetings || !google) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  const now = new Date();
  const upcoming = meetings.filter((m) => new Date(m.start_time) >= now && m.status !== "cancelled");
  const past = meetings.filter((m) => new Date(m.start_time) < now || m.status === "cancelled");

  const renderMeeting = (m) => (
    <Card key={m.id} data-testid={`meeting-row-${m.id}`} className="p-4 bg-surface-1 border-white/10 flex items-start justify-between gap-3">
      <div>
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">{m.title}</p>
          {m.source === "google" && <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-surface-2 text-info uppercase">Google</span>}
          {m.status === "cancelled" && <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-surface-2 text-danger uppercase">Cancelled</span>}
        </div>
        <p className="text-xs text-graphite font-mono mt-1">{format(new Date(m.start_time), "MMM d, yyyy \u00b7 h:mm a")}</p>
        {m.location && <p className="text-xs text-graphite flex items-center gap-1 mt-1"><MapPin className="h-3 w-3" /> {m.location}</p>}
        {m.notes && <p className="text-xs text-ash mt-1 line-clamp-2">{m.notes}</p>}
      </div>
      <button data-testid={`delete-meeting-${m.id}`} onClick={() => remove(m.id)} className="text-graphite hover:text-danger shrink-0"><Trash2 className="h-3.5 w-3.5" /></button>
    </Card>
  );

  return (
    <div className="p-6 space-y-6" data-testid="meetings-page">
      <PageHeader
        title="Meetings"
        description="Schedule meetings and sync with Google Calendar"
        actions={<Button data-testid="open-create-meeting-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New Meeting</Button>}
      />

      <Card className="p-4 bg-surface-1 border-white/10 flex items-center justify-between flex-wrap gap-3" data-testid="google-calendar-card">
        <div className="flex items-center gap-2">
          <CalendarIcon className="h-4 w-4 text-graphite" />
          <div>
            <p className="text-sm font-medium">Google Calendar</p>
            <p className="text-xs text-graphite">{google.connected ? `Connected as ${google.email}` : google.configured ? "Not connected" : "Not configured on this server"}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {google.connected ? (
            <>
              <Button data-testid="sync-google-calendar-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={syncGoogle} disabled={syncing}>
                <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} /> {syncing ? "Syncing..." : "Sync Now"}
              </Button>
              <Button data-testid="disconnect-google-calendar-btn" size="sm" variant="outline" className="gap-1.5 border-white/10 text-danger" onClick={disconnectGoogle}>
                <Link2Off className="h-3.5 w-3.5" /> Disconnect
              </Button>
            </>
          ) : (
            <Button data-testid="connect-google-calendar-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={connectGoogle} disabled={!google.configured}>
              <Link2 className="h-3.5 w-3.5" /> Connect
            </Button>
          )}
        </div>
      </Card>

      {meetings.length === 0 ? (
        <EmptyState icon={CalendarIcon} title="No meetings yet" description="Schedule a meeting or connect Google Calendar and sync your events." testId="meetings-empty-state" />
      ) : (
        <div className="space-y-6">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite mb-2">Upcoming</p>
            <div className="space-y-2" data-testid="upcoming-meetings-list">
              {upcoming.length === 0 && <p className="text-sm text-graphite py-4 text-center">No upcoming meetings</p>}
              {upcoming.map(renderMeeting)}
            </div>
          </div>
          {past.length > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite mb-2">Past</p>
              <div className="space-y-2" data-testid="past-meetings-list">{past.map(renderMeeting)}</div>
            </div>
          )}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-meeting-dialog">
          <DialogHeader><DialogTitle>New Meeting</DialogTitle></DialogHeader>
          <form onSubmit={createMeeting} className="space-y-3">
            <div className="space-y-1"><Label>Title *</Label><Input data-testid="meeting-form-title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Start *</Label><Input data-testid="meeting-form-start" type="datetime-local" required value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>End</Label><Input data-testid="meeting-form-end" type="datetime-local" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            </div>
            <div className="space-y-1"><Label>Location</Label><Input data-testid="meeting-form-location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1"><Label>Notes</Label><Textarea data-testid="meeting-form-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            {google.connected && <p className="text-xs text-graphite">This will also be added to your connected Google Calendar.</p>}
            <DialogFooter><Button type="submit" data-testid="meeting-form-submit">Schedule Meeting</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

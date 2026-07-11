import { useEffect, useMemo, useState } from "react";
import {
  Plus, ChevronLeft, ChevronRight, Trash2, MapPin, Clock, Link2, Copy, Settings2, CalendarDays, Users,
} from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import {
  format, startOfMonth, endOfMonth, startOfWeek, endOfWeek, eachDayOfInterval,
  isSameMonth, isSameDay, isToday, addMonths, parseISO,
} from "date-fns";
import { toast } from "sonner";

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const emptyForm = { title: "", start_time: "", end_time: "", location: "Google Meet", notes: "" };

export default function Calendar() {
  const [meetings, setMeetings] = useState(null);
  const [month, setMonth] = useState(new Date());
  const [selectedDay, setSelectedDay] = useState(new Date());
  const [open, setOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [booking, setBooking] = useState(null);
  const [bookingOpen, setBookingOpen] = useState(false);

  const load = async () => {
    const [m, b] = await Promise.all([api.get("/meetings"), api.get("/bookings/settings")]);
    setMeetings(m.data);
    setBooking(b.data);
  };

  useEffect(() => { load(); }, []);

  const byDay = useMemo(() => {
    const map = {};
    (meetings || []).forEach((m) => {
      if (m.status === "cancelled") return;
      const key = format(parseISO(m.start_time), "yyyy-MM-dd");
      (map[key] = map[key] || []).push(m);
    });
    Object.values(map).forEach((arr) => arr.sort((a, b) => a.start_time.localeCompare(b.start_time)));
    return map;
  }, [meetings]);

  const days = useMemo(() => {
    const start = startOfWeek(startOfMonth(month), { weekStartsOn: 1 });
    const end = endOfWeek(endOfMonth(month), { weekStartsOn: 1 });
    return eachDayOfInterval({ start, end });
  }, [month]);

  const dayMeetings = byDay[format(selectedDay, "yyyy-MM-dd")] || [];

  const openCreate = (day) => {
    const d = day || selectedDay;
    const base = format(d, "yyyy-MM-dd");
    setForm({ ...emptyForm, start_time: `${base}T10:00`, end_time: `${base}T10:30` });
    setEditTarget(null);
    setOpen(true);
  };

  const openEdit = (m) => {
    setEditTarget(m);
    setForm({
      title: m.title,
      start_time: format(parseISO(m.start_time), "yyyy-MM-dd'T'HH:mm"),
      end_time: m.end_time ? format(parseISO(m.end_time), "yyyy-MM-dd'T'HH:mm") : "",
      location: m.location || "",
      notes: m.notes || "",
    });
    setOpen(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    const payload = {
      ...form,
      start_time: new Date(form.start_time).toISOString(),
      end_time: form.end_time ? new Date(form.end_time).toISOString() : null,
    };
    try {
      if (editTarget) {
        await api.put(`/meetings/${editTarget.id}`, payload);
        toast.success("Meeting updated");
      } else {
        await api.post("/meetings", payload);
        toast.success("Meeting scheduled");
      }
      setOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const remove = async (id) => {
    await api.delete(`/meetings/${id}`);
    toast.success("Meeting deleted");
    setOpen(false);
    load();
  };

  const bookingUrl = booking ? `${window.location.origin}/book/${booking.slug}` : "";

  const copyLink = () => {
    navigator.clipboard.writeText(bookingUrl);
    toast.success("Booking link copied to clipboard");
  };

  const saveBooking = async (updates) => {
    try {
      const { data } = await api.put("/bookings/settings", updates);
      setBooking(data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const setDayCfg = (idx, patch) => {
    const days = { ...booking.days, [idx]: { ...booking.days[idx], ...patch } };
    setBooking({ ...booking, days });
  };

  if (!meetings || !booking) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6 space-y-5" data-testid="calendar-page">
      <PageHeader
        title="Calendar"
        description="Your agency's own calendar — meetings, scheduling, and client bookings"
        actions={
          <div className="flex items-center gap-2">
            <Button data-testid="booking-settings-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={() => setBookingOpen(true)}>
              <Settings2 className="h-3.5 w-3.5" /> Booking Page
            </Button>
            <Button data-testid="open-create-meeting-btn" size="sm" className="gap-1.5" onClick={() => openCreate()}>
              <Plus className="h-3.5 w-3.5" /> New Meeting
            </Button>
          </div>
        }
      />

      <Card className="p-4 bg-surface-1 border-white/10 flex items-center justify-between flex-wrap gap-3" data-testid="booking-link-card">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 border border-white/10 shrink-0">
            <Link2 className="h-4 w-4 text-graphite" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium">Your booking link {booking.enabled ? "" : "(disabled)"}</p>
            <p className="text-xs text-graphite font-mono truncate">{bookingUrl}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Switch checked={!!booking.enabled} onCheckedChange={(v) => saveBooking({ enabled: v })} data-testid="booking-enabled-switch" />
          <Button data-testid="copy-booking-link-btn" size="sm" variant="outline" className="gap-1.5 border-white/10" onClick={copyLink}>
            <Copy className="h-3.5 w-3.5" /> Copy Link
          </Button>
        </div>
      </Card>

      <div className="grid lg:grid-cols-[1fr_320px] gap-5">
        <Card className="p-4 bg-surface-1 border-white/10">
          <div className="flex items-center justify-between mb-3">
            <p className="font-display font-semibold">{format(month, "MMMM yyyy")}</p>
            <div className="flex items-center gap-1">
              <button data-testid="calendar-prev-month" onClick={() => setMonth(addMonths(month, -1))} className="p-1.5 rounded hover:bg-surface-2 text-graphite hover:text-foreground"><ChevronLeft className="h-4 w-4" /></button>
              <button data-testid="calendar-today" onClick={() => { setMonth(new Date()); setSelectedDay(new Date()); }} className="px-2 py-1 rounded hover:bg-surface-2 text-xs text-graphite hover:text-foreground">Today</button>
              <button data-testid="calendar-next-month" onClick={() => setMonth(addMonths(month, 1))} className="p-1.5 rounded hover:bg-surface-2 text-graphite hover:text-foreground"><ChevronRight className="h-4 w-4" /></button>
            </div>
          </div>
          <div className="grid grid-cols-7 mb-1">
            {WEEKDAY_LABELS.map((d) => <p key={d} className="text-center font-mono text-[10px] uppercase tracking-wider text-carbon py-1">{d}</p>)}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {days.map((day) => {
              const key = format(day, "yyyy-MM-dd");
              const dayEvents = byDay[key] || [];
              const selected = isSameDay(day, selectedDay);
              return (
                <button
                  key={key}
                  data-testid={`calendar-day-${key}`}
                  onClick={() => setSelectedDay(day)}
                  onDoubleClick={() => openCreate(day)}
                  className={`min-h-[76px] rounded-lg border p-1.5 text-left transition-colors flex flex-col gap-1
                    ${selected ? "border-foreground/60 bg-surface-2" : "border-white/5 hover:border-white/20"}
                    ${isSameMonth(day, month) ? "" : "opacity-35"}`}
                >
                  <span className={`text-xs font-mono w-6 h-6 flex items-center justify-center rounded-full
                    ${isToday(day) ? "bg-foreground text-background font-bold" : "text-ash"}`}>
                    {format(day, "d")}
                  </span>
                  <div className="space-y-0.5 overflow-hidden">
                    {dayEvents.slice(0, 2).map((m) => (
                      <p key={m.id} className={`truncate text-[10px] leading-tight px-1 py-0.5 rounded ${m.source === "booking" ? "bg-info/15 text-info" : "bg-surface-2 text-ash"}`}>
                        {format(parseISO(m.start_time), "HH:mm")} {m.title}
                      </p>
                    ))}
                    {dayEvents.length > 2 && <p className="text-[9px] text-graphite px-1">+{dayEvents.length - 2} more</p>}
                  </div>
                </button>
              );
            })}
          </div>
        </Card>

        <Card className="p-4 bg-surface-1 border-white/10 h-fit" data-testid="day-detail-panel">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="font-medium text-sm">{format(selectedDay, "EEEE")}</p>
              <p className="text-xs text-graphite font-mono">{format(selectedDay, "MMMM d, yyyy")}</p>
            </div>
            <Button size="sm" variant="outline" className="gap-1 border-white/10 h-7 text-xs" onClick={() => openCreate()}>
              <Plus className="h-3 w-3" /> Add
            </Button>
          </div>
          {dayMeetings.length === 0 ? (
            <div className="py-8 text-center">
              <CalendarDays className="h-6 w-6 text-carbon mx-auto mb-2" />
              <p className="text-xs text-graphite">Nothing scheduled</p>
            </div>
          ) : (
            <div className="space-y-2">
              {dayMeetings.map((m) => (
                <button
                  key={m.id}
                  data-testid={`day-meeting-${m.id}`}
                  onClick={() => openEdit(m)}
                  className="w-full text-left p-3 rounded-lg bg-surface-2 border border-white/5 hover:border-white/20 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium flex-1 truncate">{m.title}</p>
                    {m.source === "booking" && <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-info/15 text-info uppercase shrink-0">Booked</span>}
                  </div>
                  <p className="text-xs text-graphite font-mono mt-1 flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {format(parseISO(m.start_time), "h:mm a")}{m.end_time ? ` – ${format(parseISO(m.end_time), "h:mm a")}` : ""}
                  </p>
                  {m.location && <p className="text-xs text-graphite flex items-center gap-1 mt-0.5"><MapPin className="h-3 w-3" /> {m.location}</p>}
                  {m.booked_by && <p className="text-xs text-ash flex items-center gap-1 mt-0.5"><Users className="h-3 w-3" /> {m.booked_by.name} · {m.booked_by.email}</p>}
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="meeting-dialog">
          <DialogHeader><DialogTitle>{editTarget ? "Edit Meeting" : "New Meeting"}</DialogTitle></DialogHeader>
          <form onSubmit={submit} className="space-y-3">
            <div className="space-y-1"><Label>Title *</Label><Input data-testid="meeting-form-title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Start *</Label><Input data-testid="meeting-form-start" type="datetime-local" required value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>End</Label><Input data-testid="meeting-form-end" type="datetime-local" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            </div>
            <div className="space-y-1"><Label>Location</Label><Input data-testid="meeting-form-location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1"><Label>Notes</Label><Textarea data-testid="meeting-form-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <DialogFooter className="gap-2">
              {editTarget && (
                <Button type="button" variant="outline" className="border-white/10 text-danger gap-1.5" data-testid="meeting-delete-btn" onClick={() => remove(editTarget.id)}>
                  <Trash2 className="h-3.5 w-3.5" /> Delete
                </Button>
              )}
              <Button type="submit" data-testid="meeting-form-submit">{editTarget ? "Save Changes" : "Schedule Meeting"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={bookingOpen} onOpenChange={setBookingOpen}>
        <DialogContent className="bg-surface-1 border-white/10 max-h-[85vh] overflow-y-auto" data-testid="booking-settings-dialog">
          <DialogHeader>
            <DialogTitle>Booking Page Settings</DialogTitle>
            <DialogDescription>Clients use your booking link to pick a free slot. Slots come from the availability below, minus anything already on your calendar.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Meeting Title</Label><Input value={booking.title || ""} onChange={(e) => setBooking({ ...booking, title: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1">
                <Label>Slot Length</Label>
                <Select value={String(booking.slot_minutes)} onValueChange={(v) => setBooking({ ...booking, slot_minutes: parseInt(v) })}>
                  <SelectTrigger className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent>{[15, 30, 45, 60, 90].map((n) => <SelectItem key={n} value={String(n)}>{n} minutes</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1"><Label>Description (shown to clients)</Label><Textarea value={booking.description || ""} onChange={(e) => setBooking({ ...booking, description: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="space-y-1"><Label>Location / Meeting method</Label><Input value={booking.location || ""} onChange={(e) => setBooking({ ...booking, location: e.target.value })} className="bg-surface-2 border-white/10" placeholder="Google Meet / Phone" /></div>
            <div>
              <Label className="mb-2 block">Weekly Availability</Label>
              <div className="space-y-1.5">
                {WEEKDAY_LABELS.map((label, idx) => {
                  const cfg = booking.days?.[String(idx)] || { enabled: false, start: "10:00", end: "18:00" };
                  return (
                    <div key={label} className="flex items-center gap-3 text-sm">
                      <Switch checked={!!cfg.enabled} onCheckedChange={(v) => setDayCfg(String(idx), { enabled: v })} />
                      <span className="w-10 font-mono text-xs text-ash">{label}</span>
                      <Input type="time" value={cfg.start} disabled={!cfg.enabled} onChange={(e) => setDayCfg(String(idx), { start: e.target.value })} className="bg-surface-2 border-white/10 h-8 w-28" />
                      <span className="text-graphite text-xs">to</span>
                      <Input type="time" value={cfg.end} disabled={!cfg.enabled} onChange={(e) => setDayCfg(String(idx), { end: e.target.value })} className="bg-surface-2 border-white/10 h-8 w-28" />
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              data-testid="booking-settings-save"
              onClick={async () => {
                await saveBooking({
                  title: booking.title, description: booking.description, location: booking.location,
                  slot_minutes: booking.slot_minutes, days: booking.days,
                });
                toast.success("Booking settings saved");
                setBookingOpen(false);
              }}
            >
              Save Settings
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { CalendarDays, Clock, MapPin, CheckCircle2, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { format, addDays, parseISO } from "date-fns";
import { formatApiError } from "@/lib/api";

const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api` });

export default function BookMeeting() {
  const { slug } = useParams();
  const [info, setInfo] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [weekOffset, setWeekOffset] = useState(0);
  const [selectedDate, setSelectedDate] = useState(null);
  const [slots, setSlots] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [form, setForm] = useState({ name: "", email: "", notes: "" });
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/public/booking/${slug}`)
      .then((r) => setInfo(r.data))
      .catch(() => setNotFound(true));
  }, [slug]);

  const days = useMemo(() => {
    if (!info) return [];
    const out = [];
    for (let i = weekOffset * 7; i < weekOffset * 7 + 7; i++) {
      const d = addDays(new Date(), i);
      if (i >= (info.days_ahead || 14)) break;
      out.push(d);
    }
    return out;
  }, [info, weekOffset]);

  const pickDate = async (d) => {
    setSelectedDate(d);
    setSelectedSlot(null);
    setSlots(null);
    setError("");
    const { data } = await api.get(`/public/booking/${slug}/slots`, { params: { date: format(d, "yyyy-MM-dd") } });
    setSlots(data.slots);
  };

  const book = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const { data } = await api.post(`/public/booking/${slug}/book`, { ...form, start_time: selectedSlot });
      setConfirmed(data);
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
      if (err.response?.status === 409 && selectedDate) pickDate(selectedDate);
    } finally {
      setSubmitting(false);
    }
  };

  if (notFound) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <p className="text-graphite">This booking page doesn't exist or has been disabled.</p>
      </div>
    );
  }

  if (!info) {
    return <div className="min-h-screen bg-background flex items-center justify-center"><p className="text-graphite font-mono text-sm">Loading…</p></div>;
  }

  if (confirmed) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6" data-testid="booking-confirmed">
        <Card className="max-w-md w-full p-8 bg-surface-1 border-white/10 text-center">
          <CheckCircle2 className="h-12 w-12 text-success mx-auto mb-4" />
          <h1 className="font-display text-xl font-bold mb-2">You're booked!</h1>
          <p className="text-sm text-ash mb-4">
            {info.title} with {info.company_name}
          </p>
          <div className="rounded-lg bg-surface-2 border border-white/10 p-4 text-left space-y-2 text-sm">
            <p className="flex items-center gap-2"><CalendarDays className="h-4 w-4 text-graphite" /> {format(parseISO(confirmed.start_time), "EEEE, MMMM d, yyyy")}</p>
            <p className="flex items-center gap-2"><Clock className="h-4 w-4 text-graphite" /> {format(parseISO(confirmed.start_time), "h:mm a")} – {format(parseISO(confirmed.end_time), "h:mm a")} (your local time)</p>
          </div>
          <p className="text-xs text-graphite mt-4">A member of the {info.company_name} team will reach out to confirm details.</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground p-6 flex justify-center" data-testid="booking-page">
      <div className="max-w-2xl w-full">
        <div className="text-center mb-8 mt-6">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-foreground text-background font-display font-bold">
            {(info.company_name || "O")[0]}
          </div>
          <h1 className="font-display text-2xl font-bold">{info.title}</h1>
          <p className="text-sm text-graphite mt-1">with {info.company_name}</p>
          <div className="flex items-center justify-center gap-4 mt-3 text-xs text-ash">
            <span className="flex items-center gap-1"><Clock className="h-3.5 w-3.5" /> {info.slot_minutes} min</span>
          </div>
          {info.description && <p className="text-sm text-ash mt-3 max-w-md mx-auto">{info.description}</p>}
        </div>

        <Card className="p-5 bg-surface-1 border-white/10">
          <div className="flex items-center justify-between mb-3">
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">1 · Pick a day</p>
            <div className="flex items-center gap-1">
              <button disabled={weekOffset === 0} onClick={() => setWeekOffset(weekOffset - 1)} className="p-1 rounded hover:bg-surface-2 text-graphite disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button>
              <button disabled={(weekOffset + 1) * 7 >= (info.days_ahead || 14)} onClick={() => setWeekOffset(weekOffset + 1)} className="p-1 rounded hover:bg-surface-2 text-graphite disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button>
            </div>
          </div>
          <div className="grid grid-cols-7 gap-1.5">
            {days.map((d) => {
              const available = info.available_weekdays.includes((d.getDay() + 6) % 7);
              const selected = selectedDate && format(d, "yyyy-MM-dd") === format(selectedDate, "yyyy-MM-dd");
              return (
                <button
                  key={d.toISOString()}
                  data-testid={`book-day-${format(d, "yyyy-MM-dd")}`}
                  disabled={!available}
                  onClick={() => pickDate(d)}
                  className={`rounded-lg border p-2 text-center transition-colors
                    ${selected ? "border-foreground bg-surface-2" : "border-white/10 hover:border-white/30"}
                    ${available ? "" : "opacity-30 cursor-not-allowed"}`}
                >
                  <p className="font-mono text-[9px] uppercase text-graphite">{format(d, "EEE")}</p>
                  <p className="text-sm font-semibold mt-0.5">{format(d, "d")}</p>
                  <p className="font-mono text-[9px] text-carbon">{format(d, "MMM")}</p>
                </button>
              );
            })}
          </div>

          {selectedDate && (
            <div className="mt-5">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite mb-3">2 · Pick a time <span className="text-carbon normal-case tracking-normal">(shown in your local time)</span></p>
              {!slots ? (
                <p className="text-xs text-graphite py-3">Loading times…</p>
              ) : slots.length === 0 ? (
                <p className="text-xs text-graphite py-3">No free slots on this day — try another date.</p>
              ) : (
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-1.5">
                  {slots.map((s) => (
                    <button
                      key={s}
                      data-testid={`book-slot-${s}`}
                      onClick={() => setSelectedSlot(s)}
                      className={`rounded-lg border py-2 text-sm font-mono transition-colors
                        ${selectedSlot === s ? "border-foreground bg-foreground text-background font-semibold" : "border-white/10 hover:border-white/30"}`}
                    >
                      {format(parseISO(s), "h:mm a")}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {selectedSlot && (
            <form onSubmit={book} className="mt-5 space-y-3">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">3 · Your details</p>
              <div className="grid sm:grid-cols-2 gap-3">
                <div className="space-y-1"><Label>Name *</Label><Input data-testid="book-form-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="bg-surface-2 border-white/10" /></div>
                <div className="space-y-1"><Label>Email *</Label><Input data-testid="book-form-email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              </div>
              <div className="space-y-1"><Label>What would you like to discuss?</Label><Textarea data-testid="book-form-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              {error && <p className="text-xs text-danger">{error}</p>}
              <Button data-testid="book-submit" type="submit" disabled={submitting} className="w-full">
                {submitting ? "Booking…" : `Confirm — ${format(parseISO(selectedSlot), "EEE, MMM d · h:mm a")}`}
              </Button>
            </form>
          )}
        </Card>

        <p className="text-center font-mono text-[10px] text-carbon mt-6 tracking-widest uppercase">Powered by {info.company_name}</p>
      </div>
    </div>
  );
}

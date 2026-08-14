import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import axios from "axios";
import { CalendarDays, Clock, MapPin, CheckCircle2, XCircle, ChevronLeft, ChevronRight, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { format, addDays, parseISO } from "date-fns";
import { formatApiError } from "@/lib/api";

const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api` });

// Self-service manage page reached from the booking confirmation email
// (/meeting/:token). The token in the URL is the authorisation — no login —
// so an attendee can view, reschedule or cancel their own meeting and nothing
// else. Reschedule reuses the same public booking-slot endpoints the booking
// page uses, scoped to this meeting's calendar.
export default function ManageMeeting() {
  const { token } = useParams();
  const [searchParams] = useSearchParams();

  const [meeting, setMeeting] = useState(null);
  const [notFound, setNotFound] = useState(false);
  // "view" | "reschedule" | "cancel" | "rescheduled" | "cancelled"
  const [mode, setMode] = useState("view");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Reschedule picker state (mirrors BookMeeting).
  const [info, setInfo] = useState(null);
  const [weekOffset, setWeekOffset] = useState(0);
  const [selectedDate, setSelectedDate] = useState(null);
  const [slots, setSlots] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState(null);

  useEffect(() => {
    api.get(`/public/booking/manage/${token}`)
      .then((r) => {
        setMeeting(r.data);
        const wanted = searchParams.get("action");
        if (r.data.status !== "cancelled" && (wanted === "reschedule" || wanted === "cancel")) {
          setMode(wanted);
        }
      })
      .catch(() => setNotFound(true));
  }, [token, searchParams]);

  // Load the booking calendar only when the attendee starts a reschedule.
  useEffect(() => {
    if (mode === "reschedule" && meeting?.booking_slug && !info) {
      api.get(`/public/booking/${meeting.booking_slug}`)
        .then((r) => setInfo(r.data))
        .catch(() => setError("This meeting can't be rescheduled online. Please reply to your confirmation email."));
    }
  }, [mode, meeting, info]);

  const days = useMemo(() => {
    if (!info) return [];
    const out = [];
    for (let i = weekOffset * 7; i < weekOffset * 7 + 7; i++) {
      if (i >= (info.days_ahead || 14)) break;
      out.push(addDays(new Date(), i));
    }
    return out;
  }, [info, weekOffset]);

  const pickDate = async (d) => {
    setSelectedDate(d);
    setSelectedSlot(null);
    setSlots(null);
    setError("");
    try {
      const { data } = await api.get(`/public/booking/${meeting.booking_slug}/slots`, { params: { date: format(d, "yyyy-MM-dd") } });
      setSlots(data.slots);
    } catch {
      setError("Couldn't load times. Try another day.");
    }
  };

  const doReschedule = async () => {
    setBusy(true);
    setError("");
    try {
      await api.post(`/public/booking/manage/${token}/reschedule`, { start_time: selectedSlot });
      setMode("rescheduled");
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
      if (err.response?.status === 409 && selectedDate) pickDate(selectedDate);
    } finally {
      setBusy(false);
    }
  };

  const doCancel = async () => {
    setBusy(true);
    setError("");
    try {
      await api.post(`/public/booking/manage/${token}/cancel`);
      setMode("cancelled");
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const shell = (children) => (
    <div className="min-h-screen bg-background text-foreground p-6 flex justify-center">
      <div className="max-w-lg w-full mt-8">{children}</div>
    </div>
  );

  if (notFound) {
    return shell(
      <Card className="p-8 bg-surface-1 border-white/10 text-center">
        <XCircle className="h-10 w-10 text-graphite mx-auto mb-4" />
        <p className="text-ash">This meeting link isn't valid or has expired.</p>
      </Card>
    );
  }

  if (!meeting) {
    return <div className="min-h-screen bg-background flex items-center justify-center"><p className="text-graphite font-mono text-sm">Loading…</p></div>;
  }

  const whenLine = (
    <div className="rounded-lg bg-surface-2 border border-white/10 p-4 text-left space-y-2 text-sm">
      <p className="flex items-center gap-2"><CalendarDays className="h-4 w-4 text-graphite" /> {format(parseISO(meeting.start_time), "EEEE, MMMM d, yyyy")}</p>
      <p className="flex items-center gap-2"><Clock className="h-4 w-4 text-graphite" /> {format(parseISO(meeting.start_time), "h:mm a")}{meeting.end_time ? ` – ${format(parseISO(meeting.end_time), "h:mm a")}` : ""} (your local time)</p>
      {meeting.location && <p className="flex items-center gap-2"><MapPin className="h-4 w-4 text-graphite" /> {meeting.location}</p>}
    </div>
  );

  if (mode === "rescheduled") {
    return shell(
      <Card className="p-8 bg-surface-1 border-white/10 text-center" data-testid="reschedule-done">
        <CheckCircle2 className="h-12 w-12 text-success mx-auto mb-4" />
        <h1 className="font-display text-xl font-bold mb-2">Rescheduled</h1>
        <p className="text-sm text-ash mb-4">We've emailed you the new details.</p>
      </Card>
    );
  }

  if (mode === "cancelled" || meeting.status === "cancelled") {
    return shell(
      <Card className="p-8 bg-surface-1 border-white/10 text-center" data-testid="cancel-done">
        <XCircle className="h-12 w-12 text-danger mx-auto mb-4" />
        <h1 className="font-display text-xl font-bold mb-2">Meeting cancelled</h1>
        <p className="text-sm text-ash">Your {meeting.title} has been cancelled. You can book again any time.</p>
      </Card>
    );
  }

  if (mode === "cancel") {
    return shell(
      <Card className="p-6 bg-surface-1 border-white/10">
        <button onClick={() => { setMode("view"); setError(""); }} className="flex items-center gap-1 text-xs text-graphite mb-4 hover:text-foreground"><ArrowLeft className="h-3.5 w-3.5" /> Back</button>
        <h1 className="font-display text-xl font-bold mb-2">Cancel this meeting?</h1>
        <p className="text-sm text-ash mb-4">{meeting.title}</p>
        {whenLine}
        {error && <p className="text-xs text-danger mt-3">{error}</p>}
        <div className="flex gap-2 mt-5">
          <Button variant="destructive" disabled={busy} onClick={doCancel} data-testid="confirm-cancel" className="flex-1">
            {busy ? "Cancelling…" : "Yes, cancel it"}
          </Button>
          <Button variant="outline" disabled={busy} onClick={() => setMode("view")} className="flex-1">Keep it</Button>
        </div>
      </Card>
    );
  }

  if (mode === "reschedule") {
    return shell(
      <Card className="p-5 bg-surface-1 border-white/10">
        <button onClick={() => { setMode("view"); setError(""); }} className="flex items-center gap-1 text-xs text-graphite mb-4 hover:text-foreground"><ArrowLeft className="h-3.5 w-3.5" /> Back</button>
        <h1 className="font-display text-xl font-bold mb-1">Pick a new time</h1>
        <p className="text-sm text-graphite mb-4">Currently {format(parseISO(meeting.start_time), "EEE, MMM d · h:mm a")}</p>

        {!info ? (
          <p className="text-xs text-graphite py-3">{error || "Loading availability…"}</p>
        ) : (
          <>
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
                  <button key={d.toISOString()} disabled={!available} onClick={() => pickDate(d)}
                    className={`rounded-lg border p-2 text-center transition-colors
                      ${selected ? "border-foreground bg-surface-2" : "border-white/10 hover:border-white/30"}
                      ${available ? "" : "opacity-30 cursor-not-allowed"}`}>
                    <p className="font-mono text-[9px] uppercase text-graphite">{format(d, "EEE")}</p>
                    <p className="text-sm font-semibold mt-0.5">{format(d, "d")}</p>
                    <p className="font-mono text-[9px] text-carbon">{format(d, "MMM")}</p>
                  </button>
                );
              })}
            </div>

            {selectedDate && (
              <div className="mt-5">
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite mb-3">2 · Pick a time</p>
                {!slots ? (
                  <p className="text-xs text-graphite py-3">Loading times…</p>
                ) : slots.length === 0 ? (
                  <p className="text-xs text-graphite py-3">No free slots on this day — try another date.</p>
                ) : (
                  <div className="grid grid-cols-3 sm:grid-cols-4 gap-1.5">
                    {slots.map((s) => (
                      <button key={s} onClick={() => setSelectedSlot(s)}
                        className={`rounded-lg border py-2 text-sm font-mono transition-colors
                          ${selectedSlot === s ? "border-foreground bg-foreground text-background font-semibold" : "border-white/10 hover:border-white/30"}`}>
                        {format(parseISO(s), "h:mm a")}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {error && <p className="text-xs text-danger mt-3">{error}</p>}

            {selectedSlot && (
              <Button disabled={busy} onClick={doReschedule} data-testid="confirm-reschedule" className="w-full mt-5">
                {busy ? "Moving…" : `Move to ${format(parseISO(selectedSlot), "EEE, MMM d · h:mm a")}`}
              </Button>
            )}
          </>
        )}
      </Card>
    );
  }

  // Default view.
  return shell(
    <Card className="p-6 bg-surface-1 border-white/10" data-testid="manage-view">
      <h1 className="font-display text-xl font-bold mb-1">Your meeting</h1>
      <p className="text-sm text-graphite mb-4">{meeting.title}{meeting.company_name ? ` · ${meeting.company_name}` : ""}</p>
      {whenLine}
      <div className="flex gap-2 mt-5">
        {meeting.can_reschedule && (
          <Button onClick={() => setMode("reschedule")} data-testid="start-reschedule" className="flex-1">Reschedule</Button>
        )}
        <Button variant="outline" onClick={() => setMode("cancel")} data-testid="start-cancel" className="flex-1">Cancel</Button>
      </div>
      <p className="text-center font-mono text-[10px] text-carbon mt-6 tracking-widest uppercase">Powered by {meeting.company_name || "Obrinex"}</p>
    </Card>
  );
}

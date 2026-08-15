import { useEffect, useState } from "react";
import { Users, CheckCircle2, XCircle, Loader2, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import SeatRail from "@/components/founding/SeatRail";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";

// Mirrors backend/founding.py QUALITATIVE_MAX. The ceilings are enforced
// server-side too — this only stops the input going obviously out of range.
const AXES = [
  { key: "clarity", label: "Clarity of the bottleneck", max: 10 },
  { key: "self_awareness", label: "What they already tried", max: 10 },
  { key: "work_quality", label: "Quality of linked work", max: 10 },
  { key: "fit", label: "Fit for this circle", max: 5 },
];

const STATUS_TONE = {
  pending: "text-graphite",
  approved: "text-success",
  rejected: "text-danger",
};

export default function FoundingReview() {
  const [overview, setOverview] = useState(null);
  const [applications, setApplications] = useState(null);
  const [active, setActive] = useState(null);
  const [ratings, setRatings] = useState({});
  const [busy, setBusy] = useState(false);
  /** The application the delete dialog is asking about, if any. */
  const [deleting, setDeleting] = useState(null);
  const [confirmText, setConfirmText] = useState("");

  const load = async () => {
    const [o, a] = await Promise.all([
      api.get("/founding/overview"),
      api.get("/founding/applications"),
    ]);
    setOverview(o.data);
    setApplications(a.data);
  };

  useEffect(() => { load(); }, []);

  const open = (application) => {
    setActive(application);
    setRatings(application.ratings || {});
  };

  const saveRatings = async () => {
    setBusy(true);
    try {
      const { data } = await api.patch(`/founding/applications/${active.id}/ratings`, {
        clarity: Number(ratings.clarity) || 0,
        self_awareness: Number(ratings.self_awareness) || 0,
        work_quality: Number(ratings.work_quality) || 0,
        fit: Number(ratings.fit) || 0,
      });
      toast.success(`Scored ${data.score.total}/${overview.score_max}`);
      await load();
      setActive((prev) => ({ ...prev, ratings: data.ratings, score: data.score }));
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const decide = async (decision) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/founding/applications/${active.id}/decide`, { decision });
      // The decision is committed before the email is attempted, so a mail
      // outage must be reported without implying the decision failed.
      toast[data.email_sent ? "success" : "warning"](
        data.email_sent
          ? `${decision === "approved" ? "Approved" : "Rejected"} — they've been emailed.`
          : `${decision === "approved" ? "Approved" : "Rejected"}, but the email did not send. Contact them directly.`
      );
      setActive(null);
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const confirmDelete = async () => {
    setBusy(true);
    try {
      const { data } = await api.delete(`/founding/applications/${deleting.id}`);
      // Say what actually happened rather than "Deleted". Freeing a seat and
      // reopening an intake are consequences worth hearing about, and both are
      // easy to not realise you just caused.
      const extra = [
        data.was_status === "approved" && `Seat freed — ${data.seats_remaining} open.`,
        data.had_account && "Their login was removed.",
        data.round_reopened && "The intake reopened.",
      ].filter(Boolean).join(" ");
      toast.success(`Application deleted.${extra ? ` ${extra}` : ""}`);
      if (active?.id === deleting.id) setActive(null);
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
      setDeleting(null);
      setConfirmText("");
    }
  };

  if (!overview || !applications) {
    return <div className="p-6 space-y-4"><Skeleton className="h-24 bg-surface-1" /><Skeleton className="h-64 bg-surface-1" /></div>;
  }

  const pending = applications.filter((a) => a.status === "pending");

  return (
    <div className="p-6 space-y-5" data-testid="founding-review-page">
      <PageHeader
        title="Founding Circle"
        description={`${overview.round_label} intake · ${overview.received}/${overview.application_cap} applications · ${overview.seats_remaining} of ${overview.seats_total} seats left`}
      />

      <SeatRail taken={overview.approved} total={overview.seats_total}
                label={`${overview.round_label} intake`} totalMembers={overview.total_members} />

      <div className="grid gap-3 sm:grid-cols-4">
        {[
          { label: "Seats left", value: overview.seats_remaining, testId: "founding-seats" },
          { label: "Pending", value: overview.pending, testId: "founding-pending" },
          { label: "Approved", value: overview.approved, testId: "founding-approved" },
          { label: "Intake", value: overview.round_status === "open" ? "Open" : "Closed", testId: "founding-round-status" },
        ].map((s) => (
          <Card key={s.label} className="p-4 bg-surface-1 border-white/10" data-testid={s.testId}>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">{s.label}</p>
            <p className="font-display text-2xl font-bold mt-1">{s.value}</p>
          </Card>
        ))}
      </div>

      {overview.round_status !== "open" && (
        <Card className="p-3 bg-surface-1 border-warning/30 text-sm text-graphite">
          This intake is closed ({overview.closed_reason === "cap_reached" ? "it filled up" : "the quarter ended"}).
          The next one opens at the start of the quarter.
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-[1fr_1.2fr]">
        <div className="space-y-2">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">
            Applications · highest score first
          </p>
          {applications.length === 0 && (
            <EmptyState icon={Users} title="No applications yet"
                        description="They'll appear here as they come in from the website." />
          )}
          {/* A row is a div holding two buttons rather than one button, because
              the delete control has to live inside it and a button cannot
              contain another button. The outer div is not itself clickable —
              the row's own button fills it. */}
          {applications.map((a) => (
            <div
              key={a.id}
              className={`group flex items-center rounded-lg border transition-colors ${
                active?.id === a.id ? "border-accent/60 bg-accent/5" : "border-white/10 bg-surface-1 hover:border-white/25"
              }`}
            >
              <button
                onClick={() => open(a)}
                data-testid={`founding-application-${a.id}`}
                className="min-w-0 flex-1 text-left p-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium truncate">{a.answers?.company || a.name}</span>
                  <span className="font-mono text-sm shrink-0">
                    {a.score?.total ?? 0}
                    <span className="text-carbon">/{overview.score_max}</span>
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-2 text-[11px]">
                  <span className={`font-mono uppercase ${STATUS_TONE[a.status]}`}>{a.status}</span>
                  {!a.score?.reviewed && a.status === "pending" && (
                    <span className="text-carbon">· not yet reviewed</span>
                  )}
                </div>
              </button>
              {/* Hidden until the row is hovered or the control is focused, so
                  a list you are scanning does not read as a row of delete
                  buttons. focus-visible keeps it reachable by keyboard. */}
              <button
                onClick={() => { setDeleting(a); setConfirmText(""); }}
                title="Delete this application"
                aria-label={`Delete the application from ${a.answers?.company || a.name}`}
                data-testid={`founding-delete-${a.id}`}
                className="mr-2 shrink-0 rounded p-2 text-carbon opacity-0 transition-opacity hover:text-danger focus-visible:opacity-100 group-hover:opacity-100"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>

        {active ? (
          <Card className="p-5 bg-surface-1 border-white/10 space-y-4" data-testid="founding-detail">
            <div>
              <h2 className="font-display text-xl font-bold">{active.answers?.company || active.name}</h2>
              <p className="text-sm text-graphite">{active.name} · {active.email}</p>
            </div>

            <div className="grid grid-cols-2 gap-2 text-sm">
              {["revenue_band", "tenure_band", "team_band", "commitment_band"].map((k) => (
                <div key={k} className="rounded-lg bg-surface-2 border border-white/10 p-2">
                  <p className="font-mono text-[10px] uppercase text-graphite">{k.replace("_band", "").replace("_", " ")}</p>
                  <p>{active.answers?.[k] || "—"}</p>
                </div>
              ))}
            </div>

            {[
              ["One-liner", active.answers?.one_liner],
              ["Biggest bottleneck", active.answers?.bottleneck],
              ["Already tried", active.answers?.already_tried],
              ["First 90 days", active.answers?.first_90_days],
              ["Website", active.answers?.website],
              ["Best work", active.answers?.best_work],
            ].filter(([, v]) => v).map(([label, value]) => (
              <div key={label}>
                <p className="font-mono text-[10px] uppercase tracking-wide text-graphite mb-1">{label}</p>
                <p className="text-sm text-ash whitespace-pre-line break-words">{value}</p>
              </div>
            ))}

            {active.status === "pending" ? (
              <>
                <div className="border-t border-white/10 pt-4 space-y-3">
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">
                    Your rating · 35 of the 100 points
                  </p>
                  {AXES.map((axis) => (
                    <div key={axis.key} className="flex items-center gap-3">
                      <Label className="flex-1 text-sm font-normal">{axis.label}</Label>
                      <Input
                        type="number" min={0} max={axis.max}
                        data-testid={`founding-rating-${axis.key}`}
                        value={ratings[axis.key] ?? ""}
                        onChange={(e) => setRatings({ ...ratings, [axis.key]: e.target.value })}
                        className="w-20 bg-surface-2 border-white/10"
                      />
                      <span className="w-8 text-xs text-carbon">/{axis.max}</span>
                    </div>
                  ))}
                  <Button size="sm" variant="outline" className="border-white/10"
                          onClick={saveRatings} disabled={busy} data-testid="founding-save-ratings">
                    Save rating
                  </Button>
                </div>

                <div className="border-t border-white/10 pt-4 flex items-center gap-2">
                  <Button
                    onClick={() => decide("approved")}
                    disabled={busy || overview.seats_remaining === 0}
                    title={overview.seats_remaining === 0 ? "This intake is full — the next opens next quarter" : undefined}
                    data-testid="founding-approve"
                    className="gap-1.5"
                  >
                    {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                    Approve
                  </Button>
                  <Button
                    variant="outline" onClick={() => decide("rejected")} disabled={busy}
                    data-testid="founding-reject"
                    className="gap-1.5 border-danger/30 text-danger hover:bg-danger/10 hover:text-danger"
                  >
                    <XCircle className="h-3.5 w-3.5" /> Reject
                  </Button>
                  <span className="text-xs text-carbon ml-auto">Either way, they get an email.</span>
                </div>
              </>
            ) : (
              <div className="border-t border-white/10 pt-4 text-sm">
                <span className={`font-mono uppercase ${STATUS_TONE[active.status]}`}>{active.status}</span>
                <span className="text-graphite"> · {String(active.decided_at || "").slice(0, 10)}</span>
              </div>
            )}

            {/* Deleting is available whatever the status, and sits apart from
                the decision controls — it is not a third verdict. Approve and
                Reject are answers to the applicant; this is housekeeping. */}
            <div className="border-t border-white/10 pt-4 flex items-center justify-between gap-3">
              <p className="text-xs text-carbon">
                Deleting erases the application for good.
                {active.status === "approved" && " Their seat and login go with it."}
              </p>
              <Button
                size="sm" variant="ghost"
                onClick={() => { setDeleting(active); setConfirmText(""); }}
                disabled={busy}
                data-testid="founding-delete-active"
                className="shrink-0 gap-1.5 text-carbon hover:bg-danger/10 hover:text-danger"
              >
                <Trash2 className="h-3.5 w-3.5" /> Delete
              </Button>
            </div>
          </Card>
        ) : (
          <Card className="p-8 bg-surface-1 border-white/10 flex items-center justify-center">
            <p className="text-sm text-graphite">Select an application to review it.</p>
          </Card>
        )}
      </div>

      {/* Type-to-confirm rather than a plain OK, matching Members. There is no
          undo behind this: the row is gone, not flagged. */}
      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="founding-delete-dialog">
          <DialogHeader>
            <DialogTitle className="text-danger">Delete this application?</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p className="text-graphite">
              <span className="text-ash">{deleting?.answers?.company || deleting?.name}</span>
              {" "}({deleting?.email}) is erased for good. This cannot be undone.
            </p>

            {deleting?.status === "approved" && (
              <p className="rounded-lg border border-warning/30 bg-warning/5 p-2 text-xs text-warning">
                They are a member. Their seat returns to the pool and their portal
                login is deleted. If you only want the seat back, close this and
                use Remove on the Members page instead — that keeps the record.
              </p>
            )}
            {deleting?.status === "pending" && (
              <p className="text-xs text-carbon">
                They have not been told anything either way. Deleting sends no email.
              </p>
            )}

            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="DELETE"
              autoComplete="off"
              className="bg-surface-2 border-white/10 font-mono"
              data-testid="founding-delete-confirm"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" className="border-white/10"
                    onClick={() => setDeleting(null)}>Cancel</Button>
            <Button className="bg-danger text-white hover:bg-danger/90"
                    disabled={confirmText !== "DELETE" || busy}
                    onClick={confirmDelete}
                    data-testid="founding-delete-submit">
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Delete for good"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

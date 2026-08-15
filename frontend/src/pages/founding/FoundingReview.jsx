import { useEffect, useState } from "react";
import { Users, CheckCircle2, XCircle, Loader2 } from "lucide-react";
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
          {applications.map((a) => (
            <button
              key={a.id}
              onClick={() => open(a)}
              data-testid={`founding-application-${a.id}`}
              className={`w-full text-left rounded-lg border p-3 transition-colors ${
                active?.id === a.id ? "border-accent/60 bg-accent/5" : "border-white/10 bg-surface-1 hover:border-white/25"
              }`}
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
          </Card>
        ) : (
          <Card className="p-8 bg-surface-1 border-white/10 flex items-center justify-center">
            <p className="text-sm text-graphite">Select an application to review it.</p>
          </Card>
        )}
      </div>
    </div>
  );
}

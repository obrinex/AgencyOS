import { useCallback, useEffect, useState } from "react";
import {
  Inbox, Send, CheckCircle2, XCircle, RotateCcw, Loader2, FlaskConical,
  Radio, Play, MailQuestion,
} from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import { format } from "date-fns";
import { toast } from "sonner";

const MESSAGE_STATUS_STYLE = {
  awaiting_approval: "bg-warning/15 text-warning",
  approved: "bg-info/15 text-info",
  sending: "bg-info/15 text-info",
  sent: "bg-success/15 text-success",
  delivered: "bg-success/15 text-success",
  bounced: "bg-danger/15 text-danger",
  complained: "bg-danger/15 text-danger",
  failed: "bg-danger/15 text-danger",
  rejected: "bg-surface-3 text-graphite",
  cancelled: "bg-surface-3 text-graphite",
  needs_review: "bg-danger/15 text-danger",
};

export default function SDROutreach() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [pending, setPending] = useState(null);
  const [recent, setRecent] = useState(null);
  const [needsReview, setNeedsReview] = useState(null);
  const [settings, setSettings] = useState(null);
  const [busy, setBusy] = useState(false);
  const [liveConfirm, setLiveConfirm] = useState(false);

  // The draft being reviewed, with editable copy.
  const [reviewing, setReviewing] = useState(null);
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");

  const load = useCallback(async () => {
    const [p, r, n, s] = await Promise.all([
      api.get("/sdr/messages?status=awaiting_approval&limit=100"),
      api.get("/sdr/messages?limit=50"),
      api.get("/sdr/messages?status=needs_review&limit=50"),
      api.get("/sdr/settings"),
    ]);
    setPending(p.data.items);
    setRecent(r.data.items);
    setNeedsReview(n.data.items);
    setSettings(s.data);
  }, []);

  useEffect(() => { load(); }, [load]);

  const openReview = (message) => {
    setReviewing(message);
    setEditSubject(message.subject);
    setEditBody(message.body);
  };

  const approve = async () => {
    setBusy(true);
    try {
      const edited = editSubject !== reviewing.subject || editBody !== reviewing.body;
      await api.post(`/sdr/messages/${reviewing.id}/approve`,
        edited ? { subject: editSubject, body: editBody } : {});
      toast.success("Approved — it sends in the recipient's next business-hours window");
      setReviewing(null);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const reject = async (regenerate) => {
    setBusy(true);
    try {
      await api.post(`/sdr/messages/${reviewing.id}/reject`, { regenerate });
      toast.success(regenerate
        ? "Rejected — a fresh draft will be written on the next run"
        : "Rejected — this lead's sequence has been stopped");
      setReviewing(null);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const runQueue = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/sdr/jobs/drain");
      const tick = data.tick || {};
      toast.success(
        `Tick: ${tick.personalization_queued ?? 0} drafts queued, ` +
        `${tick.sends_queued ?? 0} sends queued · processed ${data.processed}`
      );
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const setSendMode = async (mode) => {
    setBusy(true);
    try {
      await api.put("/sdr/settings", { send_mode: mode });
      toast.success(mode === "live"
        ? "LIVE — approved messages now go to real inboxes"
        : "Simulate — the pipeline runs but no email leaves");
      setLiveConfirm(false);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  if (!pending || !settings) {
    return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;
  }

  const simulate = settings.send_mode !== "live";

  return (
    <div className="p-6 space-y-5" data-testid="sdr-outreach-page">
      <PageHeader
        title="Outreach"
        description="Every drafted email, waiting for your yes"
        actions={
          <div className="flex items-center gap-2">
            {isAdmin && (
              <Button
                size="sm" variant="outline"
                data-testid="sdr-send-mode-btn"
                disabled={busy}
                className={simulate
                  ? "border-info/40 text-info hover:text-info gap-1.5"
                  : "border-danger/40 text-danger hover:text-danger gap-1.5"}
                onClick={() => (simulate ? setLiveConfirm(true) : setSendMode("simulate"))}
              >
                {simulate ? <FlaskConical className="h-3.5 w-3.5" /> : <Radio className="h-3.5 w-3.5" />}
                {simulate ? "Simulate mode" : "LIVE"}
              </Button>
            )}
            <Button size="sm" data-testid="sdr-run-queue-btn" disabled={busy}
                    className="gap-1.5" onClick={runQueue}>
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              Run queue now
            </Button>
          </div>
        }
      />

      {simulate && (
        <Card className="p-4 bg-info/10 border-info/20" data-testid="sdr-simulate-banner">
          <p className="text-sm text-info flex items-center gap-2">
            <FlaskConical className="h-4 w-4" /> Simulate mode — the whole pipeline runs,
            but nothing is actually emailed.
          </p>
          <p className="text-xs text-graphite mt-1">
            Messages marked “sent” here were rehearsals. Flip to live only when a sending
            identity has passed DNS and finished warm-up.
          </p>
        </Card>
      )}

      {needsReview?.length > 0 && (
        <Card className="p-4 bg-danger/10 border-danger/20" data-testid="sdr-needs-review-banner">
          <p className="text-sm text-danger flex items-center gap-2">
            <MailQuestion className="h-4 w-4" />
            {needsReview.length} send{needsReview.length === 1 ? "" : "s"} with an unknown outcome
          </p>
          <p className="text-xs text-graphite mt-1">
            A send attempt did not record a result. Check the provider dashboard for the
            recipient before doing anything — replaying blind risks a duplicate email.
          </p>
        </Card>
      )}

      <Tabs defaultValue="queue">
        <TabsList className="bg-surface-2">
          <TabsTrigger value="queue" data-testid="sdr-tab-approval">
            Approval queue{pending.length ? ` (${pending.length})` : ""}
          </TabsTrigger>
          <TabsTrigger value="log" data-testid="sdr-tab-log">Message log</TabsTrigger>
        </TabsList>

        <TabsContent value="queue" className="mt-4">
          {pending.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title="Nothing waiting for approval"
              description="When a campaign runs, every drafted email lands here for your review before it can send."
              testId="sdr-approval-empty"
            />
          ) : (
            <div className="space-y-2" data-testid="sdr-approval-list">
              {pending.map((message) => (
                <button
                  key={message.id}
                  data-testid={`sdr-pending-${message.id}`}
                  onClick={() => openReview(message)}
                  className="w-full text-left rounded-lg border border-white/10 bg-surface-1 px-4 py-3 hover:border-white/25"
                >
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-medium text-sm truncate flex-1 min-w-0">
                      {message.subject}
                    </span>
                    <span className="font-mono text-[11px] text-carbon">{message.to_email}</span>
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded uppercase bg-surface-2 text-graphite">
                      step {message.step_index + 1}
                    </span>
                  </div>
                  <p className="text-xs text-graphite mt-1 line-clamp-2">{message.body}</p>
                </button>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="log" className="mt-4">
          {!recent?.length ? (
            <EmptyState
              icon={Send}
              title="No messages yet"
              description="Everything drafted, sent, bounced or cancelled shows up here with its full history."
              testId="sdr-log-empty"
            />
          ) : (
            <div className="space-y-2" data-testid="sdr-message-log">
              {recent.map((message) => (
                <div
                  key={message.id}
                  className="flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-surface-1 px-4 py-2.5"
                  data-testid={`sdr-message-${message.id}`}
                >
                  <span className="text-sm truncate flex-1 min-w-0">{message.subject}</span>
                  <span className="font-mono text-[11px] text-carbon truncate">{message.to_email}</span>
                  {message.simulated && (
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded uppercase bg-info/15 text-info">
                      simulated
                    </span>
                  )}
                  {message.sent_at && (
                    <span className="font-mono text-[11px] text-carbon hidden sm:block">
                      {format(new Date(message.sent_at), "MMM d, HH:mm")}
                    </span>
                  )}
                  <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${MESSAGE_STATUS_STYLE[message.status] || "bg-surface-2 text-ash"}`}>
                    {message.status.replace(/_/g, " ")}
                  </span>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Review one draft */}
      <Dialog open={!!reviewing} onOpenChange={(open) => !open && setReviewing(null)}>
        <DialogContent className="bg-surface-1 border-white/10 max-w-2xl" data-testid="sdr-review-dialog">
          <DialogHeader>
            <DialogTitle className="pr-8">
              To {reviewing?.to_email} · step {(reviewing?.step_index ?? 0) + 1}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>Subject</Label>
              <Input data-testid="sdr-review-subject" value={editSubject}
                     onChange={(e) => setEditSubject(e.target.value)}
                     className="bg-surface-2 border-white/10" />
            </div>
            <div className="space-y-1">
              <Label>Body</Label>
              <Textarea data-testid="sdr-review-body" value={editBody} rows={9}
                        onChange={(e) => setEditBody(e.target.value)}
                        className="bg-surface-2 border-white/10 text-sm" />
            </div>
            {reviewing?.cited_facts?.length > 0 && (
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon mb-1">
                  Facts this draft is grounded in
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {reviewing.cited_facts.map((fact, index) => (
                    <span key={index} className="font-mono text-[10px] px-2 py-0.5 rounded bg-surface-2 text-ash border border-white/10">
                      {fact}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <p className="text-[11px] text-carbon">
              The unsubscribe footer and one-click headers are added at send time — you are
              approving the words, the system supplies the legal frame.
            </p>
          </div>
          <DialogFooter className="flex-wrap gap-2">
            <Button variant="outline" disabled={busy}
                    className="border-white/10 gap-1.5"
                    data-testid="sdr-reject-regenerate"
                    onClick={() => reject(true)}>
              <RotateCcw className="h-3.5 w-3.5" /> Reject, rewrite
            </Button>
            <Button variant="outline" disabled={busy}
                    className="border-danger/40 text-danger hover:text-danger gap-1.5"
                    data-testid="sdr-reject-stop"
                    onClick={() => reject(false)}>
              <XCircle className="h-3.5 w-3.5" /> Reject, stop sequence
            </Button>
            <Button disabled={busy} data-testid="sdr-approve-btn" className="gap-1.5" onClick={approve}>
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
              Approve
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Going live is the consequential direction; it gets a real confirm. */}
      <Dialog open={liveConfirm} onOpenChange={setLiveConfirm}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="sdr-live-confirm">
          <DialogHeader><DialogTitle>Switch to LIVE sending?</DialogTitle></DialogHeader>
          <p className="text-sm text-graphite">
            Approved messages will be delivered to real inboxes through Resend. Only do
            this once a sending identity has passed all DNS checks and warm-up is under
            way — sending from a cold or unverified domain damages its reputation for weeks.
          </p>
          <DialogFooter>
            <Button variant="outline" className="border-white/10" onClick={() => setLiveConfirm(false)}>
              Cancel
            </Button>
            <Button variant="destructive" disabled={busy} data-testid="sdr-live-confirm-btn"
                    onClick={() => setSendMode("live")} className="gap-1.5">
              <Radio className="h-3.5 w-3.5" /> Go live
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

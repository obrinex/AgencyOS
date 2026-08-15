import { useEffect, useState } from "react";
import { ShieldCheck, ShieldOff, Mail, UserMinus, Loader2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import SeatRail from "@/components/founding/SeatRail";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";

const ACCESS = {
  active: { label: "Active", tone: "text-success", note: "Can sign in" },
  revoked: { label: "Revoked", tone: "text-danger", note: "Signed out, seat kept" },
  pending: { label: "Invite sent", tone: "text-warning", note: "Hasn't set a password" },
};

export default function FoundingMembers() {
  const [members, setMembers] = useState(null);
  const [overview, setOverview] = useState(null);
  const [busy, setBusy] = useState(null);
  const [removing, setRemoving] = useState(null);
  const [confirmText, setConfirmText] = useState("");

  const load = async () => {
    const [m, o] = await Promise.all([
      api.get("/founding/members"),
      api.get("/founding/overview"),
    ]);
    setMembers(m.data);
    setOverview(o.data);
  };

  useEffect(() => { load(); }, []);

  const act = async (member, path, body, success) => {
    setBusy(member.id);
    try {
      const { data } = await api.post(`/founding/members/${member.id}/${path}`, body);
      toast.success(typeof success === "function" ? success(data) : success);
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setBusy(null); }
  };

  const confirmRemove = async () => {
    await act(removing, "remove", {}, (d) => `Seat returned. ${d.seats_remaining} of ${overview.seats_total} open.`);
    setRemoving(null);
    setConfirmText("");
  };

  if (!members || !overview) {
    return <div className="p-6 space-y-4"><Skeleton className="h-28 bg-surface-1" /><Skeleton className="h-72 bg-surface-1" /></div>;
  }

  return (
    <div className="p-6 space-y-6" data-testid="founding-members-page">
      <PageHeader
        title="Members"
        description="Ten seats. Access is yours to give and take back."
      />

      <SeatRail taken={overview.approved} total={overview.seats_total} />

      {members.length === 0 && (
        <Card className="p-10 bg-surface-1 border-white/10 text-center">
          <p className="text-sm text-graphite">No members yet. Approve an application to fill the first seat.</p>
        </Card>
      )}

      <div className="space-y-2">
        {members.map((m, index) => {
          const state = ACCESS[m.access] || ACCESS.pending;
          return (
            <Card
              key={m.id}
              data-testid={`founding-member-${m.id}`}
              className="bg-surface-1 border-white/10 p-4 flex flex-wrap items-center gap-4"
            >
              {/* The seat number is the point of the whole thing — one of ten,
                  in the order they joined. */}
              <span className="font-mono text-[11px] text-carbon w-8 shrink-0">
                {String(index + 1).padStart(2, "0")}
              </span>

              <div className="min-w-0 flex-1">
                <p className="font-display text-base font-semibold truncate">
                  {m.company || m.name}
                </p>
                <p className="text-xs text-graphite truncate">{m.name} · {m.email}</p>
              </div>

              <div className="text-right shrink-0">
                <p className={`font-mono text-[11px] uppercase tracking-wide ${state.tone}`}
                   data-testid={`founding-access-${m.id}`}>
                  {state.label}
                </p>
                <p className="text-[11px] text-carbon">{state.note}</p>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {m.access === "pending" && (
                  <Button size="sm" variant="outline" className="gap-1.5 border-white/10"
                          disabled={busy === m.id}
                          onClick={() => act(m, "reinvite", {},
                            (d) => d.email_sent ? "Invite re-sent." : "New link made, but the email didn't send.")}
                          data-testid={`founding-reinvite-${m.id}`}>
                    <Mail className="h-3.5 w-3.5" /> Re-invite
                  </Button>
                )}
                {m.access === "active" && (
                  <Button size="sm" variant="outline"
                          className="gap-1.5 border-white/10 text-danger hover:bg-danger/10 hover:text-danger"
                          disabled={busy === m.id}
                          onClick={() => act(m, "access", { active: false }, "Access revoked.")}
                          data-testid={`founding-revoke-${m.id}`}>
                    <ShieldOff className="h-3.5 w-3.5" /> Revoke
                  </Button>
                )}
                {m.access === "revoked" && (
                  <Button size="sm" variant="outline" className="gap-1.5 border-white/10"
                          disabled={busy === m.id}
                          onClick={() => act(m, "access", { active: true }, "Access restored.")}
                          data-testid={`founding-restore-${m.id}`}>
                    <ShieldCheck className="h-3.5 w-3.5" /> Restore
                  </Button>
                )}
                <Button size="icon" variant="ghost" title="Remove from the circle"
                        className="text-carbon hover:text-danger"
                        disabled={busy === m.id}
                        onClick={() => { setRemoving(m); setConfirmText(""); }}
                        data-testid={`founding-remove-${m.id}`}>
                  {busy === m.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserMinus className="h-4 w-4" />}
                </Button>
              </div>
            </Card>
          );
        })}
      </div>

      <p className="text-xs text-carbon">
        Revoking blocks the login and keeps the seat. Removing returns the seat to the pool.
      </p>

      <Dialog open={!!removing} onOpenChange={(o) => !o && setRemoving(null)}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="founding-remove-dialog">
          <DialogHeader><DialogTitle className="text-danger">Return this seat?</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm">
            <p className="text-graphite">
              <span className="text-ash">{removing?.company || removing?.name}</span> loses
              their portal login and stops being one of the ten. Their messages in the
              community stay.
            </p>
            <p className="text-xs text-carbon">
              If you only want to suspend them, close this and use Revoke instead — that
              keeps the seat.
            </p>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="REMOVE"
              autoComplete="off"
              className="bg-surface-2 border-white/10 font-mono"
              data-testid="founding-remove-confirm"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" className="border-white/10"
                    onClick={() => setRemoving(null)}>Cancel</Button>
            <Button className="bg-danger text-white hover:bg-danger/90"
                    disabled={confirmText !== "REMOVE"}
                    onClick={confirmRemove}
                    data-testid="founding-remove-submit">
              Return the seat
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

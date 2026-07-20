import { useEffect, useState } from "react";
import {
  AlertTriangle, Bot, CheckCircle2, Link2, Loader2, User,
} from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  INBOUND_CATEGORY_CONFIG, INBOUND_CATEGORY_STYLE, MATCH_METHOD_CONFIG,
} from "@/lib/sdrConfig";
import { format } from "date-fns";
import { toast } from "sonner";

function Section({ label, children }) {
  return (
    <div className="space-y-1.5">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">{label}</p>
      {children}
    </div>
  );
}

export default function InboundDrawer({ inboundId, open, onOpenChange, onChanged }) {
  const [data, setData] = useState(null);
  const [override, setOverride] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !inboundId) return;
    // Reset first so the previous reply never shows under the new heading.
    setData(null);
    setOverride("");
    (async () => {
      const { data: detail } = await api.get(`/sdr/inbox/${inboundId}`);
      setData(detail);
      setOverride(detail.category || "");
    })();
  }, [open, inboundId]);

  const reclassify = async () => {
    setBusy(true);
    try {
      const { data: result } = await api.post(`/sdr/inbox/${inboundId}/reclassify`, {
        category: override,
      });
      toast.success(
        result.action_taken?.includes("resumed")
          ? "Reclassified — the sequence has been restarted"
          : "Reclassified"
      );
      setData({ ...data, ...result });
      onChanged?.();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const markReviewed = async () => {
    setBusy(true);
    try {
      await api.post(`/sdr/inbox/${inboundId}/reviewed`);
      toast.success("Marked reviewed");
      setData({ ...data, needs_human: false });
      onChanged?.();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const category = data?.category;
  const config = INBOUND_CATEGORY_CONFIG[category];
  const match = MATCH_METHOD_CONFIG[data?.match_method];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="bg-surface-1 border-white/10 w-full sm:max-w-lg overflow-y-auto scrollbar-thin"
        data-testid="sdr-inbound-drawer"
      >
        {!data ? (
          <div className="space-y-3 pt-6">
            <Skeleton className="h-8 bg-surface-2" />
            <Skeleton className="h-40 bg-surface-2" />
          </div>
        ) : (
          <div className="space-y-5">
            <SheetHeader>
              <SheetTitle className="pr-8 text-left break-words">
                {data.subject || "(no subject)"}
              </SheetTitle>
            </SheetHeader>

            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[11px] text-ash break-all">{data.from_email}</span>
              {config && (
                <span
                  className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase ${INBOUND_CATEGORY_STYLE[category]}`}
                  data-testid="sdr-inbound-category"
                >
                  {config.label}
                </span>
              )}
              {data.received_at && (
                <span className="font-mono text-[11px] text-carbon">
                  {format(new Date(data.received_at), "MMM d, HH:mm")}
                </span>
              )}
            </div>

            {/* A machine reply is called out in words, not just a grey pill.
                Someone skimming must not read this as a person answering. */}
            {config?.machine && (
              <div
                className="rounded-lg border border-white/10 bg-surface-2 px-3 py-2.5"
                data-testid="sdr-inbound-machine-notice"
              >
                <p className="text-xs text-ash flex items-start gap-2">
                  <Bot className="h-3.5 w-3.5 mt-0.5 shrink-0 text-graphite" />
                  <span>
                    A machine sent this — nobody read your email. The sequence was
                    {category === "out_of_office"
                      ? " left running and the next touch pushed out 7 days."
                      : " left running, untouched."}
                  </span>
                </p>
              </div>
            )}

            {data.needs_human && (
              <div
                className="rounded-lg border border-warning/20 bg-warning/10 px-3 py-2.5"
                data-testid="sdr-inbound-needs-human"
              >
                <p className="text-xs text-warning flex items-start gap-2">
                  <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  <span>
                    {data.match_method === "none"
                      ? "Nobody could route this reply. Someone answered and is waiting on an answer back."
                      : data.match_method === "sender"
                      ? MATCH_METHOD_CONFIG.sender.hint
                      : "The classifier was not confident. Confirm the category below."}
                  </span>
                </p>
              </div>
            )}

            <Section label="The reply">
              <p
                className="text-sm whitespace-pre-wrap break-words rounded-lg border border-white/10 bg-surface-2 px-3 py-2.5 max-h-64 overflow-y-auto scrollbar-thin"
                data-testid="sdr-inbound-body"
              >
                {data.text_body || "(empty)"}
              </p>
            </Section>

            {/* The message it answers, because a reply judged without the email
                that provoked it invites the same mistake the classifier made. */}
            {data.sent_message && (
              <Section label="What we sent">
                <div className="rounded-lg border border-white/10 bg-surface-2 px-3 py-2.5">
                  <p className="text-xs font-medium break-words">{data.sent_message.subject}</p>
                  <p className="text-xs text-graphite whitespace-pre-wrap break-words mt-1 max-h-40 overflow-y-auto scrollbar-thin">
                    {data.sent_message.body}
                  </p>
                  <p className="font-mono text-[10px] text-carbon mt-2">
                    step {(data.sent_message.step_index ?? 0) + 1}
                    {data.sent_message.sent_at
                      ? ` · ${format(new Date(data.sent_message.sent_at), "MMM d, HH:mm")}`
                      : ""}
                  </p>
                </div>
              </Section>
            )}

            <Section label="How this was matched">
              <p className="text-xs text-graphite flex items-start gap-2">
                <Link2 className="h-3.5 w-3.5 mt-0.5 shrink-0 text-carbon" />
                <span>
                  <span className="text-ash">{match?.label || "—"}</span>
                  {match?.hint ? ` — ${match.hint}` : ""}
                </span>
              </p>
            </Section>

            <Section label="Classification">
              <p className="text-xs text-graphite flex items-start gap-2">
                {data.category_source === "human" ? (
                  <User className="h-3.5 w-3.5 mt-0.5 shrink-0 text-carbon" />
                ) : (
                  <Bot className="h-3.5 w-3.5 mt-0.5 shrink-0 text-carbon" />
                )}
                <span>
                  {data.category_source === "headers"
                    ? "Decided from the message headers — no model was consulted."
                    : data.category_source === "human"
                    ? "Set by a human."
                    : data.category_source === "error"
                    ? "The classifier failed; nothing was acted on."
                    : `Classifier${
                        typeof data.category_confidence === "number"
                          ? `, ${Math.round(data.category_confidence * 100)}% confident`
                          : ""
                      }.`}
                  {data.reasoning ? ` ${data.reasoning}` : ""}
                </span>
              </p>
            </Section>

            {data.action_taken?.length > 0 && (
              <Section label="What happened">
                <div className="flex flex-wrap gap-1.5">
                  {data.action_taken.map((action) => (
                    <span
                      key={action}
                      className="font-mono text-[10px] px-2 py-0.5 rounded bg-surface-2 text-ash border border-white/10"
                    >
                      {action.replace(/[:_]/g, " ")}
                    </span>
                  ))}
                </div>
              </Section>
            )}

            <Section label="Correct the category">
              <p className="text-[11px] text-carbon">
                This re-applies for real. Changing a stop to an out-of-office restarts
                the sequence; it does not just relabel the row.
              </p>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Select value={override} onValueChange={setOverride}>
                  <SelectTrigger
                    className="bg-surface-2 border-white/10 h-9 w-full sm:w-52"
                    data-testid="sdr-inbound-category-select"
                  >
                    <SelectValue placeholder="Category" />
                  </SelectTrigger>
                  <SelectContent className="bg-surface-2 border-white/10">
                    {Object.entries(INBOUND_CATEGORY_CONFIG).map(([value, meta]) => (
                      <SelectItem key={value} value={value}>{meta.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  size="sm"
                  disabled={busy || !override || override === data.category}
                  onClick={reclassify}
                  className="gap-1.5"
                  data-testid="sdr-inbound-reclassify-btn"
                >
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  Apply
                </Button>
                {data.needs_human && (
                  <Button
                    size="sm" variant="outline" disabled={busy} onClick={markReviewed}
                    className="border-white/10 gap-1.5"
                    data-testid="sdr-inbound-reviewed-btn"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" /> Looks right
                  </Button>
                )}
              </div>
            </Section>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

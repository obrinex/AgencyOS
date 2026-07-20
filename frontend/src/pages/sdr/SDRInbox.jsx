import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Bot, Filter, MailQuestion, MessageSquare } from "lucide-react";
import api from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import InboundDrawer from "@/components/sdr/InboundDrawer";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  INBOUND_CATEGORY_CONFIG, INBOUND_CATEGORY_STYLE, MATCH_METHOD_CONFIG,
} from "@/lib/sdrConfig";
import { formatDistanceToNow } from "date-fns";

const PAGE_SIZE = 50;
//: Radix forbids value="" on a SelectItem, so an explicit sentinel.
const ALL = "__all__";

export default function SDRInbox() {
  const [items, setItems] = useState(null);
  const [summary, setSummary] = useState(null);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [tab, setTab] = useState("needs_human");
  const [category, setCategory] = useState(ALL);
  const [drawerId, setDrawerId] = useState(null);

  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
    if (tab === "needs_human") params.set("needs_human", "true");
    if (category !== ALL) params.set("category", category);
    return params;
  }, [tab, category]);

  const load = useCallback(async () => {
    const [list, counts] = await Promise.all([
      api.get(`/sdr/inbox?${query.toString()}`),
      api.get("/sdr/inbox/summary"),
    ]);
    setItems(list.data.items);
    setCursor(list.data.next_cursor);
    setHasMore(list.data.has_more);
    setSummary(counts.data);
  }, [query]);

  useEffect(() => { load(); }, [load]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const next = new URLSearchParams(query);
      next.set("cursor", cursor);
      const { data } = await api.get(`/sdr/inbox?${next.toString()}`);
      setItems((current) => [...(current || []), ...data.items]);
      setCursor(data.next_cursor);
      setHasMore(data.has_more);
    } finally {
      setLoadingMore(false);
    }
  };

  if (!items || !summary) {
    return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;
  }

  const filtered = tab === "needs_human" || category !== ALL;

  return (
    <div className="p-6 space-y-5" data-testid="sdr-inbox-page">
      <PageHeader
        title="Inbox"
        description="Every reply, matched back to the email that earned it"
        testId="sdr-inbox-header"
      />

      {/* An unroutable reply is a person waiting on an answer, so it gets a
          banner rather than a row that scrolls past. */}
      {summary.unmatched > 0 && (
        <Card className="p-4 bg-warning/10 border-warning/20" data-testid="sdr-inbox-unmatched-banner">
          <p className="text-sm text-warning flex items-center gap-2">
            <MailQuestion className="h-4 w-4" />
            {summary.unmatched} repl{summary.unmatched === 1 ? "y" : "ies"} nobody could route
          </p>
          <p className="text-xs text-graphite mt-1">
            These did not thread and the sender is not in any campaign. Somebody
            answered and has not been answered back — open each one and reply by hand.
          </p>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="bg-surface-2">
            <TabsTrigger value="needs_human" data-testid="sdr-inbox-tab-needs-human">
              Needs you{summary.needs_human ? ` (${summary.needs_human})` : ""}
            </TabsTrigger>
            <TabsTrigger value="all" data-testid="sdr-inbox-tab-all">
              All{summary.total ? ` (${summary.total})` : ""}
            </TabsTrigger>
          </TabsList>
        </Tabs>

        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger className="bg-surface-1 border-white/10 h-9 w-48" data-testid="sdr-inbox-category-filter">
            <SelectValue placeholder="All categories" />
          </SelectTrigger>
          <SelectContent className="bg-surface-2 border-white/10">
            <SelectItem value={ALL}>All categories</SelectItem>
            {Object.entries(INBOUND_CATEGORY_CONFIG).map(([value, meta]) => (
              <SelectItem key={value} value={value}>
                {meta.label}
                {summary.by_category?.[value] ? ` (${summary.by_category[value]})` : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon ml-auto">
          {items.length} repl{items.length === 1 ? "y" : "ies"}{hasMore ? "+" : ""}
        </span>
      </div>

      {items.length === 0 ? (
        filtered ? (
          <EmptyState
            icon={Filter}
            title={tab === "needs_human" ? "Nothing needs you" : "No replies match these filters"}
            description={
              tab === "needs_human"
                ? "Every reply so far was matched and classified confidently. Switch to All to see them."
                : "Try a different category."
            }
            testId="sdr-inbox-empty-filtered"
          />
        ) : (
          <EmptyState
            icon={MessageSquare}
            title="No replies yet"
            description="Once inbound routing is live, every reply lands here — matched to the message that earned it, classified, and acted on."
            testId="sdr-inbox-empty"
          />
        )
      ) : (
        <div className="space-y-2" data-testid="sdr-inbox-list">
          {items.map((reply) => {
            const config = INBOUND_CATEGORY_CONFIG[reply.category];
            return (
              <button
                key={reply.id}
                data-testid={`sdr-inbound-row-${reply.id}`}
                onClick={() => setDrawerId(reply.id)}
                className="w-full text-left rounded-lg border border-white/10 bg-surface-1 px-4 py-3 hover:border-white/25"
              >
                <div className="flex flex-wrap items-center gap-3">
                  {reply.needs_human && (
                    <AlertTriangle
                      className="h-3.5 w-3.5 text-warning shrink-0"
                      data-testid={`sdr-inbound-flag-${reply.id}`}
                    />
                  )}
                  <span className="font-medium text-sm truncate flex-1 min-w-0">
                    {reply.subject || "(no subject)"}
                  </span>
                  <span className="font-mono text-[11px] text-carbon truncate max-w-[14rem]">
                    {reply.from_email}
                  </span>
                  {reply.match_method !== "threaded" && (
                    <span
                      className="font-mono text-[9px] px-1.5 py-0.5 rounded uppercase bg-surface-2 text-graphite"
                      title={MATCH_METHOD_CONFIG[reply.match_method]?.hint}
                    >
                      {MATCH_METHOD_CONFIG[reply.match_method]?.label || reply.match_method}
                    </span>
                  )}
                  {config?.machine && (
                    <Bot className="h-3.5 w-3.5 text-graphite shrink-0" title="A machine sent this" />
                  )}
                  <span
                    className={`font-mono text-[9px] px-1.5 py-0.5 rounded uppercase w-28 text-center shrink-0 ${
                      INBOUND_CATEGORY_STYLE[reply.category] || "bg-surface-2 text-ash"
                    }`}
                  >
                    {config?.label || reply.category || "unclassified"}
                  </span>
                  {reply.received_at && (
                    <span className="font-mono text-[10px] text-carbon hidden sm:block w-24 text-right shrink-0">
                      {formatDistanceToNow(new Date(reply.received_at), { addSuffix: true })}
                    </span>
                  )}
                </div>
                <p className="text-xs text-graphite mt-1 line-clamp-2">{reply.text_body}</p>
              </button>
            );
          })}

          {hasMore && (
            <Button
              variant="outline" size="sm" disabled={loadingMore} onClick={loadMore}
              className="border-white/10 w-full" data-testid="sdr-inbox-load-more"
            >
              {loadingMore ? "Loading…" : "Load more"}
            </Button>
          )}
        </div>
      )}

      <InboundDrawer
        inboundId={drawerId}
        open={!!drawerId}
        onOpenChange={(open) => !open && setDrawerId(null)}
        onChanged={load}
      />
    </div>
  );
}

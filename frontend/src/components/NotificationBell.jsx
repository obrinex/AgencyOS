import { Bell, Check } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useNotifications } from "@/lib/useNotifications";

/** The bell, for the two member-facing shells.
 *
 *  Not shared with the CRM's Topbar: that one is embedded in a wider toolbar
 *  with its own spacing and test ids, and pulling it out would change a screen
 *  nobody asked to have changed. This is the same data through a surface that
 *  belongs to the portals.
 */
const TONE = {
  founding_chat: "text-primary",
  chat_message: "text-primary",
  ticket_message: "text-warning",
};

export default function NotificationBell({ testId = "portal-notifications", onNavigate }) {
  const { items, unread, reload, markAllRead, markRead } = useNotifications();
  const navigate = useNavigate();

  const open = (n) => {
    if (!n.read) markRead(n.id);
    if (n.link) {
      onNavigate?.(n.link);
      navigate(n.link);
    }
  };

  return (
    <DropdownMenu onOpenChange={(isOpen) => isOpen && reload()}>
      <DropdownMenuTrigger asChild>
        <button
          data-testid={`${testId}-trigger`}
          aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
          className="obx-glass obx-lift relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
        >
          <Bell className="h-4 w-4" />
          {unread > 0 && (
            <span className="obx-ping absolute -right-1 -top-1 flex h-[17px] min-w-[17px] items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold text-background">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent
        align="end"
        sideOffset={10}
        data-testid={`${testId}-panel`}
        className="w-[min(92vw,22rem)] overflow-hidden border-white/10 bg-black/80 p-0 backdrop-blur-2xl"
      >
        <div className="obx-aurora flex items-center justify-between border-b border-white/10 px-3 py-2.5">
          <p className="relative z-10 font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
            Notifications
          </p>
          {unread > 0 && (
            <button
              onClick={markAllRead}
              data-testid={`${testId}-mark-all`}
              className="relative z-10 flex items-center gap-1 text-[11px] text-primary hover:underline"
            >
              <Check className="h-3 w-3" /> Mark all read
            </button>
          )}
        </div>

        <div className="scrollbar-thin max-h-[60vh] overflow-y-auto">
          {items.length === 0 ? (
            <p className="px-4 py-10 text-center text-sm text-graphite">
              Nothing yet. This is where you&apos;ll hear about it.
            </p>
          ) : (
            items.map((n) => (
              <button
                key={n.id}
                onClick={() => open(n)}
                data-testid={`${testId}-item-${n.id}`}
                className="obx-row flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-white/[0.05]"
              >
                <span
                  className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                    n.read ? "bg-white/15" : `${TONE[n.type] || "text-primary"} bg-current`
                  }`}
                />
                <span className="min-w-0 flex-1">
                  <span className={`block truncate text-sm ${n.read ? "text-ash" : "font-medium"}`}>
                    {n.title}
                  </span>
                  {n.message && (
                    <span className="mt-0.5 line-clamp-2 block text-xs text-graphite">{n.message}</span>
                  )}
                  <span className="mt-1 block font-mono text-[10px] text-carbon">
                    {n.created_at
                      ? formatDistanceToNow(new Date(n.created_at), { addSuffix: true })
                      : ""}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

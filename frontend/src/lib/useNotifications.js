import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";

/** Notifications, polled.
 *
 *  Polling rather than a socket because the backend is a stateless FastAPI app
 *  behind Vercel — there is nowhere to hold a connection, and a portal that is
 *  open for an hour costs six requests a minute for a number that is almost
 *  always zero. The interval backs off when the tab is hidden for the same
 *  reason: a laptop with the portal on a background tab should not be doing
 *  work nobody is looking at.
 */
const ACTIVE_MS = 12000;
const HIDDEN_MS = 60000;

export function useNotifications({ announce = true } = {}) {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  //: The newest id we have already told the user about. Without this, every
  //: poll would re-announce the same message — and on first load it would
  //: announce a week of history at once.
  const announced = useRef(null);
  const primed = useRef(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/notifications");
      const rows = Array.isArray(data) ? data : [];
      setItems(rows);
      setUnread(rows.filter((n) => !n.read).length);

      const newest = rows[0];
      if (!primed.current) {
        // First load establishes the baseline and announces nothing.
        primed.current = true;
        announced.current = newest?.id ?? null;
        return;
      }
      if (announce && newest && newest.id !== announced.current && !newest.read) {
        announced.current = newest.id;
        toast(newest.title, { description: newest.message });
      }
    } catch {
      // A failed poll is not worth a toast — the next one is 12 seconds away.
    }
  }, [announce]);

  useEffect(() => {
    load();
    let timer;
    const schedule = () => {
      clearInterval(timer);
      timer = setInterval(load, document.hidden ? HIDDEN_MS : ACTIVE_MS);
    };
    const onVisibility = () => {
      schedule();
      if (!document.hidden) load();
    };
    schedule();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [load]);

  const markAllRead = useCallback(async () => {
    // Optimistic: the badge clears on the click, not on the round trip.
    setItems((rows) => rows.map((n) => ({ ...n, read: true })));
    setUnread(0);
    try {
      await api.patch("/notifications/read-all");
    } catch {
      load();
    }
  }, [load]);

  const markRead = useCallback(async (id) => {
    setItems((rows) => rows.map((n) => (n.id === id ? { ...n, read: true } : n)));
    setUnread((n) => Math.max(0, n - 1));
    try {
      await api.patch(`/notifications/${id}/read`);
    } catch {
      load();
    }
  }, [load]);

  return { items, unread, reload: load, markAllRead, markRead };
}

/** Per-surface unread counts — the dots on the navigation itself.
 *
 *  Separate from the bell on purpose. The bell answers "has anything happened";
 *  these answer "where", which is what makes a badge worth tapping.
 */
export function useUnreadCounts(path, { enabled = true } = {}) {
  const [counts, setCounts] = useState({});

  const load = useCallback(async () => {
    if (!enabled) return;
    try {
      const { data } = await api.get(path);
      setCounts(data || {});
    } catch {
      /* leave the last known counts rather than flashing them to zero */
    }
  }, [path, enabled]);

  useEffect(() => {
    load();
    let timer;
    const schedule = () => {
      clearInterval(timer);
      timer = setInterval(load, document.hidden ? HIDDEN_MS : ACTIVE_MS);
    };
    const onVisibility = () => {
      schedule();
      if (!document.hidden) load();
    };
    schedule();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [load]);

  return { counts, reload: load, clear: (key) => setCounts((c) => ({ ...c, [key]: 0 })) };
}

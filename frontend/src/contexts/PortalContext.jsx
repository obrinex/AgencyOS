import { createContext, useCallback, useContext, useEffect, useState } from "react";
import api from "@/lib/api";

/** What the portal shell needs to know about the person before it renders.
 *
 *  One fetch, shared by the gate, the tour and the assistant. Three components
 *  each fetching `/me/context` on mount would mean three requests on every open
 *  and three chances for them to disagree about whether the interview is done.
 *
 *  Deliberately fails open. If the request errors — backend down, network gone
 *  — `blocked` resolves to false and the portal renders normally. A gate that
 *  appears because a request failed would lock someone out of their own account
 *  over a dropped packet, which is a far worse failure than showing the portal
 *  to someone who has not been interviewed yet.
 */

const Ctx = createContext(null);

export function usePortal() {
  const value = useContext(Ctx);
  if (!value) throw new Error("usePortal must be used inside <PortalProvider>");
  return value;
}

export function PortalProvider({ children }) {
  const [state, setState] = useState(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/me/context");
      setState(data);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveAnswer = useCallback(async (key, value) => {
    const { data } = await api.post("/me/onboarding", { key, value });
    setState((s) =>
      s ? { ...s, answers: { ...s.answers, [key]: value },
            onboarding_complete: data.onboarding_complete } : s);
    return data;
  }, []);

  const markGuideSeen = useCallback(async () => {
    // Optimistic — the tour closes on the click, not on the round trip.
    setState((s) => (s ? { ...s, guide_seen: true } : s));
    try { await api.post("/me/guide-seen"); } catch { /* it will re-show; harmless */ }
  }, []);

  const replayGuide = useCallback(async () => {
    setState((s) => (s ? { ...s, guide_seen: false } : s));
    try { await api.post("/me/guide-reset"); } catch { /* nothing to undo */ }
  }, []);

  const ready = state !== null || failed;

  return (
    <Ctx.Provider
      value={{
        ...(state || {}),
        ready,
        failed,
        questions: state?.questions || [],
        answers: state?.answers || {},
        /** True only when we positively know the interview is unfinished. */
        blocked: Boolean(state && !state.onboarding_complete && state.questions?.length),
        /** True only when we positively know the tour has never been shown. */
        showGuide: Boolean(state && state.onboarding_complete && !state.guide_seen),
        reload: load,
        saveAnswer,
        markGuideSeen,
        replayGuide,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

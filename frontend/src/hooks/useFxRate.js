import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";

/**
 * Live conversion rate for `currency` → INR.
 *
 * Returns { rate, asOf, source, stale, loading, refresh }. The rate falls back
 * to 1 for INR (and while loading) so callers can multiply unconditionally
 * without guarding for null.
 */
export function useFxRate(currency = "USD", { enabled = true } = {}) {
  const code = (currency || "INR").toUpperCase();
  const isBase = code === "INR";
  const [state, setState] = useState({
    rate: 1, asOf: null, source: null, stale: false, loading: false,
  });

  const fetchRate = useCallback(
    async (force = false) => {
      if (!enabled || isBase) {
        setState({ rate: 1, asOf: null, source: "identity", stale: false, loading: false });
        return;
      }
      setState((s) => ({ ...s, loading: true }));
      try {
        const { data } = await api.get("/finance/fx-rate", {
          params: { base: code, quote: "INR", refresh: force },
        });
        setState({
          rate: data.rate, asOf: data.as_of, source: data.source,
          stale: !!data.stale, loading: false,
        });
      } catch {
        // Keep whatever rate we already had; flag it so the UI can say so.
        setState((s) => ({ ...s, stale: true, loading: false }));
      }
    },
    [code, isBase, enabled]
  );

  useEffect(() => { fetchRate(false); }, [fetchRate]);

  return { ...state, refresh: () => fetchRate(true) };
}

/** One-line provenance for a rate, e.g. "1 USD = ₹96.28 · frankfurter". */
export function describeRate(code, { rate, source, stale }) {
  if (!rate || code === "INR") return "";
  const value = Number(rate).toLocaleString(undefined, { maximumFractionDigits: 2 });
  return `1 ${code} = ₹${value}${source ? ` · ${source}` : ""}${stale ? " · may be out of date" : ""}`;
}

import axios from "axios";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

const EMPTY_STATS = {
  revenue: 0,
  mrr: 0,
  arr: 0,
  outstanding: 0,
  profit: 0,
  expenses: 0,
  pipeline_value: 0,
  conversion_rate: 0,
  avg_deal_size: 0,
  total_leads: 0,
  sales_funnel: [],
  todays_tasks: [],
  upcoming_meetings: [],
  active_projects_count: 0,
  at_risk_projects_count: 0,
};

const EMPTY_FINANCE = {
  revenue: 0,
  outstanding: 0,
  expenses: 0,
  profit: 0,
  mrr: 0,
  arr: 0,
  gross_margin: 0,
  pipeline_value: 0,
  conversion_rate: 0,
  revenue_by_month: [],
};

function fallbackForGet(url = "") {
  if (url.includes("/dashboard/stats")) return EMPTY_STATS;
  if (url.includes("/finance/summary")) return EMPTY_FINANCE;
  if (url.includes("/finance/goal")) return { monthly_target: 0, current: 0 };
  if (url.includes("/settings/company")) return { company_name: "Obrinex", logo_url: null, custom_domain: null, currency: "INR" };
  if (url.includes("/meetings/google/status")) return { connected: false };
  if (url.includes("/bookings/settings")) return { enabled: false, slug: "", duration_minutes: 30, availability: [] };
  if (url.includes("/portal/overview")) return { projects: [], invoices: [], contracts: [], files: [], tickets: [] };
  if (url.includes("/auth/me")) return null;
  return [];
}

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("agencyos_access_token");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// The GET fallback below stops pages getting stuck on skeletons when a request
// fails — but it must never be silent, or real data looks deceptively empty.
let _lastFallbackToast = 0;
function notifyFallback() {
  const now = Date.now();
  if (now - _lastFallbackToast < 15000) return; // debounce bursts of failing requests
  _lastFallbackToast = now;
  toast.error("Couldn't load live data — some sections may look empty.", {
    description: "Check your connection, then retry.",
    action: { label: "Retry", onClick: () => window.location.reload() },
    duration: 10000,
  });
}

function apiErrorMessage(error) {
  if (error?.response?.data?.detail) return formatApiError(error.response.data.detail);
  if (error?.response?.status) return `Request failed with status ${error.response.status}. Please refresh and try again.`;
  if (error?.code === "ERR_NETWORK" || error?.message === "Network Error") {
    return "Could not reach the server. Refresh the page, then log in again if needed.";
  }
  if (error?.message) return error.message;
  return "Something went wrong. Please try again.";
}

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    error.userMessage = apiErrorMessage(error);
    if (error.response?.status === 401 && !original._retry && !original.url.includes("/auth/")) {
      original._retry = true;
      try {
        const { data } = await api.post("/auth/refresh");
        if (data?.access_token) {
          sessionStorage.setItem("agencyos_access_token", data.access_token);
        }
        return api(original);
      } catch (e) {
        sessionStorage.removeItem("agencyos_access_token");
        sessionStorage.removeItem("agencyos_user");
        window.location.href = "/login";
        return Promise.reject(error);
      }
    }
    const isGet = (original?.method || "get").toLowerCase() === "get";
    const transient = !error.response || error.response.status >= 500;
    if (isGet && !original?.url?.includes("/auth/") && transient) {
      // One silent retry first. A serverless cold start or a transient 5xx makes
      // the very first request on a freshly-opened page fail even though the
      // backend is healthy — retrying after a beat clears it without ever
      // blanking the section or alarming the owner. Only a SECOND failure (a
      // real, persistent problem) falls back with the toast.
      if (!original._getRetry) {
        original._getRetry = true;
        await new Promise((r) => setTimeout(r, 1200));
        return api(original);
      }
      notifyFallback();
      return Promise.resolve({
        data: fallbackForGet(original.url),
        status: 200,
        statusText: "Fallback",
        headers: { "x-fallback": "1" },
        config: original,
      });
    }
    return Promise.reject(error);
  }
);

export function formatApiError(detail) {
  if (detail == null) return "Could not complete the request. Refresh the page, log in again if needed, and try once more.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export function formatRequestError(error) {
  return error?.userMessage || apiErrorMessage(error);
}

export async function downloadFile(url, filename) {
  const res = await api.get(url, { responseType: "blob" });
  const blobUrl = window.URL.createObjectURL(new Blob([res.data]));
  const link = document.createElement("a");
  link.href = blobUrl;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(blobUrl);
}

export default api;

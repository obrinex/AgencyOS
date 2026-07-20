import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const cached = sessionStorage.getItem("agencyos_user");
    return cached ? JSON.parse(cached) : null;
  }); // null = loading, false = unauthenticated, object = authenticated
  const [pendingTwoFA, setPendingTwoFA] = useState(null);

  const fetchMe = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      sessionStorage.setItem("agencyos_user", JSON.stringify(data));
      setUser(data);
    } catch (e) {
      // /auth/me intentionally bypasses the shared refresh interceptor to
      // avoid a loop, so recover a valid session explicitly before logging out.
      try {
        const { data } = await api.post("/auth/refresh");
        if (data?.access_token) {
          sessionStorage.setItem("agencyos_access_token", data.access_token);
        }
        const { data: refreshedUser } = await api.get("/auth/me");
        sessionStorage.setItem("agencyos_user", JSON.stringify(refreshedUser));
        setUser(refreshedUser);
      } catch {
        sessionStorage.removeItem("agencyos_user");
        sessionStorage.removeItem("agencyos_access_token");
        setUser(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  const login = async (email, password) => {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ email, password }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw { response: { data } };
    }
    if (data.requires_2fa) {
      setPendingTwoFA(data.temp_token);
      return { requires2FA: true };
    }
    if (data.access_token) {
      sessionStorage.setItem("agencyos_access_token", data.access_token);
      delete data.access_token;
    }
    sessionStorage.setItem("agencyos_user", JSON.stringify(data));
    setUser(data);
    return { requires2FA: false };
  };

  const verify2FA = async (code) => {
    const response = await fetch("/api/auth/2fa/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ temp_token: pendingTwoFA, code }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw { response: { data } };
    }
    if (data.access_token) {
      sessionStorage.setItem("agencyos_access_token", data.access_token);
      delete data.access_token;
    }
    sessionStorage.setItem("agencyos_user", JSON.stringify(data));
    setUser(data);
    setPendingTwoFA(null);
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      sessionStorage.removeItem("agencyos_user");
      sessionStorage.removeItem("agencyos_access_token");
      setUser(false);
    }
  };

  return (
    <AuthContext.Provider value={{ user, setUser, login, verify2FA, logout, refetch: fetchMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

export { formatApiError };

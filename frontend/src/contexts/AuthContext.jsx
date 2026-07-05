import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = loading, false = unauthenticated, object = authenticated
  const [pendingTwoFA, setPendingTwoFA] = useState(null);

  const fetchMe = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch (e) {
      setUser(false);
    }
  }, []);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    if (data.requires_2fa) {
      setPendingTwoFA(data.temp_token);
      return { requires2FA: true };
    }
    setUser(data);
    return { requires2FA: false };
  };

  const verify2FA = async (code) => {
    const { data } = await api.post("/auth/2fa/login", { temp_token: pendingTwoFA, code });
    setUser(data);
    setPendingTwoFA(null);
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } finally {
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

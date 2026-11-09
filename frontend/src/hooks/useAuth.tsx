import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, onUnauthorized } from "../lib/api";
import { consumeAuthFragment, getToken, loginUrl, setToken } from "../lib/auth";
import type { Me } from "../types";

type AuthState = {
  token: string | null;
  me: Me | null;
  loading: boolean;
  authError: string | null;
  pendingNext: string | null;
  login: (next?: string, switchAccount?: boolean) => void;
  logout: () => void;
  refreshMe: () => Promise<void>;
  clearPendingNext: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTok] = useState<string | null>(() => {
    const frag = consumeAuthFragment();
    if (frag?.token) {
      setToken(frag.token);
      sessionStorage.setItem("trill.next", frag.next || "/dashboard");
      return frag.token;
    }
    if (frag?.error) sessionStorage.setItem("trill.auth_error", frag.error);
    return getToken();
  });
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState<boolean>(!!token);
  const [authError, setAuthError] = useState<string | null>(() => {
    const e = sessionStorage.getItem("trill.auth_error");
    sessionStorage.removeItem("trill.auth_error");
    return e;
  });
  const [pendingNext, setPendingNext] = useState<string | null>(() => sessionStorage.getItem("trill.next"));

  const logout = useCallback(() => {
    setToken(null);
    setTok(null);
    setMe(null);
    api.post("/api/auth/logout").catch(() => undefined);
  }, []);

  const refreshMe = useCallback(async () => {
    if (!getToken()) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      const data = await api.get<Me>("/api/me");
      setMe(data);
    } catch (e: any) {
      if (e?.status === 401 || e?.status === 404) {
        setToken(null);
        setTok(null);
        setMe(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshMe();
  }, [token, refreshMe]);

  useEffect(() => onUnauthorized(() => { setTok(null); setMe(null); setAuthError("session_expired"); }), []);

  // Keep capability pills fresh without hammering the server
  useEffect(() => {
    if (!token) return;
    const id = window.setInterval(() => void refreshMe(), 45_000);
    return () => window.clearInterval(id);
  }, [token, refreshMe]);

  const login = useCallback((next = "/dashboard", switchAccount = false) => {
    window.location.href = loginUrl(next, switchAccount);
  }, []);

  const clearPendingNext = useCallback(() => {
    sessionStorage.removeItem("trill.next");
    setPendingNext(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ token, me, loading, authError, pendingNext, login, logout, refreshMe, clearPendingNext }),
    [token, me, loading, authError, pendingNext, login, logout, refreshMe, clearPendingNext]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

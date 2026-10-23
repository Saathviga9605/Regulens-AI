import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { ApiError, UNAUTHENTICATED_EVENT, apiClient, getToken, setToken } from "../services/apiClient";
import type { User } from "../types/api";

interface AuthValue {
  user: User | null;
  loading: boolean;
  /** Set when the session ended unexpectedly (expired, revoked). */
  notice: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(() => getToken() !== null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) return;
    apiClient.me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const onExpired = () => {
      setUser(null);
      setNotice("Your session has ended. Please sign in again.");
    };
    window.addEventListener(UNAUTHENTICATED_EVENT, onExpired);
    return () => window.removeEventListener(UNAUTHENTICATED_EVENT, onExpired);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const result = await apiClient.login(username, password);
    setToken(result.token);
    setUser(result.user);
    setNotice(null);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiClient.logout();
    } catch (err) {
      if (!(err instanceof ApiError)) throw err;
    } finally {
      setToken(null);
      setUser(null);
    }
  }, []);

  return <AuthContext.Provider value={{ user, loading, notice, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

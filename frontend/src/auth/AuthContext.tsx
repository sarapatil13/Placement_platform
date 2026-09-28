import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, clearSession, extractErrorMessage, getStoredUser, storeSession } from "../api/client";
import type { AccessToken, WhoAmI } from "../api/types";
import { httpError } from "../api/client";

interface AuthContextValue {
  user: WhoAmI | null;
  loading: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<WhoAmI>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<WhoAmI | null>(() => getStoredUser());

  useEffect(() => {
    if (getStoredUser()) {
      void refreshUser().catch(() => {
        /* interceptor clears stale session */
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post<AccessToken>("/auth/login", { email, password });
    storeSession(data);
    setUser(data.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      // The refresh token lives in an httpOnly cookie; the server revokes it and
      // clears the cookie. Works even when the access token has already expired.
      await api.post("/auth/logout", {}, { withCredentials: true });
    } catch {
      /* best-effort server-side token revoke */
    } finally {
      clearSession();
      setUser(null);
    }
  }, []);

  const refreshUser = useCallback(async () => {
    const { data } = await api.get<WhoAmI>("/auth/me");
    setUser((prev) => ({ ...prev, ...data }));
    return data;
  }, []);

  const value: AuthContextValue = {
    user,
    loading: false,
    isAdmin: user?.role === "placement_admin" || user?.role === "super_admin",
    login,
    logout,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export { extractErrorMessage, httpError };
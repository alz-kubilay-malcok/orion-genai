"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  fetchCurrentUser,
  loginRequest,
  logoutRequest,
  type AuthUser,
  type LoginResult,
} from "@/lib/adminApi";

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<LoginResult>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/**
 * Tek provider üzerinden sayfa-level auth state. SSR'da ``loading=true``
 * olarak başlar; ilk render'da ``/auth/me`` çağrısı yapılır. Login formu
 * provider'ı ``useAuth().login()`` ile kullanır; nav/auth-guard'lar
 * ``useAuth().user``'a bakar.
 *
 * Fetch yarışı: ilk ``fetchCurrentUser`` 401 dönerse (token'sız) UI
 * login sayfasına yönlendirilmek üzere ``user=null`` bırakır; Bearer
 * token localStorage'a yazıldıktan sonra otomatik ikinci mount yok —
 * ``loginRequest`` zaten ``/auth/me`` çağırıp ``user``'ı doldurur.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const me = await fetchCurrentUser();
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (username: string, password: string): Promise<LoginResult> => {
      const res = await loginRequest(username, password);
      if (res.kind === "ok") setUser(res.user);
      return res;
    },
    [],
  );

  const logout = useCallback(async () => {
    await logoutRequest();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, login, logout, refresh }),
    [user, loading, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

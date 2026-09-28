"use client";

/**
 * Who is signed in, what they may do, and the public configuration.
 *
 * Everything here comes from the server: the usage counter, the tier, whether
 * ads show. The browser renders it and never computes an entitlement itself —
 * the API enforces every limit whether or not this component agrees.
 */

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { ApiError, apiFetch, type Me, type PublicConfig, type Usage } from "@/lib/api";

interface SessionValue {
  me: Me | null;
  config: PublicConfig | null;
  loading: boolean;
  refresh: () => Promise<void>;
  setUsage: (usage: Usage) => void;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionValue>({
  me: null,
  config: null,
  loading: true,
  refresh: async () => undefined,
  setUsage: () => undefined,
  logout: async () => undefined,
});

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setMe(await apiFetch<Me>("/me"));
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) setMe(null);
    }
  }, []);

  useEffect(() => {
    Promise.all([
      refresh(),
      apiFetch<PublicConfig>("/config/public")
        .then(setConfig)
        .catch(() => setConfig(null)),
    ]).finally(() => setLoading(false));
  }, [refresh]);

  const setUsage = useCallback(
    (usage: Usage) => setMe((current) => (current ? { ...current, usage } : current)),
    [],
  );

  const logout = useCallback(async () => {
    await apiFetch("/auth/logout", { method: "POST" }).catch(() => undefined);
    setMe(null);
  }, []);

  return (
    <SessionContext.Provider value={{ me, config, loading, refresh, setUsage, logout }}>
      {children}
    </SessionContext.Provider>
  );
}

export const useSession = () => useContext(SessionContext);

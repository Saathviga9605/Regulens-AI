import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { ApiError, apiClient } from "../services/apiClient";
import type { ConnectionState, HealthResponse } from "../types/api";

interface BackendHealthValue {
  state: ConnectionState;
  refresh: () => void;
}

const BackendHealthContext = createContext<BackendHealthValue | null>(null);

export function deriveConnectionState(health: HealthResponse, checkedAt = new Date()): ConnectionState {
  const healthy = health.status === "ok" && health.database.status === "ok";
  return healthy ? { kind: "connected", health, checkedAt } : { kind: "degraded", health, checkedAt };
}

export function BackendHealthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ConnectionState>({ kind: "loading" });
  const requestSeq = useRef(0);

  const refresh = useCallback(() => {
    const seq = ++requestSeq.current;
    setState({ kind: "loading" });
    apiClient
      .getHealth()
      .then((health) => {
        if (seq === requestSeq.current) setState(deriveConnectionState(health));
      })
      .catch((err: unknown) => {
        if (seq !== requestSeq.current) return;
        const message = err instanceof ApiError ? err.message : "An unexpected error occurred while checking the API.";
        setState({ kind: "disconnected", message, checkedAt: new Date() });
      });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return <BackendHealthContext.Provider value={{ state, refresh }}>{children}</BackendHealthContext.Provider>;
}

export function useBackendHealth(): BackendHealthValue {
  const value = useContext(BackendHealthContext);
  if (!value) throw new Error("useBackendHealth must be used inside BackendHealthProvider");
  return value;
}

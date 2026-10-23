import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { LoadingState, PageHeader } from "../components/ui";
import { useAuth } from "./AuthContext";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <LoadingState label="Checking session…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}

/** UI guard only — every admin endpoint is also enforced by the backend. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user?.role !== "admin") {
    return (
      <div className="mx-auto max-w-3xl space-y-3">
        <PageHeader title="Administrator access required" />
        <p role="alert" className="text-sm text-ink">
          This page is available to administrators only. Your role is <strong>{user?.role ?? "unknown"}</strong>.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}

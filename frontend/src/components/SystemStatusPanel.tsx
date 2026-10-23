import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, XCircle } from "lucide-react";

import { API_BASE_URL } from "../services/apiClient";
import type { ConnectionState } from "../types/api";

interface Props {
  state: ConnectionState;
  onRetry: () => void;
}

const HEADINGS: Record<ConnectionState["kind"], string> = {
  loading: "Checking backend status…",
  connected: "Backend connected",
  degraded: "Backend degraded",
  disconnected: "Backend unavailable",
};

function StatusIcon({ kind }: { kind: ConnectionState["kind"] }) {
  const cls = "h-5 w-5 shrink-0";
  switch (kind) {
    case "loading":
      return <Loader2 aria-hidden="true" className={`${cls} animate-spin text-ink-subtle`} />;
    case "connected":
      return <CheckCircle2 aria-hidden="true" className={`${cls} text-success-700`} />;
    case "degraded":
      return <AlertTriangle aria-hidden="true" className={`${cls} text-warning-800`} />;
    case "disconnected":
      return <XCircle aria-hidden="true" className={`${cls} text-danger-700`} />;
  }
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="text-ink-subtle">{label}</dt>
      <dd className="min-w-0 text-right font-medium text-ink [overflow-wrap:anywhere]">{value}</dd>
    </div>
  );
}

export function SystemStatusPanel({ state, onRetry }: Props) {
  return (
    <section aria-labelledby="system-status-heading" className="rounded-lg border border-line bg-surface p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <StatusIcon kind={state.kind} />
          <h2 id="system-status-heading" className="text-base font-semibold text-ink">
            {HEADINGS[state.kind]}
          </h2>
        </div>
        <button
          type="button"
          onClick={onRetry}
          disabled={state.kind === "loading"}
          className="inline-flex items-center gap-1.5 rounded-control border border-line-strong bg-surface px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-saffron-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw aria-hidden="true" className="h-4 w-4" />
          {state.kind === "disconnected" ? "Retry" : "Recheck"}
        </button>
      </div>

      {state.kind === "disconnected" && (
        <div role="alert" className="mt-4 rounded-control border border-danger-line bg-danger-bg p-3 text-sm text-danger-700">
          <p>{state.message}</p>
          <p className="mt-1 text-danger-700">
            Start the backend (see README) and confirm <code className="font-mono">VITE_API_BASE_URL</code> is correct.
          </p>
        </div>
      )}

      {state.kind === "degraded" && (
        <div role="alert" className="mt-4 rounded-control border border-warning-line bg-warning-bg p-3 text-sm text-warning-800">
          The API is reachable but reports an unhealthy dependency.
          {state.health.database.detail && <> Database: {state.health.database.detail}</>}
        </div>
      )}

      <dl className="mt-4 divide-y divide-line">
        <Row label="API endpoint" value={API_BASE_URL} />
        {(state.kind === "connected" || state.kind === "degraded") && (
          <>
            <Row label="Application" value={state.health.app_name} />
            <Row label="API version" value={state.health.api_version} />
            <Row label="Overall status" value={state.health.status} />
            <Row label="Database" value={state.health.database.status} />
          </>
        )}
        {state.kind !== "loading" && <Row label="Last checked" value={state.checkedAt.toLocaleTimeString()} />}
      </dl>
    </section>
  );
}

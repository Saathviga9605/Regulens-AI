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
      return <Loader2 aria-hidden="true" className={`${cls} animate-spin text-slate-500`} />;
    case "connected":
      return <CheckCircle2 aria-hidden="true" className={`${cls} text-emerald-600`} />;
    case "degraded":
      return <AlertTriangle aria-hidden="true" className={`${cls} text-amber-600`} />;
    case "disconnected":
      return <XCircle aria-hidden="true" className={`${cls} text-red-600`} />;
  }
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-800 break-all">{value}</dd>
    </div>
  );
}

export function SystemStatusPanel({ state, onRetry }: Props) {
  return (
    <section aria-labelledby="system-status-heading" className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <StatusIcon kind={state.kind} />
          <h2 id="system-status-heading" className="text-base font-semibold text-slate-900">
            {HEADINGS[state.kind]}
          </h2>
        </div>
        <button
          type="button"
          onClick={onRetry}
          disabled={state.kind === "loading"}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw aria-hidden="true" className="h-4 w-4" />
          {state.kind === "disconnected" ? "Retry" : "Recheck"}
        </button>
      </div>

      {state.kind === "disconnected" && (
        <div role="alert" className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <p>{state.message}</p>
          <p className="mt-1 text-red-700">
            Start the backend (see README) and confirm <code className="font-mono">VITE_API_BASE_URL</code> is correct.
          </p>
        </div>
      )}

      {state.kind === "degraded" && (
        <div role="alert" className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          The API is reachable but reports an unhealthy dependency.
          {state.health.database.detail && <> Database: {state.health.database.detail}</>}
        </div>
      )}

      <dl className="mt-4 divide-y divide-slate-100">
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

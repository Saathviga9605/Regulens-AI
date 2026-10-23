import type { ConnectionState } from "../types/api";

const STYLES: Record<ConnectionState["kind"], { label: string; dot: string; text: string }> = {
  loading: { label: "Checking…", dot: "bg-slate-400 animate-pulse", text: "text-slate-300" },
  connected: { label: "Connected", dot: "bg-emerald-400", text: "text-emerald-200" },
  degraded: { label: "Degraded", dot: "bg-amber-400", text: "text-amber-200" },
  disconnected: { label: "Disconnected", dot: "bg-red-400", text: "text-red-200" },
};

export function ConnectionIndicator({ state }: { state: ConnectionState }) {
  const style = STYLES[state.kind];
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 text-sm" data-testid="connection-indicator">
      <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
      <span className={style.text}>
        <span className="sr-only">Backend connection: </span>
        {style.label}
      </span>
    </div>
  );
}

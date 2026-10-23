import type { ConnectionState } from "../types/api";

const STYLES: Record<ConnectionState["kind"], { label: string; dot: string; text: string }> = {
  loading: { label: "Checking…", dot: "bg-ink-subtle animate-pulse", text: "text-brand-100" },
  connected: { label: "Connected", dot: "bg-success-700", text: "text-success-line" },
  degraded: { label: "Degraded", dot: "bg-saffron-500", text: "text-warning-line" },
  disconnected: { label: "Disconnected", dot: "bg-danger-700", text: "text-danger-line" },
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

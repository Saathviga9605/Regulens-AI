import { CheckCircle2, Info, TriangleAlert, X } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type ToastTone = "success" | "error" | "info";
interface ToastItem {
  id: number;
  tone: ToastTone;
  message: string;
}

const ToastContext = createContext<(message: string, tone?: ToastTone) => void>(() => {});
const TIMEOUT_MS = 6000;

/** Toasts confirm completed server actions. They are announced via a polite live region and auto-dismiss. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const dismiss = useCallback((id: number) => setItems((all) => all.filter((t) => t.id !== id)), []);
  const push = useCallback((message: string, tone: ToastTone = "success") => {
    const id = Date.now() + Math.random();
    setItems((all) => [...all.slice(-3), { id, tone, message }]);
    setTimeout(() => dismiss(id), TIMEOUT_MS);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" aria-label="Notifications"
        className="pointer-events-none fixed bottom-4 right-4 z-[var(--z-toast)] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
        {items.map((t) => {
          const Icon = t.tone === "success" ? CheckCircle2 : t.tone === "error" ? TriangleAlert : Info;
          const tone = t.tone === "success" ? "border-success-line text-success-700" : t.tone === "error"
            ? "border-danger-line text-danger-700" : "border-info-line text-info-700";
          return (
            <div key={t.id} role="status" className={`pointer-events-auto flex items-start gap-2 rounded-panel border bg-surface px-3 py-2 text-sm shadow-overlay ${tone}`}>
              <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
              <p className="flex-1 text-ink">{t.message}</p>
              <button type="button" aria-label="Dismiss notification" onClick={() => dismiss(t.id)} className="text-ink-subtle hover:text-ink">
                <X aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}

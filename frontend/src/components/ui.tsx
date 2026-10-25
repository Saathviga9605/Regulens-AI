/**
 * ReguLens design-system primitives (see docs/design-system.md).
 * All colours come from semantic tokens in index.css; icons are Lucide at 16px (h-4 w-4), stroke 2.
 */
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, ChevronRight as Crumb, Eye, EyeOff, Info, RefreshCw, X } from "lucide-react";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { Link } from "react-router";

import { STATUS_LABELS, STATUS_STYLES } from "../app/labels";
import type { ApplicationStatus } from "../types/api";

// --- Buttons -----------------------------------------------------------------------------------

const BTN = "inline-flex items-center justify-center gap-1.5 rounded-control px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";

export const buttonStyles = {
  primary: `${BTN} bg-brand-800 text-white hover:bg-brand-900 shadow-panel`,
  secondary: `${BTN} border border-line-strong bg-surface text-ink hover:bg-surface-muted`,
  danger: `${BTN} bg-danger-700 text-white hover:brightness-90`,
  ghost: `${BTN} text-brand-700 hover:bg-brand-50`,
  link: "font-medium text-brand-700 underline-offset-2 hover:underline",
  small: "inline-flex items-center gap-1 rounded-control px-2 py-1 text-xs font-medium transition-colors",
};

export function IconButton({ label, onClick, children, className = "" }: {
  label: string; onClick: () => void; children: ReactNode; className?: string;
}) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-control text-ink-muted hover:bg-surface-muted hover:text-ink ${className}`}>
      {children}
    </button>
  );
}

// --- Page structure ----------------------------------------------------------------------------

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav aria-label="Breadcrumb" className="text-xs text-ink-subtle">
      <ol className="flex flex-wrap items-center gap-1">
        {items.map((item, i) => (
          <li key={`${item.label}-${i}`} className="flex items-center gap-1">
            {i > 0 && <Crumb aria-hidden="true" className="h-3 w-3" />}
            {item.to && i < items.length - 1
              ? <Link to={item.to} className="hover:text-brand-700 hover:underline">{item.label}</Link>
              : <span aria-current={i === items.length - 1 ? "page" : undefined} className="font-medium text-ink-muted">{item.label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function PageHeader({ title, description, actions, breadcrumbs, eyebrow }: {
  title: string; description?: ReactNode; actions?: ReactNode; breadcrumbs?: BreadcrumbItem[]; eyebrow?: ReactNode;
}) {
  return (
    <header className="space-y-2 border-b border-line pb-4">
      {breadcrumbs && <Breadcrumbs items={breadcrumbs} />}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          {eyebrow && <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-saffron-600">{eyebrow}</div>}
          <h1 className="text-xl font-semibold tracking-tight text-brand-900 sm:text-2xl [overflow-wrap:anywhere]">{title}</h1>
          {description && <p className="mt-1 max-w-3xl text-sm text-ink-muted">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
    </header>
  );
}

export function Card({ title, description, children, actions, id }: {
  title?: string; description?: ReactNode; children: ReactNode; actions?: ReactNode; id?: string;
}) {
  const headingId = useId();
  return (
    <section id={id} aria-labelledby={title ? headingId : undefined}
      className="scroll-mt-24 rounded-panel border border-line bg-surface shadow-panel">
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
          <div className="min-w-0">
            {title && <h2 id={headingId} className="text-base font-semibold text-brand-900">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-ink-subtle">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className="p-4 sm:p-5">{children}</div>
    </section>
  );
}

/** In-page section navigation for long workspaces (anchor links; all sections stay mounted). */
export function SectionNav({ label, sections }: { label: string; sections: { id: string; label: string }[] }) {
  return (
    <nav aria-label={label}
      className="sticky top-[var(--layout-header)] z-[var(--z-sticky)] -mx-4 overflow-x-auto border-b border-line bg-canvas/95 px-4 py-2 backdrop-blur-sm sm:mx-0 sm:rounded-panel sm:border sm:px-3">
      <ul className="flex gap-1 whitespace-nowrap text-sm">
        {sections.map((s) => (
          <li key={s.id}>
            <a href={`#${s.id}`} className="inline-block rounded-control px-2.5 py-1 font-medium text-ink-muted hover:bg-brand-50 hover:text-brand-800">
              {s.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

// --- Status and badges -------------------------------------------------------------------------

export function Pill({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${className}`}>
      {children}
    </span>
  );
}

export type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "brand" | "accent";
const TONES: Record<Tone, string> = {
  neutral: "bg-surface-muted text-ink-muted ring-line",
  info: "bg-info-bg text-info-700 ring-info-line",
  success: "bg-success-bg text-success-700 ring-success-line",
  warning: "bg-warning-bg text-warning-800 ring-warning-line",
  danger: "bg-danger-bg text-danger-700 ring-danger-line",
  brand: "bg-brand-50 text-brand-800 ring-brand-100",
  accent: "bg-saffron-100 text-saffron-600 ring-saffron-100",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <Pill className={TONES[tone]}>{children}</Pill>;
}

export function StatusBadge({ status }: { status: ApplicationStatus }) {
  return <Pill className={STATUS_STYLES[status]}>{STATUS_LABELS[status]}</Pill>;
}

// --- Feedback ------------------------------------------------------------------------------------

export function Alert({ tone, title, children }: { tone: "error" | "success" | "info" | "warning"; title?: string; children: ReactNode }) {
  const styles = {
    error: "border-danger-line bg-danger-bg text-danger-700",
    success: "border-success-line bg-success-bg text-success-700",
    info: "border-info-line bg-info-bg text-ink",
    warning: "border-warning-line bg-warning-bg text-warning-800",
  }[tone];
  const Icon = tone === "error" || tone === "warning" ? AlertTriangle : tone === "success" ? CheckCircle2 : Info;
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`flex gap-2 rounded-control border p-3 text-sm ${styles}`}>
      <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 [overflow-wrap:anywhere]">
        {title && <p className="font-semibold">{title}</p>}
        {children}
      </div>
    </div>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div aria-hidden="true" className="space-y-2">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-3 animate-pulse rounded bg-line" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function LoadingState({ label }: { label: string }) {
  return (
    <div role="status" className="space-y-3 py-6">
      <p className="text-sm text-ink-muted">{label}</p>
      <Skeleton />
    </div>
  );
}

export function ProgressBar({ label, value }: { label: string; value?: number }) {
  return (
    <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}
      className="h-1.5 w-full overflow-hidden rounded-full bg-line">
      <div className={`h-full bg-brand-700 ${value === undefined ? "w-1/3 animate-pulse" : ""}`}
        style={value === undefined ? undefined : { width: `${value}%` }} />
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="rounded-control border border-danger-line bg-danger-bg p-4 text-sm text-danger-700">
      <p className="font-semibold">Could not load data.</p>
      <p className="mt-1">{message}</p>
      <button type="button" onClick={onRetry} className={`${buttonStyles.secondary} mt-3`}>
        <RefreshCw aria-hidden="true" className="h-4 w-4" /> Retry
      </button>
    </div>
  );
}

export function EmptyState({ children, title, action }: { children: ReactNode; title?: string; action?: ReactNode }) {
  return (
    <div className="rounded-control border border-dashed border-line-strong bg-surface-muted px-4 py-8 text-center text-sm text-ink-muted">
      {title && <p className="mb-1 font-semibold text-ink">{title}</p>}
      <div>{children}</div>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Pagination({ page, totalPages, total, onPage }: { page: number; totalPages: number; total: number; onPage: (page: number) => void }) {
  if (total === 0) return null;
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-3 pt-3 text-sm text-ink-muted">
      <span>Page {page} of {Math.max(totalPages, 1)} · {total} {total === 1 ? "record" : "records"}</span>
      <div className="flex gap-2">
        <button type="button" className={buttonStyles.secondary} disabled={page <= 1} onClick={() => onPage(page - 1)}>
          <ChevronLeft aria-hidden="true" className="h-4 w-4" /> Previous
        </button>
        <button type="button" className={buttonStyles.secondary} disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
          Next <ChevronRight aria-hidden="true" className="h-4 w-4" />
        </button>
      </div>
    </nav>
  );
}

// --- Form fields ---------------------------------------------------------------------------------

const INPUT =
  "mt-1 block w-full rounded-control border bg-surface px-3 py-2 text-sm text-ink shadow-sm placeholder:text-ink-subtle focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/25 disabled:bg-surface-muted disabled:text-ink-subtle";

interface FieldProps {
  label: string;
  error?: string | undefined;
  hint?: string;
  required?: boolean;
}

function FieldShell({ id, label, error, hint, required, children }: FieldProps & { id: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="block text-sm font-medium text-ink">
        {label}
        {required && <span aria-hidden="true" className="ml-0.5 text-danger-700">*</span>}
      </label>
      {children}
      {hint && !error && <p id={`${id}-hint`} className="mt-1 text-xs text-ink-subtle">{hint}</p>}
      {error && <p id={`${id}-error`} className="mt-1 flex items-start gap-1 text-xs text-danger-700">{error}</p>}
    </div>
  );
}

function describedBy(id: string, error?: string, hint?: string) {
  return error ? `${id}-error` : hint ? `${id}-hint` : undefined;
}

const border = (error?: string) => (error ? "border-danger-700" : "border-line-strong");

export function TextField({ label, error, hint, required, ...props }: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} error={error} hint={hint} required={required}>
      <input id={id} aria-invalid={error ? true : undefined} aria-describedby={describedBy(id, error, hint)}
        aria-required={required || undefined} className={`${INPUT} ${border(error)}`} {...props} />
    </FieldShell>
  );
}

export function PasswordField({ label, error, hint, required, ...props }: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  return (
    <FieldShell id={id} label={label} error={error} hint={hint} required={required}>
      <div className="relative">
        <input id={id} type={visible ? "text" : "password"} aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(id, error, hint)} className={`${INPUT} ${border(error)} pr-10`} {...props} />
        <button type="button" onClick={() => setVisible((v) => !v)} aria-pressed={visible}
          aria-label={visible ? "Hide password" : "Show password"}
          className="absolute inset-y-0 right-1 my-1 mt-2 inline-flex w-8 items-center justify-center rounded text-ink-subtle hover:text-ink">
          {visible ? <EyeOff aria-hidden="true" className="h-4 w-4" /> : <Eye aria-hidden="true" className="h-4 w-4" />}
        </button>
      </div>
    </FieldShell>
  );
}

export function TextArea({ label, error, hint, required, ...props }: FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  const length = typeof props.value === "string" ? props.value.length : undefined;
  return (
    <FieldShell id={id} label={label} error={error} hint={hint} required={required}>
      <textarea id={id} rows={3} aria-invalid={error ? true : undefined} aria-describedby={describedBy(id, error, hint)}
        className={`${INPUT} ${border(error)} resize-y`} {...props} />
      {props.maxLength && length !== undefined && (
        <p className="mt-0.5 text-right text-xs text-ink-subtle" aria-hidden="true">{length}/{props.maxLength}</p>
      )}
    </FieldShell>
  );
}

export function SelectField({ label, error, hint, required, options, placeholder, ...props }:
  FieldProps & SelectHTMLAttributes<HTMLSelectElement> & { options: [string, string][]; placeholder?: string }) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} error={error} hint={hint} required={required}>
      <select id={id} aria-invalid={error ? true : undefined} aria-describedby={describedBy(id, error, hint)}
        className={`${INPUT} ${border(error)}`} {...props}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
      </select>
    </FieldShell>
  );
}

export function Checkbox({ label, ...props }: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="inline-flex items-center gap-2 text-sm text-ink">
      <input type="checkbox" className="h-4 w-4 rounded border-line-strong accent-brand-700" {...props} />
      {label}
    </label>
  );
}

// --- Data display --------------------------------------------------------------------------------

export function DefinitionGrid({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map(([term, value]) => (
        <div key={term} className="min-w-0">
          <dt className="text-xs font-medium uppercase tracking-wide text-ink-subtle">{term}</dt>
          <dd className="mt-0.5 text-sm text-ink [overflow-wrap:anywhere]">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Tables scroll horizontally inside their own region on small screens; the page never does. */
export const TABLE = {
  wrap: "overflow-x-auto rounded-panel border border-line bg-surface shadow-panel",
  table: "min-w-full divide-y divide-line text-sm [&_tbody_tr:hover]:bg-brand-50/40",
  th: "whitespace-nowrap bg-surface-muted px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted sm:px-4",
  td: "px-3 py-3 align-top text-ink sm:px-4",
};

export function EvidenceQuote({ quote, source }: { quote: string; source?: ReactNode }) {
  return (
    <figure className="min-w-0">
      <blockquote className="border-l-4 border-teal-700 bg-teal-100/40 px-2 py-1 font-mono text-xs text-ink [overflow-wrap:anywhere]">
        <span className="sr-only">Quoted document text: </span>{quote}
      </blockquote>
      {source && <figcaption className="mt-1 text-xs text-ink-subtle">{source}</figcaption>}
    </figure>
  );
}

export function Tabs<T extends string>({ label, tabs, value, onChange }: {
  label: string; tabs: [T, string][]; value: T; onChange: (value: T) => void;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  function onKey(e: React.KeyboardEvent, i: number) {
    const next = e.key === "ArrowRight" ? (i + 1) % tabs.length : e.key === "ArrowLeft" ? (i - 1 + tabs.length) % tabs.length : null;
    if (next === null) return;
    e.preventDefault();
    onChange(tabs[next]![0]);
    refs.current[next]?.focus();
  }
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map(([key, text], i) => (
        <button key={key} ref={(el) => { refs.current[i] = el; }} type="button" role="tab" aria-selected={value === key}
          tabIndex={value === key ? 0 : -1} onClick={() => onChange(key)} onKeyDown={(e) => onKey(e, i)}
          className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${value === key ? "border-saffron-500 text-brand-900" : "border-transparent text-ink-muted hover:text-ink"}`}>
          {text}
        </button>
      ))}
    </div>
  );
}

// --- Dialogs -------------------------------------------------------------------------------------

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Modal dialog: focus moves in and is trapped, Escape closes, focus returns, background scroll is locked. */
export function Dialog({ title, open, onClose, children, footer, width = "max-w-lg" }: {
  title: string; open: boolean; onClose: () => void; children: ReactNode; footer?: ReactNode; width?: string;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  // Callers usually pass an inline onClose; keeping it in a ref stops the focus effect re-running (and stealing
  // focus from a text field) on every render while the dialog is open.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const first = panel.current?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? panel.current)?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { e.stopPropagation(); closeRef.current(); }
      if (e.key !== "Tab" || !panel.current) return;
      const items = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) return;
      const [head, tail] = [items[0]!, items[items.length - 1]!];
      if (e.shiftKey && document.activeElement === head) { e.preventDefault(); tail.focus(); }
      else if (!e.shiftKey && document.activeElement === tail) { e.preventDefault(); head.focus(); }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previous?.focus?.();
    };
  }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[var(--z-dialog)] flex items-end justify-center bg-brand-950/50 p-0 sm:items-center sm:p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
        className={`flex max-h-[92vh] w-full ${width} flex-col rounded-t-panel bg-surface shadow-overlay sm:rounded-panel`}>
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-3">
          <h2 id={titleId} className="text-base font-semibold text-brand-900">{title}</h2>
          <IconButton label="Close dialog" onClick={onClose}><X aria-hidden="true" className="h-4 w-4" /></IconButton>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ open, title, children, confirmLabel, onConfirm, onCancel, busy, destructive, error }: {
  open: boolean; title: string; children: ReactNode; confirmLabel: string; onConfirm: () => void; onCancel: () => void;
  busy?: boolean; destructive?: boolean; error?: string | null;
}) {
  return (
    <Dialog open={open} title={title} onClose={() => { if (!busy) onCancel(); }} footer={
      <>
        <button type="button" className={buttonStyles.secondary} onClick={onCancel} disabled={busy}>Cancel</button>
        <button type="button" className={destructive ? buttonStyles.danger : buttonStyles.primary} onClick={onConfirm} disabled={busy}>
          {busy ? "Working…" : confirmLabel}
        </button>
      </>
    }>
      <div className="space-y-3 text-sm text-ink">
        {children}
        {error && <Alert tone="error">{error}</Alert>}
      </div>
    </Dialog>
  );
}

import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Loader2, RefreshCw } from "lucide-react";
import { useId, type ReactNode, type SelectHTMLAttributes, type InputHTMLAttributes } from "react";

import { STATUS_LABELS, STATUS_STYLES } from "../app/labels";
import type { ApplicationStatus } from "../types/api";

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600";

export const buttonStyles = {
  primary: `inline-flex items-center justify-center gap-1.5 rounded-md bg-blue-700 px-3.5 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS}`,
  secondary: `inline-flex items-center justify-center gap-1.5 rounded-md border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS}`,
  link: `font-medium text-blue-700 underline-offset-2 hover:underline ${FOCUS}`,
};

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-600">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={title ? id : undefined} className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      {(title || actions) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && (
            <h2 id={id} className="text-base font-semibold text-slate-900">
              {title}
            </h2>
          )}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatusBadge({ status }: { status: ApplicationStatus }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}

export function Alert({ tone, children }: { tone: "error" | "success" | "info"; children: ReactNode }) {
  const styles = {
    error: "border-red-200 bg-red-50 text-red-800",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900",
    info: "border-blue-200 bg-blue-50 text-slate-700",
  }[tone];
  const Icon = tone === "error" ? AlertTriangle : CheckCircle2;
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`flex gap-2 rounded-md border p-3 text-sm ${styles}`}>
      {tone !== "info" && <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />}
      <div>{children}</div>
    </div>
  );
}

export function LoadingState({ label }: { label: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-10 text-sm text-slate-600">
      <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p className="font-medium">Could not load data.</p>
      <p className="mt-1">{message}</p>
      <button type="button" onClick={onRetry} className={`${buttonStyles.secondary} mt-3`}>
        <RefreshCw aria-hidden="true" className="h-4 w-4" /> Retry
      </button>
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-sm text-slate-600">{children}</div>;
}

export function Pagination({ page, totalPages, total, onPage }: { page: number; totalPages: number; total: number; onPage: (page: number) => void }) {
  if (total === 0) return null;
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-3 pt-4 text-sm text-slate-600">
      <span>
        Page {page} of {Math.max(totalPages, 1)} · {total} {total === 1 ? "record" : "records"}
      </span>
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

const INPUT =
  "mt-1 block w-full rounded-md border bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600/30";

interface FieldProps {
  label: string;
  error?: string | undefined;
  hint?: string;
}

function FieldShell({ id, label, error, hint, children }: FieldProps & { id: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      {children}
      {hint && !error && (
        <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="mt-1 text-xs text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}

function describedBy(id: string, error?: string, hint?: string) {
  return error ? `${id}-error` : hint ? `${id}-hint` : undefined;
}

export function TextField({ label, error, hint, ...props }: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} error={error} hint={hint}>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, error, hint)}
        className={`${INPUT} ${error ? "border-red-500" : "border-slate-300"}`}
        {...props}
      />
    </FieldShell>
  );
}

export function SelectField({
  label,
  error,
  hint,
  options,
  placeholder,
  ...props
}: FieldProps & SelectHTMLAttributes<HTMLSelectElement> & { options: [string, string][]; placeholder?: string }) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} error={error} hint={hint}>
      <select
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, error, hint)}
        className={`${INPUT} ${error ? "border-red-500" : "border-slate-300"}`}
        {...props}
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}

export function DefinitionGrid({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map(([term, value]) => (
        <div key={term}>
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{term}</dt>
          <dd className="mt-0.5 text-sm text-slate-900 break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export const TABLE = {
  wrap: "overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm",
  table: "min-w-full divide-y divide-slate-200 text-sm",
  th: "px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600 bg-slate-50",
  td: "px-4 py-3 align-top text-slate-700",
};

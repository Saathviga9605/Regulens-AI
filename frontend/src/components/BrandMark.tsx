/** Original ReguLens product mark: a document outline with a magnifier lens. Not a government emblem. */
export function BrandMark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true" focusable="false">
      <rect x="1" y="1" width="30" height="30" rx="6" fill="#10204a" />
      <path d="M9 7h9l5 5v13a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1Z" fill="none" stroke="#ffffff" strokeWidth="1.6" />
      <path d="M18 7v5h5" fill="none" stroke="#ffffff" strokeWidth="1.6" />
      <circle cx="16" cy="18" r="3.6" fill="none" stroke="#e07b16" strokeWidth="2" />
      <path d="m18.7 20.7 3 3" stroke="#e07b16" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark({ inverse = false }: { inverse?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <BrandMark />
      <span className="leading-tight">
        <span className={`block text-base font-semibold tracking-tight ${inverse ? "text-white" : "text-brand-900"}`}>ReguLens AI</span>
        <span className={`block text-[11px] uppercase tracking-wider ${inverse ? "text-brand-100" : "text-ink-subtle"}`}>
          Regulatory Scrutiny Assistance
        </span>
      </span>
    </span>
  );
}

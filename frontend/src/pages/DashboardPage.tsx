import { CheckCircle2, CircleDashed, Info } from "lucide-react";

import { useBackendHealth } from "../app/BackendHealthContext";
import { MODULES } from "../app/navigation";
import { SystemStatusPanel } from "../components/SystemStatusPanel";

const IMPLEMENTED = [
  "Dashboard shell and navigation",
  "Live backend health check (API + database query)",
  "Connection status: connected, degraded and disconnected states",
  "Institution records: create, search, view and edit (fictional data)",
  "EoA applications: create drafts, search, filter, edit drafts and move through internal workflow statuses",
  "Secure PDF intake with private storage and exact-duplicate detection",
  "Document processing: page text (OCR when Tesseract is installed), type detection, evidence-quoted fields",
  "Preliminary scrutiny: configurable rules, cross-document checks, anomaly indicators and run history",
  "Simulated issuer checks against synthetic records (clearly labelled, not real verification)",
];

export function DashboardPage() {
  const { state, refresh } = useBackendHealth();

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-600">
          Extension of Approval (EoA) scrutiny workspace — foundation release.
        </p>
      </header>

      <section
        aria-labelledby="purpose-heading"
        className="flex gap-3 rounded-lg border border-blue-200 bg-blue-50 p-5 text-sm text-slate-700"
      >
        <Info aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-blue-700" />
        <div>
          <h2 id="purpose-heading" className="font-semibold text-slate-900">
            Decision support, not decision making
          </h2>
          <p className="mt-1">
            ReguLens AI assists AICTE reviewers by organising evidence, checking applications against configurable
            regulatory rules and highlighting items that may need attention. It never approves or rejects an
            application, and a flagged anomaly is a prompt for human review — not a finding of misconduct. All
            decisions remain with authorised reviewers.
          </p>
        </div>
      </section>

      <SystemStatusPanel state={state} onRetry={refresh} />

      <div className="grid gap-6 md:grid-cols-2">
        <section aria-labelledby="implemented-heading" className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <h2 id="implemented-heading" className="text-base font-semibold text-slate-900">
            Available in this release
          </h2>
          <ul className="mt-3 space-y-2 text-sm">
            {IMPLEMENTED.map((item) => (
              <li key={item} className="flex gap-2">
                <CheckCircle2 aria-hidden="true" className="h-4 w-4 shrink-0 text-emerald-600" />
                {item}
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="planned-heading" className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <h2 id="planned-heading" className="text-base font-semibold text-slate-900">
            Planned modules
          </h2>
          <ul className="mt-3 space-y-2 text-sm">
            {MODULES.filter((m) => !m.available).map((m) => (
              <li key={m.path} className="flex gap-2">
                <CircleDashed aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-400" />
                <span>
                  <span className="font-medium text-slate-800">{m.label}</span>
                  <span className="text-slate-500"> — {m.summary}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

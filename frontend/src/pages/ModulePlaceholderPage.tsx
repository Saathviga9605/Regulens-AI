import type { ModuleDefinition } from "../app/navigation";

export function ModulePlaceholderPage({ module }: { module: ModuleDefinition }) {
  const Icon = module.icon;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="flex items-center gap-3">
        <Icon aria-hidden="true" className="h-6 w-6 text-slate-500" />
        <h1 className="text-2xl font-semibold text-slate-900">{module.label}</h1>
        <span className="rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-medium text-slate-700">Planned</span>
      </header>
      <section className="rounded-lg border border-dashed border-slate-300 bg-white p-6">
        <p className="text-sm text-slate-700">{module.summary}</p>
        <p className="mt-3 text-sm text-slate-600">
          This module is not implemented yet. No data is shown here because none exists — nothing on this page is
          simulated.
        </p>
        <h2 className="mt-5 text-sm font-semibold text-slate-900">Planned scope</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
          {module.plannedScope.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

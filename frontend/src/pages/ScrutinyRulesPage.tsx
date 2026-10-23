import { useState } from "react";

import { SEVERITY_LABELS, entries, formatDateTime } from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { Alert, ErrorState, LoadingState, PageHeader, Pill, TABLE } from "../components/ui";
import { ApiError, apiClient } from "../services/apiClient";
import type { RuleUpdate, ScrutinyRule, Severity } from "../types/api";

const VERIFICATION_TEXT: Record<ScrutinyRule["source_verification_status"], string> = {
  verified: "Source verified",
  unverified: "Source not verified",
  not_applicable: "Integrity check (not a regulatory requirement)",
};

export function ScrutinyRulesPage() {
  const rules = useApiQuery(() => apiClient.listRules(), "rules");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  async function update(rule: ScrutinyRule, change: RuleUpdate) {
    setBusy(rule.rule_id);
    setMessage(null);
    try {
      const updated = await apiClient.updateRule(rule.rule_id, change);
      rules.setData((rules.data ?? []).map((r) => (r.rule_id === updated.rule_id ? updated : r)));
      setMessage({ tone: "success", text: `${updated.rule_id} saved (now version ${updated.version}). New runs use it; past runs keep their snapshot.` });
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof ApiError ? err.message : "Could not update the rule." });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Scrutiny rules"
        description="Configurable, deterministic rules used by preliminary scrutiny. Parameters are validated data, never executable code."
      />
      <Alert tone="info">
        Rules marked <strong>demo-only</strong> are prototype expectations that have not been verified against the AICTE
        Approval Process Handbook or any official source. Integrity checks are generic consistency checks, not
        regulatory requirements.
      </Alert>
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
      {rules.loading && !rules.data ? (
        <LoadingState label="Loading rules…" />
      ) : rules.error ? (
        <ErrorState message={rules.error} onRetry={rules.reload} />
      ) : (
        <div className={TABLE.wrap}>
          <table className={TABLE.table}>
            <caption className="sr-only">Scrutiny rules</caption>
            <thead>
              <tr>
                <th scope="col" className={TABLE.th}>Rule</th>
                <th scope="col" className={TABLE.th}>Source</th>
                <th scope="col" className={TABLE.th}>Severity</th>
                <th scope="col" className={TABLE.th}>Enabled</th>
                <th scope="col" className={TABLE.th}>Version</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(rules.data ?? []).map((r) => (
                <tr key={r.rule_id} className={r.enabled ? "" : "bg-slate-50 text-slate-500"}>
                  <td className={TABLE.td}>
                    <div className="font-mono text-xs text-slate-500">{r.rule_id} · {r.rule_type}</div>
                    <div className="font-medium text-slate-900">{r.title}</div>
                    <div className="text-xs">{r.description}</div>
                    <details className="mt-1 text-xs">
                      <summary className="cursor-pointer text-blue-700">Parameters</summary>
                      <pre className="mt-1 overflow-x-auto rounded bg-slate-100 p-2">{JSON.stringify(r.parameters, null, 2)}</pre>
                    </details>
                  </td>
                  <td className={`${TABLE.td} text-xs`}>
                    {r.is_demo_only && <Pill className="mb-1 bg-amber-100 text-amber-900 ring-amber-300">Demo-only</Pill>}
                    <div>{VERIFICATION_TEXT[r.source_verification_status]}</div>
                    <div className="text-slate-500">{r.source}</div>
                    {r.source_reference && <div className="text-slate-500">{r.source_reference}</div>}
                  </td>
                  <td className={TABLE.td}>
                    <label className="sr-only" htmlFor={`sev-${r.rule_id}`}>Severity for {r.rule_id}</label>
                    <select id={`sev-${r.rule_id}`} value={r.severity} disabled={busy === r.rule_id}
                      onChange={(e) => update(r, { severity: e.target.value as Severity })}
                      className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/40">
                      {entries(SEVERITY_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </td>
                  <td className={TABLE.td}>
                    <label className="inline-flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={r.enabled} disabled={busy === r.rule_id} aria-label={`Enable ${r.rule_id}`}
                        onChange={(e) => update(r, { enabled: e.target.checked })}
                        className="h-4 w-4 rounded border-slate-300 focus-visible:outline-2 focus-visible:outline-blue-600" />
                      {r.enabled ? "On" : "Off"}
                    </label>
                  </td>
                  <td className={`${TABLE.td} whitespace-nowrap text-xs`}>
                    v{r.version}
                    <div className="text-slate-500">{formatDateTime(r.updated_at)}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-slate-500">
        Rule parameters can be changed through the API (<code>PATCH /api/v1/scrutiny-rules/&#123;rule_id&#125;</code>); they are validated against a fixed schema per rule type.
      </p>
    </div>
  );
}

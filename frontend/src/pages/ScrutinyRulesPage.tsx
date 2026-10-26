import { useState } from "react";

import { useAuth } from "../app/AuthContext";
import { SEVERITY_LABELS, entries, formatDateTime } from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { useToast } from "../components/Toast";
import { Alert, Card, ConfirmDialog, ErrorState, LoadingState, PageHeader, Pill, TABLE } from "../components/ui";
import { ApiError, apiClient } from "../services/apiClient";
import type { RuleUpdate, ScrutinyRule, Severity } from "../types/api";

const VERIFICATION_TEXT: Record<ScrutinyRule["source_verification_status"], string> = {
  verified: "Source verified",
  unverified: "Source not verified",
  not_applicable: "Integrity check (not a regulatory requirement)",
};

export function ScrutinyRulesPage() {
  const isAdmin = useAuth().user?.role === "admin";
  const rules = useApiQuery(() => apiClient.listRules(), "rules");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [pending, setPending] = useState<{ rule: ScrutinyRule; change: RuleUpdate } | null>(null);
  const [pendingError, setPendingError] = useState<string | null>(null);
  const toast = useToast();

  async function update(rule: ScrutinyRule, change: RuleUpdate) {
    if (busy) return;
    setBusy(rule.rule_id);
    setMessage(null);
    setPendingError(null);
    try {
      const updated = await apiClient.updateRule(rule.rule_id, change);
      rules.setData((rules.data ?? []).map((r) => (r.rule_id === updated.rule_id ? updated : r)));
      const text = updated.registry_managed
        ? `${updated.rule_id} enabled state saved; content remains version ${updated.version}. Change recorded in the audit trail.`
        : `${updated.rule_id} saved (now version ${updated.version}). New runs use it; past runs keep their snapshot.`;
      setMessage({ tone: "success", text });
      toast(`${updated.rule_id} saved.`);
      setPending(null);
    } catch (err) {
      // Keep the dialog open with the reason so the admin can retry or cancel.
      setPendingError(err instanceof ApiError ? err.message : "Could not update the rule.");
    } finally {
      setBusy(null);
    }
  }

  const change = pending?.change;
  const confirmTitle = change?.enabled === false ? "Disable rule?" : change?.enabled === true ? "Enable rule?" : "Change severity?";

  return (
    <div className="space-y-6">
      <ConfirmDialog open={pending !== null} title={confirmTitle} busy={busy !== null} error={pendingError}
        destructive={change?.enabled === false}
        confirmLabel={change?.enabled === false ? "Disable rule" : change?.enabled === true ? "Enable rule" : "Change severity"}
        onConfirm={() => pending && update(pending.rule, pending.change)}
        onCancel={() => { setPending(null); setPendingError(null); }}>
        {pending && (
          <>
            <p><strong className="font-mono">{pending.rule.rule_id}</strong> — {pending.rule.title}</p>
            {change?.severity && <p>Severity changes from <strong>{SEVERITY_LABELS[pending.rule.severity]}</strong> to <strong>{SEVERITY_LABELS[change.severity]}</strong>.</p>}
            {change?.enabled === false && <p>Future scrutiny runs will not evaluate this rule.</p>}
            {change?.enabled === true && <p>Future scrutiny runs will evaluate this rule again.</p>}
            {pending.rule.registry_managed
              ? <p className="text-ink-muted">Registry rule content and version stay unchanged. The enabled-state change is recorded in the audit trail.</p>
              : <p className="text-ink-muted">Past runs keep their rule snapshot. The change creates a new rule version and is recorded in the audit trail.</p>}
          </>
        )}
      </ConfirmDialog>
      <PageHeader
        eyebrow="Administration"
        breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Scrutiny rules" }]}
        title="Scrutiny rules"
        description="Configurable, deterministic rules used by preliminary scrutiny. Parameters are validated data, never executable code."
      />
      <Alert tone="info">
        Rules marked <strong>demo-only</strong> are prototype expectations that have not been verified against the AICTE
        Approval Process Handbook. Integrity checks are generic consistency checks, not regulatory requirements. APH EoA
        rules cite the pinned handbook; see Regulatory source for their classification.
      </Alert>
      {!isAdmin && (
        <p className="rounded-control border border-line bg-surface-muted p-2 text-sm text-ink">
          Read-only: only administrators can enable, disable or change rules.
        </p>
      )}
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
      {rules.loading && !rules.data ? (
        <LoadingState label="Loading rules…" />
      ) : rules.error ? (
        <ErrorState message={rules.error} onRetry={rules.reload} />
      ) : (
        <Card>
        <div className={TABLE.wrap}>
          <table className={`${TABLE.table} min-w-[56rem]`}>
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
            <tbody className="divide-y divide-line">
              {(rules.data ?? []).map((r) => (
                <tr key={r.rule_id} className={r.enabled ? "" : "bg-surface-muted text-ink-subtle"}>
                  <td className={TABLE.td}>
                    <div className="font-mono text-xs text-ink-subtle">{r.rule_id} · {r.rule_type}</div>
                    <div className="font-medium text-ink">{r.title}</div>
                    <div className="text-xs">{r.description}</div>
                    <details className="mt-1 text-xs">
                      <summary className="cursor-pointer text-brand-700">Parameters</summary>
                      <pre className="mt-1 overflow-x-auto rounded bg-surface-muted p-2">{JSON.stringify(r.parameters, null, 2)}</pre>
                    </details>
                  </td>
                  <td className={`${TABLE.td} text-xs`}>
                    {r.is_demo_only && <Pill className="mb-1 bg-warning-bg text-warning-800 ring-warning-line">Demo-only</Pill>}
                    <div>{VERIFICATION_TEXT[r.source_verification_status]}</div>
                    <div className="text-ink-subtle">{r.source}</div>
                    {r.source_reference && <div className="text-ink-subtle">{r.source_reference}</div>}
                  </td>
                  <td className={TABLE.td}>
                    {r.registry_managed ? (
                      <span className="text-xs text-ink-subtle">Registry-managed · content immutable</span>
                    ) : (
                      <>
                        <label className="sr-only" htmlFor={`sev-${r.rule_id}`}>Severity for {r.rule_id}</label>
                        <select id={`sev-${r.rule_id}`} value={r.severity} disabled={!isAdmin || busy === r.rule_id}
                          onChange={(e) => setPending({ rule: r, change: { severity: e.target.value as Severity } })}
                          className="rounded-control border border-line-strong bg-surface px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600/25">
                          {entries(SEVERITY_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                        </select>
                      </>
                    )}
                  </td>
                  <td className={TABLE.td}>
                    <label className="inline-flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={r.enabled} disabled={!isAdmin || busy === r.rule_id} aria-label={`Enable ${r.rule_id}`}
                        onChange={(e) => setPending({ rule: r, change: { enabled: e.target.checked } })}
                        className="h-4 w-4 rounded border-line-strong focus-visible:outline-2 focus-visible:outline-saffron-500" />
                      {r.enabled ? "On" : "Off"}
                    </label>
                  </td>
                  <td className={`${TABLE.td} whitespace-nowrap text-xs`}>
                    v{r.version}
                    <div className="text-ink-subtle">{formatDateTime(r.updated_at)}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </Card>
      )}
      <p className="text-xs text-ink-subtle">
        Rule parameters can be changed through the API (<code>PATCH /api/v1/scrutiny-rules/&#123;rule_id&#125;</code>); they are validated against a fixed schema per rule type.
      </p>
    </div>
  );
}

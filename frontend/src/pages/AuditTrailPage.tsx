import { useState, type FormEvent } from "react";

import { formatDateTime } from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { Alert, EmptyState, ErrorState, LoadingState, PageHeader, Pagination, Pill, SelectField, TABLE, TextField, buttonStyles } from "../components/ui";
import { apiClient } from "../services/apiClient";
import type { AuditEvent, AuditQuery } from "../types/api";

const OUTCOME_STYLE: Record<AuditEvent["outcome"], string> = {
  success: "bg-success-bg text-success-700 ring-success-line",
  failure: "bg-warning-bg text-warning-800 ring-warning-line",
  denied: "bg-danger-bg text-danger-700 ring-danger-line",
};

export function AuditTable({ events }: { events: AuditEvent[] }) {
  return (
    <div className={TABLE.wrap}>
      <table className={`${TABLE.table} min-w-[48rem]`}>
        <caption className="sr-only">Audit events</caption>
        <thead>
          <tr>
            <th scope="col" className={TABLE.th}>When (UTC shown locally)</th>
            <th scope="col" className={TABLE.th}>Actor</th>
            <th scope="col" className={TABLE.th}>Action</th>
            <th scope="col" className={TABLE.th}>Resource</th>
            <th scope="col" className={TABLE.th}>Outcome</th>
            <th scope="col" className={TABLE.th}>Details</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {events.map((e) => (
            <tr key={e.id}>
              <td className={`${TABLE.td} whitespace-nowrap text-xs`}><time dateTime={e.created_at} title={`${e.created_at} (UTC)`}>{formatDateTime(e.created_at)}</time></td>
              <td className={TABLE.td}>{e.actor_username}</td>
              <td className={`${TABLE.td} font-mono text-xs`}>{e.action}</td>
              <td className={`${TABLE.td} text-xs`}>{e.resource_type}{e.resource_id ? ` · ${e.resource_id}` : ""}</td>
              <td className={TABLE.td}><Pill className={OUTCOME_STYLE[e.outcome]}>{e.outcome}</Pill></td>
              <td className={`${TABLE.td} text-xs [overflow-wrap:anywhere]`}>
                {Object.entries(e.details).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join(" · ") || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AuditTrailPage() {
  const [query, setQuery] = useState<AuditQuery>({ page: 1, page_size: 50 });
  const [draft, setDraft] = useState({ action: "", actor: "", application_code: "" });
  const events = useApiQuery(() => apiClient.listAuditEvents(query), JSON.stringify(query));

  function apply(e: FormEvent) {
    e.preventDefault();
    setQuery({ ...query, page: 1, action: draft.action || undefined, actor: draft.actor || undefined,
      application_code: draft.application_code || undefined });
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administration" breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Audit trail" }]} title="Audit trail"
        description="Application-level append-only log of important actions. Times are shown in your local time zone; hover a time for UTC." />
      <Alert tone="info">
        Entries cannot be edited or deleted through ReguLens. This is an application-level log, not a cryptographically
        tamper-evident or legally certified immutable record: database administrators can still alter stored rows.
      </Alert>
      <form onSubmit={apply} className="grid gap-3 rounded-lg border border-line bg-surface p-4 shadow-sm sm:grid-cols-5 sm:items-end">
        <TextField label="Action starts with" placeholder="e.g. finding." value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value })} />
        <TextField label="Actor username" value={draft.actor} onChange={(e) => setDraft({ ...draft, actor: e.target.value })} />
        <TextField label="Application ID" value={draft.application_code} onChange={(e) => setDraft({ ...draft, application_code: e.target.value })} />
        <SelectField label="Outcome" value={query.outcome ?? ""} placeholder="All"
          options={[["success", "Success"], ["failure", "Failure"], ["denied", "Denied"]]}
          onChange={(e) => setQuery({ ...query, page: 1, outcome: e.target.value || undefined })} />
        <button type="submit" className={buttonStyles.secondary}>Apply filters</button>
      </form>
      {events.loading && !events.data ? <LoadingState label="Loading audit events…" /> : events.error ? (
        <ErrorState message={events.error} onRetry={events.reload} />
      ) : events.data && events.data.items.length === 0 ? <EmptyState>No audit events match.</EmptyState> : events.data ? (
        <>
          <AuditTable events={events.data.items} />
          <Pagination page={events.data.page} totalPages={events.data.total_pages} total={events.data.total}
            onPage={(p) => setQuery({ ...query, page: p })} />
        </>
      ) : null}
    </div>
  );
}

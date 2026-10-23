import { Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { REVIEW_STATE_LABELS, SEVERITY_LABELS, STATUS_LABELS, entries, formatDateTime } from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { EmptyState, ErrorState, LoadingState, PageHeader, Pagination, Pill, SelectField, TABLE, TextField, buttonStyles } from "../components/ui";
import { apiClient } from "../services/apiClient";
import type { ApplicationStatus, QueueQuery, Severity } from "../types/api";

const SCRUTINY_STATUS: Record<string, string> = {
  none: "No scrutiny run", completed: "Completed", completed_with_warnings: "Completed with warnings", failed: "Failed",
};
const SORTS: Record<string, string> = { priority: "Priority", application_code: "Application ID", updated: "Recently updated" };

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-control border border-line bg-surface px-3 py-2 shadow-sm">
      <dt className="text-xs text-ink-subtle">{label}</dt>
      <dd className="text-2xl font-semibold tabular-nums text-ink">{value}</dd>
    </div>
  );
}

export function ReviewQueuePage() {
  const [params, setParams] = useSearchParams();
  const query: QueueQuery = {
    q: params.get("q") ?? undefined,
    status: (params.get("status") as ApplicationStatus | null) ?? undefined,
    scrutiny_status: params.get("scrutiny_status") ?? undefined,
    severity: (params.get("severity") as Severity | null) ?? undefined,
    unresolved_only: params.get("unresolved_only") === "true",
    review_state: params.get("review_state") ?? undefined,
    sort: params.get("sort") ?? "priority",
    page: Number(params.get("page") ?? "1") || 1,
    page_size: 20,
  };
  const [search, setSearch] = useState(query.q ?? "");
  const result = useApiQuery(() => apiClient.reviewQueue(query), params.toString());

  function update(changes: Record<string, string | undefined>) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!("page" in changes)) next.delete("page");
    setParams(next);
  }

  const counts = result.data?.counts;
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Scrutiny work" breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Review queue" }]} title="Review queue"
        description="Applications ordered by unresolved findings. System findings are preliminary; review states are set by people." />
      {counts && (
        <dl aria-label="Queue summary" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Count label="Pending review" value={counts.pending_review} />
          <Count label="Unresolved high-severity findings" value={counts.unresolved_high} />
          <Count label="Awaiting additional evidence" value={counts.awaiting_additional_evidence} />
          <Count label="Preliminary scrutiny completed" value={counts.completed_preliminary_reviews} />
        </dl>
      )}
      <section aria-label="Search and filters" className="space-y-3 rounded-lg border border-line bg-surface p-4 shadow-sm">
        <form role="search" onSubmit={(e: FormEvent) => { e.preventDefault(); update({ q: search.trim() || undefined }); }}
          className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex-1">
            <TextField label="Search queue" type="search" placeholder="Application ID, institution name, code or state"
              value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <button type="submit" className={buttonStyles.secondary}><Search aria-hidden="true" className="h-4 w-4" /> Search</button>
        </form>
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <SelectField label="Application status" value={query.status ?? ""} placeholder="All" options={entries(STATUS_LABELS)}
            onChange={(e) => update({ status: e.target.value })} />
          <SelectField label="Scrutiny status" value={query.scrutiny_status ?? ""} placeholder="All" options={entries(SCRUTINY_STATUS)}
            onChange={(e) => update({ scrutiny_status: e.target.value })} />
          <SelectField label="Unresolved severity" value={query.severity ?? ""} placeholder="Any" options={entries(SEVERITY_LABELS)}
            onChange={(e) => update({ severity: e.target.value })} />
          <SelectField label="Review state" value={query.review_state ?? ""} placeholder="All" options={entries(REVIEW_STATE_LABELS)}
            onChange={(e) => update({ review_state: e.target.value })} />
          <SelectField label="Sort by" value={query.sort ?? "priority"} options={entries(SORTS)}
            onChange={(e) => update({ sort: e.target.value })} />
          <label className="flex items-end gap-2 pb-2 text-sm text-ink">
            <input type="checkbox" checked={!!query.unresolved_only} className="h-4 w-4"
              onChange={(e) => update({ unresolved_only: e.target.checked ? "true" : undefined })} />
            Unresolved only
          </label>
        </div>
      </section>

      {result.loading && !result.data ? <LoadingState label="Loading review queue…" /> : result.error ? (
        <ErrorState message={result.error} onRetry={result.reload} />
      ) : result.data && result.data.items.length === 0 ? (
        <EmptyState>No applications match these filters.</EmptyState>
      ) : result.data ? (
        <div>
          <div className={TABLE.wrap}>
            <table className={`${TABLE.table} min-w-[60rem]`}>
              <caption className="sr-only">Review queue</caption>
              <thead>
                <tr>
                  <th scope="col" className={TABLE.th}>Application</th>
                  <th scope="col" className={TABLE.th}>Latest scrutiny (system)</th>
                  <th scope="col" className={TABLE.th}>Unresolved findings</th>
                  <th scope="col" className={TABLE.th}>Evidence requests</th>
                  <th scope="col" className={TABLE.th}>Human review</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {result.data.items.map((i) => (
                  <tr key={i.application_code}>
                    <td className={TABLE.td}>
                      <Link to={`/applications/${i.application_code}`} className={`${buttonStyles.link} whitespace-nowrap font-mono`}>
                        {i.application_code}
                      </Link>
                      <div className="text-ink">{i.institution_name}</div>
                      <div className="text-xs text-ink-subtle">{STATUS_LABELS[i.status]} · {i.academic_year}</div>
                    </td>
                    <td className={TABLE.td}>
                      {i.latest_run_number
                        ? <>Run #{i.latest_run_number} · {SCRUTINY_STATUS[i.latest_run_status ?? ""] ?? i.latest_run_status}
                            <div className="text-xs text-ink-subtle">{formatDateTime(i.latest_run_finished_at)}</div></>
                        : <span className="text-ink-subtle">No scrutiny run</span>}
                    </td>
                    <td className={TABLE.td}>
                      <div className="flex flex-wrap gap-1">
                        {(["high", "medium", "low"] as Severity[]).map((s) => (i.unresolved_by_severity[s] ?? 0) > 0 && (
                          <Pill key={s} className={s === "high" ? "bg-danger-700 text-white ring-danger-700" : s === "medium"
                            ? "bg-saffron-100 text-warning-800 ring-warning-line" : "bg-info-bg text-info-700 ring-info-line"}>
                            {i.unresolved_by_severity[s]} {SEVERITY_LABELS[s].toLowerCase()}
                          </Pill>
                        ))}
                        {i.unresolved_total === 0 && <span className="text-ink-subtle">None</span>}
                      </div>
                    </td>
                    <td className={TABLE.td}>
                      {i.open_evidence_requests} open{i.overdue_evidence_requests > 0 && (
                        <span className="ml-1 font-semibold text-danger-700">({i.overdue_evidence_requests} overdue)</span>)}
                    </td>
                    <td className={TABLE.td}>{REVIEW_STATE_LABELS[i.review_state]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={result.data.page} totalPages={result.data.total_pages} total={result.data.total}
            onPage={(p) => update({ page: String(p) })} />
        </div>
      ) : null}
    </div>
  );
}

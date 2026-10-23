import { Plus, Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { ACADEMIC_YEARS, APPLICATION_TYPE_LABELS, STATUS_LABELS, entries, formatDateTime } from "../../app/labels";
import { useApiQuery } from "../../app/useApiQuery";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Pagination,
  SelectField,
  StatusBadge,
  TABLE,
  TextField,
  buttonStyles,
} from "../../components/ui";
import { apiClient } from "../../services/apiClient";
import type { ApplicationQuery, ApplicationStatus, ApplicationType } from "../../types/api";

const PAGE_SIZE = 20;

export function ApplicationsListPage() {
  const [params, setParams] = useSearchParams();
  const query: ApplicationQuery = {
    q: params.get("q") ?? undefined,
    status: (params.get("status") as ApplicationStatus | null) ?? undefined,
    academic_year: params.get("academic_year") ?? undefined,
    application_type: (params.get("application_type") as ApplicationType | null) ?? undefined,
    page: Number(params.get("page") ?? "1") || 1,
    page_size: PAGE_SIZE,
  };
  const [search, setSearch] = useState(query.q ?? "");
  const result = useApiQuery(() => apiClient.listApplications(query), params.toString());

  function update(changes: Record<string, string | undefined>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    if (!("page" in changes)) next.delete("page");
    setParams(next);
  }

  function onSearch(event: FormEvent) {
    event.preventDefault();
    update({ q: search.trim() || undefined });
  }

  const filtered = Boolean(query.q || query.status || query.academic_year || query.application_type);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Scrutiny work"
        breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Applications" }]}
        title="Applications"
        description="Extension of Approval applications recorded in ReguLens. Statuses are internal workflow states, not AICTE decisions."
        actions={
          <Link to="/applications/new" className={buttonStyles.primary}>
            <Plus aria-hidden="true" className="h-4 w-4" /> New application
          </Link>
        }
      />

      <section aria-label="Search and filters" className="rounded-lg border border-line bg-surface p-4 shadow-sm">
        <form role="search" onSubmit={onSearch} className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex-1">
            <TextField
              label="Search"
              type="search"
              placeholder="Application ID, institution name or code"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button type="submit" className={buttonStyles.secondary}>
            <Search aria-hidden="true" className="h-4 w-4" /> Search
          </button>
        </form>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <SelectField
            label="Status"
            value={query.status ?? ""}
            onChange={(e) => update({ status: e.target.value })}
            options={entries(STATUS_LABELS)}
            placeholder="All statuses"
          />
          <SelectField
            label="Academic year"
            value={query.academic_year ?? ""}
            onChange={(e) => update({ academic_year: e.target.value })}
            options={ACADEMIC_YEARS.map((y) => [y, y])}
            placeholder="All years"
          />
          <SelectField
            label="Application type"
            value={query.application_type ?? ""}
            onChange={(e) => update({ application_type: e.target.value })}
            options={entries(APPLICATION_TYPE_LABELS)}
            placeholder="All types"
          />
        </div>
        {filtered && (
          <button
            type="button"
            className={`${buttonStyles.link} mt-3 text-sm`}
            onClick={() => {
              setSearch("");
              setParams(new URLSearchParams());
            }}
          >
            Clear search and filters
          </button>
        )}
      </section>

      {result.loading && !result.data ? (
        <LoadingState label="Loading applications…" />
      ) : result.error ? (
        <ErrorState message={result.error} onRetry={result.reload} />
      ) : result.data && result.data.items.length === 0 ? (
        <EmptyState>
          {filtered ? "No applications match the current search or filters." : "No applications have been created yet."}{" "}
          <Link to="/applications/new" className={buttonStyles.link}>
            Create an application
          </Link>
        </EmptyState>
      ) : result.data ? (
        <div>
          <div className={TABLE.wrap}>
            <table className={`${TABLE.table} min-w-[52rem]`}>
              <caption className="sr-only">Applications</caption>
              <thead>
                <tr>
                  <th scope="col" className={TABLE.th}>Application ID</th>
                  <th scope="col" className={TABLE.th}>Institution</th>
                  <th scope="col" className={TABLE.th}>Academic year</th>
                  <th scope="col" className={TABLE.th}>Type</th>
                  <th scope="col" className={TABLE.th}>Status</th>
                  <th scope="col" className={TABLE.th}>Last updated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {result.data.items.map((a) => (
                  <tr key={a.application_code} className="hover:bg-surface-muted">
                    <td className={TABLE.td}>
                      <Link to={`/applications/${a.application_code}`} className={`${buttonStyles.link} whitespace-nowrap font-mono`}>
                        {a.application_code}
                      </Link>
                    </td>
                    <td className={TABLE.td}>
                      <div className="font-medium text-ink">{a.institution.name}</div>
                      <div className="text-xs text-ink-subtle">{a.institution.institution_code}</div>
                    </td>
                    <td className={TABLE.td}>{a.academic_year}</td>
                    <td className={TABLE.td}>{APPLICATION_TYPE_LABELS[a.application_type]}</td>
                    <td className={TABLE.td}>
                      <StatusBadge status={a.status} />
                    </td>
                    <td className={`${TABLE.td} whitespace-nowrap`}>{formatDateTime(a.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={result.data.page}
            totalPages={result.data.total_pages}
            total={result.data.total}
            onPage={(page) => update({ page: String(page) })}
          />
        </div>
      ) : null}
    </div>
  );
}

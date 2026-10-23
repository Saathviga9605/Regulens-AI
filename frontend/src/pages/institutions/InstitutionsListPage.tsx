import { Plus, Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { INSTITUTION_TYPE_LABELS, RECORD_STATUS_LABELS } from "../../app/labels";
import { useApiQuery } from "../../app/useApiQuery";
import { EmptyState, ErrorState, LoadingState, PageHeader, Pagination, TABLE, TextField, buttonStyles } from "../../components/ui";
import { apiClient } from "../../services/apiClient";

const PAGE_SIZE = 20;

export function InstitutionsListPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const page = Number(params.get("page") ?? "1") || 1;
  const [search, setSearch] = useState(q);
  const result = useApiQuery(() => apiClient.listInstitutions({ q: q || undefined, page, page_size: PAGE_SIZE }), params.toString());

  function onSearch(event: FormEvent) {
    event.preventDefault();
    setParams(search.trim() ? { q: search.trim() } : {});
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Institutions"
        description="Fictional institution records used for prototype EoA applications."
        actions={
          <Link to="/institutions/new" className={buttonStyles.primary}>
            <Plus aria-hidden="true" className="h-4 w-4" /> New institution
          </Link>
        }
      />
      <form role="search" onSubmit={onSearch} className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-end">
        <div className="flex-1">
          <TextField label="Search institutions" type="search" placeholder="Name or institution code" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <button type="submit" className={buttonStyles.secondary}>
          <Search aria-hidden="true" className="h-4 w-4" /> Search
        </button>
      </form>

      {result.loading && !result.data ? (
        <LoadingState label="Loading institutions…" />
      ) : result.error ? (
        <ErrorState message={result.error} onRetry={result.reload} />
      ) : result.data && result.data.items.length === 0 ? (
        <EmptyState>{q ? `No institutions match “${q}”.` : "No institutions have been created yet."}</EmptyState>
      ) : result.data ? (
        <div>
          <div className={TABLE.wrap}>
            <table className={TABLE.table}>
              <caption className="sr-only">Institutions</caption>
              <thead>
                <tr>
                  <th scope="col" className={TABLE.th}>Institution</th>
                  <th scope="col" className={TABLE.th}>Code</th>
                  <th scope="col" className={TABLE.th}>Type</th>
                  <th scope="col" className={TABLE.th}>Location</th>
                  <th scope="col" className={TABLE.th}>Record status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {result.data.items.map((i) => (
                  <tr key={i.institution_code} className="hover:bg-slate-50">
                    <td className={TABLE.td}>
                      <Link to={`/institutions/${i.institution_code}`} className={buttonStyles.link}>
                        {i.name}
                      </Link>
                    </td>
                    <td className={`${TABLE.td} font-mono`}>{i.institution_code}</td>
                    <td className={TABLE.td}>{INSTITUTION_TYPE_LABELS[i.institution_type]}</td>
                    <td className={TABLE.td}>
                      {i.district}, {i.state}
                    </td>
                    <td className={TABLE.td}>{RECORD_STATUS_LABELS[i.status]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={result.data.page}
            totalPages={result.data.total_pages}
            total={result.data.total}
            onPage={(p) => setParams({ ...(q ? { q } : {}), page: String(p) })}
          />
        </div>
      ) : null}
    </div>
  );
}

import { useState } from "react";

import { useApiQuery } from "../app/useApiQuery";
import { AuditTable } from "../pages/AuditTrailPage";
import { apiClient } from "../services/apiClient";
import { EmptyState, ErrorState, LoadingState, Pagination } from "./ui";

/** Audit events scoped to one application (visible to reviewers and administrators). */
export function ActivityLog({ applicationCode }: { applicationCode: string }) {
  const [page, setPage] = useState(1);
  const events = useApiQuery(() => apiClient.listApplicationAudit(applicationCode, page), `${applicationCode}:${page}`);
  if (events.loading && !events.data) return <LoadingState label="Loading activity…" />;
  if (events.error) return <ErrorState message={events.error} onRetry={events.reload} />;
  if (!events.data || events.data.items.length === 0) return <EmptyState>No recorded activity yet.</EmptyState>;
  return (
    <div className="space-y-2">
      <AuditTable events={events.data.items} />
      <Pagination page={events.data.page} totalPages={events.data.total_pages} total={events.data.total} onPage={setPage} />
    </div>
  );
}

import { useState } from "react";
import { Link } from "react-router";

import { ALERT_EVENT_LABELS, entries, formatDateTime } from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { Alert, EmptyState, ErrorState, LoadingState, PageHeader, Pagination, Pill, SelectField, buttonStyles } from "../components/ui";
import { ApiError, apiClient } from "../services/apiClient";
import type { AlertItem } from "../types/api";

export function AlertList({ applicationCode, compact = false }: { applicationCode?: string; compact?: boolean }) {
  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [eventType, setEventType] = useState("");
  const key = `${applicationCode}|${page}|${unreadOnly}|${eventType}`;
  const alerts = useApiQuery(() => apiClient.listAlerts({
    application_code: applicationCode, page, page_size: compact ? 10 : 20, unread_only: unreadOnly,
    event_type: eventType || undefined,
  }), key);
  const [error, setError] = useState<string | null>(null);

  async function markRead(ids: string[]) {
    setError(null);
    try {
      await apiClient.markAlertsRead(ids);
      alerts.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update alerts.");
    }
  }

  async function markAll() {
    setError(null);
    try {
      await apiClient.markAllAlertsRead(applicationCode);
      alerts.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update alerts.");
    }
  }

  const items: AlertItem[] = alerts.data?.items ?? [];
  return (
    <section aria-label={applicationCode ? `Alerts for ${applicationCode}` : "Alerts"} className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <SelectField label="Event type" value={eventType} placeholder="All events" options={entries(ALERT_EVENT_LABELS)}
          onChange={(e) => { setEventType(e.target.value); setPage(1); }} />
        <label className="flex items-center gap-2 pb-2 text-sm">
          <input type="checkbox" className="h-4 w-4" checked={unreadOnly} onChange={(e) => { setUnreadOnly(e.target.checked); setPage(1); }} />
          Unread only
        </label>
        <button type="button" className={buttonStyles.secondary} onClick={markAll}
          disabled={!alerts.data || alerts.data.unread_count === 0}>
          Mark all read
        </button>
        {alerts.data && <span className="pb-2 text-sm text-ink-muted">{alerts.data.unread_count} unread in total</span>}
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      {alerts.loading && !alerts.data ? <LoadingState label="Loading alerts…" /> : alerts.error ? (
        <ErrorState message={alerts.error} onRetry={alerts.reload} />
      ) : items.length === 0 ? (
        <EmptyState>No alerts{unreadOnly ? " are unread" : ""}.</EmptyState>
      ) : (
        <ul className="space-y-2">
          {items.map((a) => (
            <li key={a.id} className={`rounded-control border p-3 text-sm ${a.read ? "border-line bg-surface" : "border-info-line bg-info-bg"}`}>
              <div className="flex flex-wrap items-center gap-2">
                {!a.read && <Pill className="bg-brand-800 text-white ring-brand-800">Unread</Pill>}
                <Pill className="bg-surface-muted text-ink ring-line">{ALERT_EVENT_LABELS[a.event_type] ?? a.event_type}</Pill>
                <strong className="text-ink">{a.title}</strong>
                <span className="text-xs text-ink-subtle">{formatDateTime(a.created_at)}</span>
              </div>
              <p className="mt-1 text-ink">{a.message}</p>
              <div className="mt-2 flex gap-3">
                {!applicationCode && (
                  <Link to={`/applications/${a.application_code}`} className={`${buttonStyles.link} text-xs`}>Open {a.application_code}</Link>
                )}
                {!a.read && (
                  <button type="button" className={`${buttonStyles.link} text-xs`} onClick={() => markRead([a.id])}
                    aria-label={`Mark "${a.title}" as read`}>Mark read</button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {alerts.data && <Pagination page={alerts.data.page} totalPages={alerts.data.total_pages} total={alerts.data.total} onPage={setPage} />}
    </section>
  );
}

export function AlertsPage() {
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Scrutiny work" breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Alerts" }]} title="Alerts" description="Generated from scrutiny, review and evidence events. Read state is personal. No email or SMS is sent." />
      <AlertList />
    </div>
  );
}

import { ArrowRight, Bell, ClipboardList, FilePlus2, FileText } from "lucide-react";
import { Link } from "react-router";

import { useAuth } from "../app/AuthContext";
import { useBackendHealth } from "../app/BackendHealthContext";
import { ALERT_EVENT_LABELS, formatDateTime } from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { SystemStatusPanel } from "../components/SystemStatusPanel";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge, buttonStyles } from "../components/ui";
import { apiClient } from "../services/apiClient";

function Metric({ label, value, to, tone }: { label: string; value: number | undefined; to: string; tone: string }) {
  return (
    <Link to={to} className={`group block rounded-panel border border-line border-t-4 ${tone} bg-surface p-4 shadow-panel hover:border-brand-600`}>
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-subtle">{label}</dt>
      <dd className="mt-1 flex items-end justify-between">
        <span className="text-3xl font-semibold tabular-nums text-brand-900">{value ?? "—"}</span>
        <ArrowRight aria-hidden="true" className="h-4 w-4 text-ink-subtle group-hover:text-brand-700" />
      </dd>
    </Link>
  );
}

export function DashboardPage() {
  const { state, refresh } = useBackendHealth();
  const { user } = useAuth();
  const queue = useApiQuery(() => apiClient.reviewQueue({ page_size: 5 }), "overview-queue");
  const alerts = useApiQuery(() => apiClient.listAlerts({ page_size: 5 }), "overview-alerts");
  const recent = useApiQuery(() => apiClient.listApplications({ page_size: 5 }), "overview-apps");
  const counts = queue.data?.counts;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Overview" title={`Welcome, ${user?.display_name ?? "reviewer"}`}
        description="Extension of Approval (EoA) preliminary-scrutiny workspace. Figures below come from stored records."
        actions={<>
          <Link to="/review-queue" className={buttonStyles.primary}><ClipboardList aria-hidden="true" className="h-4 w-4" /> Open review queue</Link>
          <Link to="/applications/new" className={buttonStyles.secondary}><FilePlus2 aria-hidden="true" className="h-4 w-4" /> New application</Link>
        </>} />

      <section aria-labelledby="purpose-heading" className="rounded-panel border border-info-line bg-info-bg p-4 text-sm text-ink">
        <h2 id="purpose-heading" className="font-semibold text-brand-900">Decision support, not decision making</h2>
        <p className="mt-1">
          ReguLens organises evidence, checks applications against configurable rules and highlights items that may need
          attention. It never approves or rejects an application; a flagged anomaly is a prompt for human review, not a
          finding of misconduct.
        </p>
      </section>

      {queue.error ? <ErrorState message={queue.error} onRetry={queue.reload} /> : (
        <dl aria-label="Review summary" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Metric label="Pending review" value={counts?.pending_review} to="/review-queue?unresolved_only=true" tone="border-t-brand-700" />
          <Metric label="Unresolved high-severity" value={counts?.unresolved_high} to="/review-queue?severity=high" tone="border-t-danger-700" />
          <Metric label="Awaiting evidence" value={counts?.awaiting_additional_evidence} to="/review-queue" tone="border-t-saffron-500" />
          <Metric label="Preliminary reviews completed" value={counts?.completed_preliminary_reviews}
            to="/review-queue?status=preliminary_scrutiny_completed" tone="border-t-teal-700" />
        </dl>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card title="Highest-priority applications" actions={<Link to="/review-queue" className={`${buttonStyles.link} text-sm`}>View all</Link>}>
            {queue.loading && !queue.data ? <LoadingState label="Loading priorities…" /> : queue.data && queue.data.items.length === 0 ? (
              <EmptyState>No applications yet.</EmptyState>
            ) : (
              <ul className="divide-y divide-line">
                {(queue.data?.items ?? []).map((i) => (
                  <li key={i.application_code} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                    <div className="min-w-0">
                      <Link to={`/applications/${i.application_code}`} className={`${buttonStyles.link} font-mono text-sm`}>{i.application_code}</Link>
                      <p className="text-sm text-ink [overflow-wrap:anywhere]">{i.institution_name}</p>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {(i.unresolved_by_severity.high ?? 0) > 0 && <Badge tone="danger">{i.unresolved_by_severity.high} high</Badge>}
                      {i.unresolved_total > 0 ? <Badge tone="warning">{i.unresolved_total} unresolved</Badge> : (
                        <Badge tone={i.latest_run_number ? "success" : "neutral"}>{i.latest_run_number ? "No unresolved findings" : "No scrutiny yet"}</Badge>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <Card title="Recent alerts" actions={<Link to="/alerts" className={`${buttonStyles.link} text-sm`}>All alerts</Link>}>
          {alerts.loading && !alerts.data ? <LoadingState label="Loading alerts…" /> : alerts.error ? (
            <ErrorState message={alerts.error} onRetry={alerts.reload} />
          ) : (alerts.data?.items ?? []).length === 0 ? <EmptyState>No alerts.</EmptyState> : (
            <ul className="space-y-2">
              {alerts.data!.items.map((a) => (
                <li key={a.id} className="text-sm">
                  <div className="flex items-center gap-1.5">
                    <Bell aria-hidden="true" className={`h-4 w-4 ${a.read ? "text-ink-subtle" : "text-saffron-600"}`} />
                    <span className="font-medium text-ink">{ALERT_EVENT_LABELS[a.event_type] ?? a.title}</span>
                    {!a.read && <span className="sr-only">(unread)</span>}
                  </div>
                  <p className="text-xs text-ink-muted [overflow-wrap:anywhere]">{a.application_code} · {formatDateTime(a.created_at)}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card title="Recently created applications" actions={<Link to="/applications" className={`${buttonStyles.link} text-sm`}>All applications</Link>}>
            {recent.loading && !recent.data ? <LoadingState label="Loading applications…" /> : recent.error ? (
              <ErrorState message={recent.error} onRetry={recent.reload} />
            ) : (recent.data?.items ?? []).length === 0 ? <EmptyState>No applications yet.</EmptyState> : (
              <ul className="divide-y divide-line">
                {recent.data!.items.map((a) => (
                  <li key={a.application_code} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                    <span className="flex min-w-0 items-center gap-2">
                      <FileText aria-hidden="true" className="h-4 w-4 shrink-0 text-ink-subtle" />
                      <Link to={`/applications/${a.application_code}`} className={`${buttonStyles.link} font-mono`}>{a.application_code}</Link>
                      <span className="truncate text-ink-muted">{a.institution.name}</span>
                    </span>
                    <StatusBadge status={a.status} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <SystemStatusPanel state={state} onRetry={refresh} />
      </div>
    </div>
  );
}

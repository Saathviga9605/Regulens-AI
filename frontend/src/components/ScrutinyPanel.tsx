import { ClipboardCheck, FileDown, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import {
  FINDING_KIND_LABELS,
  OUTCOME_LABELS,
  OUTCOME_STYLES,
  REVIEW_STATUS_LABELS,
  REVIEW_STATUS_STYLES,
  SEVERITY_LABELS,
  SEVERITY_STYLES,
  entries,
  fieldLabel,
  formatDateTime,
} from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { ApiError, apiClient } from "../services/apiClient";
import type {
  ComparedValue,
  Finding,
  FindingDetail,
  FindingKind,
  FindingQuery,
  ReviewStatus,
  RuleOutcome,
  ScrutinyRun,
  Severity,
} from "../types/api";
import { ReviewActions } from "./ReviewActions";
import { Alert, Card, EmptyState, ErrorState, LoadingState, Pill, SelectField, TABLE, buttonStyles } from "./ui";

const RUN_STATUS_TEXT: Record<ScrutinyRun["status"], string> = {
  running: "Running",
  completed: "Completed",
  completed_with_warnings: "Completed with warnings",
  failed: "Failed",
};

function Tile({ label, value, className = "" }: { label: string; value: number; className?: string }) {
  return (
    <div className={`rounded-control border border-line bg-surface px-3 py-2 ${className}`}>
      <dt className="text-xs text-ink-subtle">{label}</dt>
      <dd className="text-xl font-semibold tabular-nums text-ink">{value}</dd>
    </div>
  );
}

function RunSummary({ run }: { run: ScrutinyRun }) {
  const s = run.summary;
  const outcomes = s.evaluation_outcomes;
  const severities = s.finding_severities;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm text-ink">
        <Pill className={run.status === "failed" ? OUTCOME_STYLES.issue : run.status === "completed" ? OUTCOME_STYLES.pass : OUTCOME_STYLES.inconclusive}>
          {RUN_STATUS_TEXT[run.status]}
        </Pill>
        <span>Run #{run.run_number} · scrutiny date {run.scrutiny_date} · started {formatDateTime(run.started_at)}</span>
        <span className="text-xs text-ink-subtle">rule set {run.rule_set_version}</span>
      </div>
      {run.failure_reason && <Alert tone="error">{run.failure_reason}</Alert>}
      {run.warnings.length > 0 && (
        <Alert tone="info">
          <ul className="list-disc pl-4">{run.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </Alert>
      )}
      {outcomes && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">Rule evaluations by outcome</h4>
          <dl className="mt-1 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(Object.keys(OUTCOME_LABELS) as RuleOutcome[]).map((o) => (
              <Tile key={o} label={OUTCOME_LABELS[o]} value={outcomes[o] ?? 0} />
            ))}
          </dl>
        </div>
      )}
      {severities && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">
            Findings by severity ({s.rule_findings ?? 0} rule findings, {s.anomaly_indicators ?? 0} anomaly indicators)
          </h4>
          <dl className="mt-1 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(["high", "medium", "low", "info"] as Severity[]).map((sev) => (
              <Tile key={sev} label={SEVERITY_LABELS[sev]} value={severities[sev] ?? 0} />
            ))}
          </dl>
          <p className="mt-1 text-xs text-ink-subtle">
            {s.documents_considered ?? 0} document(s) considered, {s.documents_processed_ok ?? 0} readable · {s.rules_evaluated ?? 0} enabled rules
          </p>
        </div>
      )}
    </div>
  );
}

function ComparedValues({ values }: { values: ComparedValue[] }) {
  if (values.length === 0) return null;
  return (
    <div>
      <h5 className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">Values compared</h5>
      <ul className="mt-1 space-y-0.5 text-sm">
        {values.map((v, i) => (
          <li key={i}>
            {Object.entries(v).map(([k, val]) => `${fieldLabel(k)}: ${val === null || val === undefined ? "—" : String(val)}`).join(" · ")}
          </li>
        ))}
      </ul>
    </div>
  );
}

function FindingDetailView({ applicationCode, findingId, onReviewed, isLatestRun }: {
  applicationCode: string; findingId: string; onReviewed: (f: FindingDetail) => void; isLatestRun: boolean;
}) {
  const [version, setVersion] = useState(0);
  const detail = useApiQuery(() => apiClient.getFinding(applicationCode, findingId), `${findingId}:${version}`);

  if (detail.loading && !detail.data) return <LoadingState label="Loading finding…" />;
  if (detail.error) return <ErrorState message={detail.error} onRetry={detail.reload} />;
  const f = detail.data;
  if (!f) return null;

  async function refresh() {
    try {
      const updated = await apiClient.getFinding(applicationCode, findingId);
      detail.setData(updated);
      onReviewed(updated);
    } catch {
      setVersion((v) => v + 1);
    }
  }

  return (
    <article aria-label={`Finding: ${f.title}`} className="space-y-3 rounded-control border border-line-strong bg-surface p-4">
      <header className="space-y-1">
        <div className="flex flex-wrap gap-2">
          <Pill className={SEVERITY_STYLES[f.severity]}>{SEVERITY_LABELS[f.severity]} severity</Pill>
          <Pill className={OUTCOME_STYLES[f.outcome]}>{OUTCOME_LABELS[f.outcome]}</Pill>
          <Pill className="bg-surface-muted text-ink ring-line">{FINDING_KIND_LABELS[f.kind]}</Pill>
        </div>
        <h4 className="text-base font-semibold text-ink">{f.title}</h4>
      </header>

      <section aria-label="System-generated result" className="space-y-2">
        <h5 className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">System-generated explanation</h5>
        <p className="text-sm text-ink">{f.explanation}</p>
        {f.uncertainty && <p className="text-sm text-warning-800"><strong>Uncertainty:</strong> {f.uncertainty}</p>}
        {f.missing_evidence && <p className="text-sm text-ink"><strong>Missing evidence:</strong> {f.missing_evidence}</p>}
        {f.kind === "anomaly_indicator" && (
          <p className="text-xs text-ink-subtle">Anomaly indicators are prompts for attention. They are not conclusions and never establish misconduct.</p>
        )}
        {f.evidence.length > 0 && (
          <div>
            <h5 className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">Supporting evidence</h5>
            <ul className="mt-1 space-y-2">
              {f.evidence.map((e, i) => (
                <li key={i} className="text-sm">
                  <span className="font-medium">{e.document_filename}</span>
                  {e.page_number && <> · page {e.page_number}</>}
                  {e.field_name && <> · {fieldLabel(e.field_name)}</>}
                  {e.quote && (
                    <blockquote className="mt-1 border-l-2 border-info-line pl-2 font-mono text-xs text-ink [overflow-wrap:anywhere]">
                      {e.quote}
                    </blockquote>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        <ComparedValues values={f.compared_values} />
        {f.rule ? (
          <div className="rounded border border-line bg-surface-muted p-2 text-xs text-ink">
            <p>
              Rule <strong>{f.rule.rule_id}</strong> v{f.rule.version}: {f.rule.title}
            </p>
            <p>Source: {f.rule.source}{f.rule.source_reference ? ` — ${f.rule.source_reference}` : ""}</p>
            <p>Source verification: {f.rule.source_verification_status.replace("_", " ")}</p>
            {f.rule.is_demo_only && (
              <p className="mt-1 font-semibold text-warning-800">DEMO-ONLY RULE — not a verified AICTE requirement.</p>
            )}
          </div>
        ) : f.detector && <p className="text-xs text-ink-subtle">Detector: {f.detector}</p>}
      </section>

      {isLatestRun ? (
        <ReviewActions applicationCode={applicationCode} finding={f} onChanged={refresh} />
      ) : (
        <p className="border-t border-line pt-3 text-sm text-ink-muted">
          Human review state: <strong>{REVIEW_STATUS_LABELS[f.review_status]}</strong>. This finding belongs to an earlier run;
          review actions are taken on the latest run.
        </p>
      )}
    </article>
  );
}

function FindingRow({ f, selected, onSelect }: { f: Finding; selected: boolean; onSelect: () => void }) {
  return (
    <li>
      <button type="button" onClick={onSelect} aria-pressed={selected}
        className={`flex w-full flex-col gap-1 rounded-control border px-3 py-2 text-left text-sm hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-saffron-500 sm:flex-row sm:items-center sm:justify-between ${selected ? "border-brand-600 bg-info-bg" : "border-line bg-surface"}`}>
        <span className="flex flex-wrap items-center gap-2">
          <Pill className={SEVERITY_STYLES[f.severity]}>{SEVERITY_LABELS[f.severity]}</Pill>
          <Pill className={OUTCOME_STYLES[f.outcome]}>{OUTCOME_LABELS[f.outcome]}</Pill>
          <span className="font-medium text-ink">{f.title}</span>
        </span>
        <Pill className={REVIEW_STATUS_STYLES[f.review_status]}>{REVIEW_STATUS_LABELS[f.review_status]}</Pill>
      </button>
    </li>
  );
}

function EvaluationsTable({ run }: { run: ScrutinyRun }) {
  return (
    <details className="rounded-control border border-line bg-surface">
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-ink">
        All rule evaluations ({run.evaluations.length}) — including passes and not-applicable results
      </summary>
      <div className="overflow-x-auto">
        <table className={TABLE.table}>
          <caption className="sr-only">All rule evaluations for run {run.run_number}</caption>
          <thead>
            <tr>
              <th scope="col" className={TABLE.th}>Rule</th>
              <th scope="col" className={TABLE.th}>Outcome</th>
              <th scope="col" className={TABLE.th}>Explanation</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {run.evaluations.map((e) => (
              <tr key={e.id}>
                <td className={`${TABLE.td} whitespace-nowrap font-mono text-xs`}>{e.rule_id} v{e.rule_version}</td>
                <td className={TABLE.td}><Pill className={OUTCOME_STYLES[e.outcome]}>{OUTCOME_LABELS[e.outcome]}</Pill></td>
                <td className={`${TABLE.td} text-xs`}>{e.explanation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

interface PanelProps {
  applicationCode: string;
  onRunCompleted: () => void;
  /** A finding to open (e.g. from a copilot source); changes when a new source is clicked. */
  focus?: { findingId: string; nonce: number } | null;
}

export function ScrutinyPanel({ applicationCode, onRunCompleted, focus }: PanelProps) {
  const [version, setVersion] = useState(0);
  const runs = useApiQuery(() => apiClient.listScrutinyRuns(applicationCode), `${applicationCode}:${version}`);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const runId = selectedRunId ?? runs.data?.items[0]?.id ?? null;
  const run = useApiQuery(() => (runId ? apiClient.getScrutinyRun(applicationCode, runId) : Promise.resolve(null)), runId ?? "none");
  const [filters, setFilters] = useState<FindingQuery>({});
  const findingsKey = `${runId}|${JSON.stringify(filters)}|${version}`;
  const findings = useApiQuery(
    () => (runId ? apiClient.listRunFindings(applicationCode, runId, filters) : Promise.resolve(null)), findingsKey);
  const [selectedFinding, setSelectedFinding] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reportState, setReportState] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [downloading, setDownloading] = useState(false);
  const latestRunId = runs.data?.items[0]?.id ?? null;

  useEffect(() => {
    if (!focus) return;
    setSelectedRunId(null); // findings referenced by the copilot belong to the latest run
    setFilters({});
    setSelectedFinding(focus.findingId);
  }, [focus]);

  async function downloadReport() {
    if (!runId) return;
    setDownloading(true);
    setReportState(null);
    try {
      const name = await apiClient.downloadReport(applicationCode, runId);
      setReportState({ tone: "success", text: `Downloaded ${name}.` });
    } catch (err) {
      setReportState({ tone: "error", text: err instanceof ApiError ? err.message : "The report could not be generated." });
    } finally {
      setDownloading(false);
    }
  }

  async function startRun() {
    setRunning(true);
    setError(null);
    try {
      const created = await apiClient.startScrutinyRun(applicationCode);
      setSelectedRunId(created.id);
      setSelectedFinding(null);
      setVersion((v) => v + 1);
      onRunCompleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The scrutiny run could not be started.");
    } finally {
      setRunning(false);
    }
  }

  const items = findings.data?.items ?? [];
  const ruleFindings = items.filter((f) => f.kind === "rule_finding");
  const indicators = items.filter((f) => f.kind === "anomaly_indicator");

  return (
    <Card
      title="Preliminary scrutiny"
      actions={
        <button type="button" className={buttonStyles.primary} onClick={startRun} disabled={running}>
          {running ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : <ClipboardCheck aria-hidden="true" className="h-4 w-4" />}
          {running ? "Running…" : runs.data?.total ? "Rerun preliminary scrutiny" : "Run preliminary scrutiny"}
        </button>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-ink-muted">
          Runs the configured rules over processed documents (unprocessed documents are processed first). Results are
          preliminary indicators for human review — nothing here approves or rejects the application or establishes
          misconduct.
        </p>
        {running && <div role="status" className="text-sm text-ink">Processing documents and evaluating rules…</div>}
        {error && <Alert tone="error">{error}</Alert>}

        {runs.loading && !runs.data ? (
          <LoadingState label="Loading scrutiny runs…" />
        ) : runs.error ? (
          <ErrorState message={runs.error} onRetry={runs.reload} />
        ) : !runs.data || runs.data.items.length === 0 ? (
          <EmptyState>No scrutiny runs yet. Upload documents and run preliminary scrutiny.</EmptyState>
        ) : (
          <>
            <SelectField
              label="Scrutiny run"
              value={runId ?? ""}
              onChange={(e) => { setSelectedRunId(e.target.value); setSelectedFinding(null); }}
              options={runs.data.items.map((r) => [r.id, `Run #${r.run_number} — ${formatDateTime(r.started_at)} — ${RUN_STATUS_TEXT[r.status]}`])}
            />
            {run.loading && !run.data ? <LoadingState label="Loading run…" /> : run.error ? (
              <ErrorState message={run.error} onRetry={run.reload} />
            ) : run.data ? (
              <>
                <RunSummary run={run.data} />
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" className={buttonStyles.secondary} onClick={downloadReport}
                    disabled={downloading || run.data.status === "failed" || run.data.status === "running"}>
                    <FileDown aria-hidden="true" className="h-4 w-4" />
                    {downloading ? "Generating report…" : `Download preliminary report (run #${run.data.run_number})`}
                  </button>
                  {reportState && <span role="status" className={`text-sm ${reportState.tone === "error" ? "text-danger-700" : "text-success-700"}`}>{reportState.text}</span>}
                </div>
                <section aria-label="Findings" className="space-y-3">
                  <div className="grid gap-2 sm:grid-cols-3">
                    <SelectField label="Severity" value={filters.severity ?? ""} placeholder="All severities"
                      options={entries(SEVERITY_LABELS)}
                      onChange={(e) => setFilters({ ...filters, severity: (e.target.value || undefined) as Severity | undefined })} />
                    <SelectField label="Finding type" value={filters.kind ?? ""} placeholder="All types"
                      options={entries(FINDING_KIND_LABELS)}
                      onChange={(e) => setFilters({ ...filters, kind: (e.target.value || undefined) as FindingKind | undefined })} />
                    <SelectField label="Review status" value={filters.review_status ?? ""} placeholder="All review statuses"
                      options={entries(REVIEW_STATUS_LABELS)}
                      onChange={(e) => setFilters({ ...filters, review_status: (e.target.value || undefined) as ReviewStatus | undefined })} />
                  </div>
                  {findings.loading && !findings.data ? <LoadingState label="Loading findings…" /> : findings.error ? (
                    <ErrorState message={findings.error} onRetry={findings.reload} />
                  ) : items.length === 0 ? (
                    <EmptyState>
                      {Object.values(filters).some(Boolean)
                        ? "No findings match these filters."
                        : "No findings in this run. Every enabled rule passed or was not applicable — see all evaluations below."}
                    </EmptyState>
                  ) : (
                    <div className="grid gap-4 lg:grid-cols-2">
                      <div className="space-y-4">
                        {ruleFindings.length > 0 && (
                          <div>
                            <h4 className="mb-2 text-sm font-semibold text-ink">Rule findings ({ruleFindings.length})</h4>
                            <ul className="space-y-2">
                              {ruleFindings.map((f) => (
                                <FindingRow key={f.id} f={f} selected={selectedFinding === f.id} onSelect={() => setSelectedFinding(f.id)} />
                              ))}
                            </ul>
                          </div>
                        )}
                        {indicators.length > 0 && (
                          <div>
                            <h4 className="mb-1 text-sm font-semibold text-ink">Anomaly indicators ({indicators.length})</h4>
                            <p className="mb-2 text-xs text-ink-subtle">Prompts for attention, not conclusions.</p>
                            <ul className="space-y-2">
                              {indicators.map((f) => (
                                <FindingRow key={f.id} f={f} selected={selectedFinding === f.id} onSelect={() => setSelectedFinding(f.id)} />
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                      <div>
                        {selectedFinding ? (
                          <FindingDetailView key={selectedFinding} applicationCode={applicationCode} findingId={selectedFinding}
                            isLatestRun={runId === latestRunId}
                            onReviewed={(updated) => findings.setData({
                              ...findings.data!,
                              items: items.map((x) => (x.id === updated.id
                                ? { ...x, review_status: updated.review_status, review_version: updated.review_version,
                                    allowed_actions: updated.allowed_actions } : x)),
                            })} />
                        ) : (
                          <p className="rounded-control border border-dashed border-line-strong p-4 text-sm text-ink-subtle">
                            Select a finding to see its explanation and evidence.
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </section>
                <EvaluationsTable run={run.data} />
              </>
            ) : null}
          </>
        )}
      </div>
    </Card>
  );
}

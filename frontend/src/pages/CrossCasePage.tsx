import { useState } from "react";
import { Link } from "react-router";

import { useAuth } from "../app/AuthContext";
import { PAIR_REVIEW_LABELS, REUSE_OUTCOME_LABELS, REUSE_OUTCOME_TONES, formatDateTime } from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { useToast } from "../components/Toast";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Pagination,
  SelectField,
  TABLE,
  buttonStyles,
} from "../components/ui";
import { ApiError, apiClient, deliverBlob } from "../services/apiClient";
import type { ArmMetrics, EvaluationDetail, Ratio, ReuseOutcome } from "../types/api";

const OUTCOMES: [ReuseOutcome | "", string][] = [["", "All outcomes"], ...Object.entries(REUSE_OUTCOME_LABELS) as [ReuseOutcome, string][]];

export function CrossCasePage() {
  const { user } = useAuth();
  const authorised = Boolean(user?.cross_case_reviewer);
  const canEvaluate = authorised || user?.role === "admin";
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Scrutiny work" title="Cross-case document reuse"
        breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Cross-case reuse" }]}
        description="Pairs of documents from different cases that may share underlying content. Matching outcomes are prompts for human review, not findings of misconduct." />
      {authorised ? <PairList /> : (
        <Alert tone="info" title="Restricted">Linked-case details require the cross-case reviewer permission. Each
          application's workspace shows a restricted alert when one of its documents may match another case.</Alert>)}
      {canEvaluate && <EvaluationPanel />}
    </div>
  );
}

function PairList() {
  const [page, setPage] = useState(1);
  const [outcome, setOutcome] = useState<ReuseOutcome | "">("MATCH_CONFIRMED_FOR_REVIEW");
  const pairs = useApiQuery(() => apiClient.listCasePairs({ page, page_size: 20, outcome: outcome || undefined }),
    `${page}:${outcome}`);
  return (
    <Card title="Case pairs" actions={<div className="w-56"><SelectField label="Outcome" value={outcome}
      options={OUTCOMES} onChange={(e) => { setOutcome(e.target.value as ReuseOutcome | ""); setPage(1); }} /></div>}>
      {pairs.loading && !pairs.data ? <LoadingState label="Loading pairs…" /> : pairs.error ? (
        <ErrorState message={pairs.error} onRetry={pairs.reload} />
      ) : (pairs.data?.items ?? []).length === 0 ? <EmptyState>No pairs with this outcome.</EmptyState> : (
        <>
          <div className={TABLE.wrap}>
            <table className={`${TABLE.table} min-w-[56rem]`}>
              <caption className="sr-only">Case pairs</caption>
              <thead><tr>
                <th scope="col" className={TABLE.th}>Outcome</th>
                <th scope="col" className={TABLE.th}>Case A</th>
                <th scope="col" className={TABLE.th}>Case B</th>
                <th scope="col" className={TABLE.th}>Review</th>
                <th scope="col" className={TABLE.th}>Detected</th>
                <th scope="col" className={TABLE.th}><span className="sr-only">Open</span></th>
              </tr></thead>
              <tbody className="divide-y divide-line">
                {pairs.data!.items.map((p) => (
                  <tr key={p.id}>
                    <td className={TABLE.td}><Badge tone={REUSE_OUTCOME_TONES[p.outcome]}>{REUSE_OUTCOME_LABELS[p.outcome]}</Badge></td>
                    <td className={`${TABLE.td} [overflow-wrap:anywhere]`}><span className="font-mono">{p.a.application_code}</span><br />{p.a.filename}</td>
                    <td className={`${TABLE.td} [overflow-wrap:anywhere]`}><span className="font-mono">{p.b.application_code}</span><br />{p.b.filename}</td>
                    <td className={TABLE.td}>{PAIR_REVIEW_LABELS[p.review_status]}</td>
                    <td className={`${TABLE.td} text-xs`}>{formatDateTime(p.created_at)}</td>
                    <td className={TABLE.td}><Link className={buttonStyles.link} to={`/case-pairs/${p.id}`}>Open comparison</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} totalPages={pairs.data!.total_pages} total={pairs.data!.total} onPage={setPage} />
        </>
      )}
    </Card>
  );
}

function fmt(r: Ratio) {
  return r.value === null ? `n/a (${r.numerator}/${r.denominator})` : `${r.value.toFixed(2)} (${r.numerator}/${r.denominator})`;
}

function EvaluationPanel() {
  const list = useApiQuery(() => apiClient.listReuseEvaluations(), "evaluations");
  const [current, setCurrent] = useState<EvaluationDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  async function run() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await apiClient.runReuseEvaluation();
      setCurrent(result);
      list.reload();
      toast("Evaluation completed.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The evaluation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function open(id: string) {
    setError(null);
    try {
      setCurrent(await apiClient.getReuseEvaluation(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the evaluation.");
    }
  }

  async function download(format: "csv" | "md" | "json") {
    if (!current) return;
    try {
      const { blob, filename } = await apiClient.exportReuseEvaluation(current.id, format);
      deliverBlob(blob, filename ?? `reuse-evaluation.${format}`, "download");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Export failed.");
    }
  }

  return (
    <Card title="A0 / A1 / A4 evaluation (synthetic fixtures)"
      description="Exact hash (A0), perceptual hash only (A1) and the full cascade (A4) on the same labelled synthetic pairs. With OCR enabled this takes several minutes."
      actions={<button type="button" className={buttonStyles.secondary} onClick={run} disabled={busy}>
        {busy ? "Evaluating…" : "Run evaluation"}</button>}>
      {error && <Alert tone="error">{error}</Alert>}
      {list.data && list.data.length > 0 && (
        <p className="mb-3 text-sm text-ink-muted">Previous runs:{" "}
          {list.data.slice(0, 5).map((e) => (
            <button key={e.id} type="button" className={`${buttonStyles.link} mr-2 text-sm`} onClick={() => open(e.id)}>
              {formatDateTime(e.created_at)}</button>
          ))}
        </p>
      )}
      {!current ? <p className="text-sm text-ink-muted">Run an evaluation or open a previous run to see measured metrics.</p> : (
        <div className="space-y-4" data-testid="evaluation-result">
          <p className="text-xs text-ink-subtle">Dataset {current.dataset_version} ({current.dataset_digest}) · thresholds{" "}
            {current.config_version} · A1 pHash ≤ {current.results.a1_threshold} · OCR {current.results.environment.ocr_available ? "available" : "not available"}
            {" "}· synthetic data; no statistical significance is claimed.</p>
          {Object.entries(current.results.metrics).map(([split, arms]) => (
            <div key={split} className={TABLE.wrap}>
              <table className={`${TABLE.table} min-w-[44rem]`}>
                <caption className="px-3 py-2 text-left text-sm font-semibold text-ink">Split: {split}</caption>
                <thead><tr>{["Arm", "TP", "FP", "TN", "FN", "Precision", "Recall", "Hard-negative FP"].map((h) =>
                  <th key={h} scope="col" className={TABLE.th}>{h}</th>)}</tr></thead>
                <tbody className="divide-y divide-line">
                  {(Object.entries(arms) as [string, ArmMetrics][]).map(([arm, m]) => (
                    <tr key={arm}>
                      <th scope="row" className={TABLE.td}>{arm}</th>
                      <td className={TABLE.td}>{m.tp}</td><td className={TABLE.td}>{m.fp}</td>
                      <td className={TABLE.td}>{m.tn}</td><td className={TABLE.td}>{m.fn}</td>
                      <td className={TABLE.td}>{fmt(m.precision)}</td><td className={TABLE.td}>{fmt(m.recall)}</td>
                      <td className={TABLE.td}>{m.hard_negative_fp}/{m.hard_negative_fp_rate.denominator}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          <p className="text-sm text-ink">Evidence traceability: {fmt(current.results.evidence_traceability)}.{" "}
            Field exact match: {Object.entries(current.results.field_exact_match).map(([k, r]) => `${k.replace(/_/g, " ")} ${r.numerator}/${r.denominator}`).join(" · ")}.</p>
          {current.results.environment.unavailable_stages.length > 0 && (
            <Alert tone="warning" title="Stages that could not run">{current.results.environment.unavailable_stages.join(" ")}</Alert>
          )}
          <div className="flex flex-wrap gap-2">
            {(["csv", "md", "json"] as const).map((f) => (
              <button key={f} type="button" className={buttonStyles.secondary} onClick={() => download(f)}>Export {f.toUpperCase()}</button>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

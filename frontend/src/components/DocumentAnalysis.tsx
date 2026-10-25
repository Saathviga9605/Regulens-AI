import { FileSearch, Loader2, RefreshCw, ShieldQuestion } from "lucide-react";
import { useState } from "react";

import {
  DOCUMENT_CATEGORY_LABELS,
  FIELD_STATUS_LABELS,
  FIELD_STATUS_STYLES,
  PAGE_STATUS_LABELS,
  PROCESSING_STATUS_LABELS,
  PROCESSING_STATUS_STYLES,
  SIMULATION_LABEL,
  VERIFICATION_OUTCOME_LABELS,
  fieldLabel,
  formatDateTime,
} from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { ApiError, apiClient } from "../services/apiClient";
import type { ApplicationDocument, DocumentPageText, ExtractedField, ProcessingResult, VerificationAttempt } from "../types/api";
import { Alert, ErrorState, LoadingState, Pill, TABLE, buttonStyles } from "./ui";

/** Loads the stored processing result; a 404 "not_processed" is a normal state, not an error. */
async function loadProcessing(id: string): Promise<ProcessingResult | null> {
  try {
    return await apiClient.getProcessing(id);
  } catch (err) {
    if (err instanceof ApiError && err.code === "not_processed") return null;
    throw err;
  }
}

function normalizedText(f: ExtractedField): string | null {
  const n = f.normalized_value;
  if (!n) return null;
  if (typeof n.date === "string") return n.date;
  if (n.value_sq_m != null) return `${Number(n.value_sq_m).toLocaleString("en-IN")} sq m`;
  if (n.value != null && n.unit == null) return "unit not recognised";
  return null;
}

function FieldsTable({ fields }: { fields: ExtractedField[] }) {
  if (fields.length === 0) return <p className="text-sm text-ink-muted">No fields were extracted.</p>;
  return (
    <div className={TABLE.wrap}>
      <table className={TABLE.table}>
        <caption className="sr-only">Extracted fields with evidence</caption>
        <thead>
          <tr>
            <th scope="col" className={TABLE.th}>Field</th>
            <th scope="col" className={TABLE.th}>Value</th>
            <th scope="col" className={TABLE.th}>Status</th>
            <th scope="col" className={TABLE.th}>Evidence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {fields.map((f) => (
            <tr key={f.id}>
              <th scope="row" className={`${TABLE.td} text-left font-medium text-ink`}>{fieldLabel(f.field_name)}</th>
              <td className={TABLE.td}>
                {f.raw_value ? (
                  <>
                    <div className="[overflow-wrap:anywhere]">{f.raw_value}</div>
                    {normalizedText(f) && <div className="text-xs text-ink-subtle">Normalised: {normalizedText(f)}</div>}
                  </>
                ) : (
                  <span className="text-ink-subtle">—</span>
                )}
              </td>
              <td className={TABLE.td}>
                <Pill className={FIELD_STATUS_STYLES[f.status]}>{FIELD_STATUS_LABELS[f.status]}</Pill>
                {f.status !== "not_found" && <div className="mt-1 text-xs text-ink-subtle">{f.confidence} confidence</div>}
              </td>
              <td className={TABLE.td}>
                {f.evidence_quote ? (
                  <figure>
                    <blockquote className="border-l-2 border-info-line pl-2 font-mono text-xs text-ink [overflow-wrap:anywhere]">
                      {f.evidence_quote}
                    </blockquote>
                    <figcaption className="mt-1 text-xs text-ink-subtle">
                      Page {f.page_number} · {f.method} · {f.evidence_source === "ocr" ? "read by OCR" : "text layer"}
                      {f.ocr_confidence != null && ` · OCR score ${f.ocr_confidence.toFixed(2)}`}
                      {f.evidence_box ? " · location recorded" : f.evidence_source ? " · location not recorded" : ""}
                    </figcaption>
                  </figure>
                ) : (
                  <span className="text-xs text-ink-subtle">No evidence in readable text</span>
                )}
                {f.candidates.length > 0 && (
                  <ul className="mt-1 list-disc pl-4 text-xs text-warning-800">
                    {f.candidates.map((c) => (
                      <li key={`${c.page_number}-${c.value}`}>“{c.value}” (p.{c.page_number})</li>
                    ))}
                  </ul>
                )}
                {f.warnings.map((w) => (
                  <p key={w} className="mt-1 text-xs text-warning-800">{w}</p>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PageTexts({ documentId }: { documentId: string }) {
  const [pages, setPages] = useState<DocumentPageText[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setPages((await apiClient.getDocumentPages(documentId)).items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load page text.");
    } finally {
      setLoading(false);
    }
  }

  if (!pages) {
    return (
      <div>
        <button type="button" className={buttonStyles.secondary} onClick={load} disabled={loading}>
          <FileSearch aria-hidden="true" className="h-4 w-4" /> {loading ? "Loading…" : "Show extracted page text"}
        </button>
        {error && <p role="alert" className="mt-2 text-sm text-danger-700">{error}</p>}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {pages.map((p) => (
        <details key={p.page_number} className="rounded border border-line bg-surface">
          <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-ink">
            Page {p.page_number} · {p.method.replace("_", " ")} · {PAGE_STATUS_LABELS[p.status]} · {p.char_count} characters
            {p.ocr_engine && ` · OCR ${p.ocr_engine}${p.ocr_confidence != null ? ` (score ${p.ocr_confidence.toFixed(2)})` : ""}`}
            {p.rotation_degrees ? ` · rotated ${p.rotation_degrees}°` : ""}
          </summary>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap border-t border-line px-3 py-2 font-mono text-xs text-ink">
            {p.text || "(no text)"}
          </pre>
        </details>
      ))}
    </div>
  );
}

function SimulatedIssuerChecks({ documentId, enabled }: { documentId: string; enabled: boolean }) {
  const attempts = useApiQuery(() => apiClient.listIssuerChecks(documentId), documentId);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const attempt = await apiClient.runSimulatedIssuerCheck(documentId);
      attempts.setData([attempt, ...(attempts.data ?? [])]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Simulated check failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section aria-label="Simulated issuer verification" className="space-y-2">
      <div className="rounded-control border-2 border-warning-line bg-warning-bg px-3 py-2 text-sm font-semibold text-warning-800">
        {SIMULATION_LABEL}
        <p className="mt-0.5 text-xs font-normal">
          Compares extracted fields with configured synthetic demo records only. No issuing authority is contacted.
        </p>
      </div>
      <button type="button" className={buttonStyles.secondary} onClick={run} disabled={running || !enabled}>
        <ShieldQuestion aria-hidden="true" className="h-4 w-4" /> {running ? "Checking…" : "Run simulated issuer check"}
      </button>
      {!enabled && <p className="text-xs text-ink-subtle">Available after the document has been processed successfully.</p>}
      {error && <p role="alert" className="text-sm text-danger-700">{error}</p>}
      {attempts.error && <p className="text-sm text-danger-700">{attempts.error}</p>}
      {attempts.data && attempts.data.length === 0 && (
        <p className="text-sm text-ink" data-testid="source-status-pending">
          Source-verification status: <strong>Verification pending</strong>{" "}
          <Pill className="bg-surface-muted text-ink-muted ring-line">no check run yet</Pill>
        </p>
      )}
      {(attempts.data ?? []).map((a: VerificationAttempt) => (
        <div key={a.id} className="rounded border border-warning-line bg-surface p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span>Source-verification status:</span>
            <strong data-testid="source-status">{a.source_status_label}</strong>
            <Pill className={a.source_type === "LIVE" ? "bg-success-bg text-success-700 ring-success-line"
              : "bg-warning-bg text-warning-800 ring-warning-line"}>{a.source_type.replace("_", " ")}</Pill>
            <span className="text-xs text-ink-subtle">{formatDateTime(a.created_at)}</span>
          </div>
          <p className="mt-1 text-xs text-ink-subtle">
            Adapter result: {VERIFICATION_OUTCOME_LABELS[a.outcome]} · {a.simulation_label ?? "Not simulated"}
          </p>
          <p className="mt-1 text-ink">{a.explanation}</p>
          {a.fields_compared.length > 0 && (
            <ul className="mt-1 text-xs text-ink-muted">
              {a.fields_compared.map((c) => (
                <li key={c.field}>
                  {fieldLabel(c.field)}: {c.document_value ?? "—"} → {c.result.replace("_", " ")}
                </li>
              ))}
            </ul>
          )}
          {a.reference_code && <p className="mt-1 text-xs text-ink-subtle">Synthetic reference: {a.reference_code}</p>}
        </div>
      ))}
    </section>
  );
}

export function DocumentAnalysis({ doc, onProcessed }: { doc: ApplicationDocument; onProcessed: () => void }) {
  const result = useApiQuery(() => loadProcessing(doc.id), doc.id);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function process(force: boolean) {
    setProcessing(true);
    setError(null);
    try {
      result.setData(await apiClient.processDocument(doc.id, force));
      onProcessed();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Processing failed unexpectedly.");
    } finally {
      setProcessing(false);
    }
  }

  if (result.loading && result.data === null) return <LoadingState label="Loading analysis…" />;
  if (result.error) return <ErrorState message={result.error} onRetry={result.reload} />;
  const r = result.data;

  return (
    <section aria-label={`Analysis of ${doc.original_filename}`} className="space-y-4 border-t border-line pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">Text extraction and evidence</h3>
        <button type="button" className={buttonStyles.secondary} onClick={() => process(r !== null)} disabled={processing}
          aria-label={`${r ? "Reprocess" : "Process"} ${doc.original_filename}`}>
          {processing ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden="true" className="h-4 w-4" />}
          {processing ? "Processing…" : r ? "Reprocess" : "Process document"}
        </button>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      {!r ? (
        <p className="text-sm text-ink-muted">This document has not been processed yet.</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Pill className={PROCESSING_STATUS_STYLES[r.status]}>{PROCESSING_STATUS_LABELS[r.status]}</Pill>
            <span className="text-ink-muted">
              {r.pages_processed} of {r.page_count} page(s) · OCR {r.ocr_available ? "available" : "not available"}
              {r.reused_from_cache && " · cached result for identical content"} · {formatDateTime(r.finished_at)}
            </span>
          </div>
          {!r.is_current && <Alert tone="info">This result was produced by an older pipeline version; reprocess to refresh it.</Alert>}
          {r.failure_reason && <Alert tone="error">{r.failure_reason}</Alert>}
          {r.warnings.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5 text-xs text-warning-800" aria-label="Processing warnings">
              {r.warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}
          <div className="rounded-control border border-line bg-surface p-3 text-sm">
            <h4 className="font-semibold text-ink">Detected type</h4>
            <p className="mt-1">
              {r.classification.predicted_category
                ? <>Predicted <strong>{DOCUMENT_CATEGORY_LABELS[r.classification.predicted_category]}</strong></>
                : <strong>Uncertain</strong>}{" "}
              ({r.classification.confidence} confidence, signal share {Math.round(r.classification.score * 100)}%) ·
              selected at upload: {DOCUMENT_CATEGORY_LABELS[r.classification.selected_category]}
            </p>
            {r.classification.agrees_with_selected === false && (
              <p className="mt-1 text-warning-800">The predicted type differs from the selected category. The selected category was kept; please review.</p>
            )}
            {r.classification.signals.length > 0 && (
              <p className="mt-1 text-xs text-ink-subtle">Signals: {r.classification.signals.map((s) => s.signal).join("; ")}</p>
            )}
            <p className="mt-1 text-xs text-ink-subtle">Confidence is a keyword-signal heuristic, not a probability.</p>
          </div>
          <FieldsTable fields={r.fields} />
          <p className="text-xs text-ink-subtle">
            Extracted values are quoted from the document text. Extraction does not establish authenticity or compliance.
          </p>
          <PageTexts documentId={doc.id} />
        </>
      )}
      <SimulatedIssuerChecks documentId={doc.id} enabled={!!r && r.status !== "failed" && r.is_current} />
    </section>
  );
}

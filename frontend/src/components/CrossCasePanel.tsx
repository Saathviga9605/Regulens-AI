import { Link } from "react-router";
import { useState } from "react";

import { PAIR_REVIEW_LABELS, REUSE_OUTCOME_LABELS, REUSE_OUTCOME_TONES, formatDateTime } from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { ApiError, apiClient } from "../services/apiClient";
import type { AiCapabilities, CaseAlert } from "../types/api";
import { useToast } from "./Toast";
import { Alert, Badge, Card, EmptyState, ErrorState, LoadingState, buttonStyles } from "./ui";

/** Cross-case reuse for one application. Ordinary reviewers see restricted alerts only — the API never sends
 * linked-case details to them, so nothing is hidden client-side. */
export function CrossCasePanel({ applicationCode, onScanned }: { applicationCode: string; onScanned?: () => void }) {
  const alerts = useApiQuery(() => apiClient.crossCaseAlerts(applicationCode), applicationCode);
  const info = useApiQuery(() => apiClient.getSystemInfo(), "system-info");
  const caps = info.data?.ai_capabilities;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  async function scan() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const run = await apiClient.startCrossCaseScan(applicationCode);
      toast(`Cross-case scan completed: ${run.comparisons} comparisons, ${run.candidates} candidate pair(s).`);
      alerts.reload();
      onScanned?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The scan failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const data = alerts.data;
  const latest = data?.latest_scan;
  return (
    <Card title="Cross-case document reuse"
      description="Compares this case's documents with documents in other cases (exact hash, text, page images, geometry, critical fields)."
      actions={<button type="button" className={buttonStyles.secondary} onClick={scan} disabled={busy}>
        {busy ? "Scanning…" : latest ? "Re-run cross-case scan" : "Run cross-case scan"}</button>}>
      <div className="space-y-3">
        <Alert tone="info">A possible match is a prompt for human review. Document reuse is not automatically misconduct,
          and a similarity score is not proof of forgery or fraud.</Alert>
        {caps && <Capabilities caps={caps} />}
        {error && <Alert tone="error">{error}</Alert>}
        {alerts.loading && !data ? <LoadingState label="Loading cross-case alerts…" /> : alerts.error ? (
          <ErrorState message={alerts.error} onRetry={alerts.reload} />
        ) : data && (
          <>
            {latest ? (
              <p className="text-sm text-ink-muted" data-testid="latest-scan">
                Last scan {formatDateTime(latest.finished_at ?? latest.started_at)} by {latest.triggered_by}:{" "}
                {latest.status === "failed" ? <strong className="text-danger-700">failed</strong> : <>
                  {latest.documents_scanned} document(s) compared in {latest.comparisons} comparison(s);{" "}
                  {latest.candidates} candidate pair(s) examined.</>}
                <span className="ml-1 text-xs text-ink-subtle">Configuration {latest.config_version}.</span>
              </p>
            ) : <p className="text-sm text-ink-muted">No scan has been run for this case yet.</p>}
            {data.items.length === 0 ? (
              <EmptyState>No possible cross-case matches are recorded for this case.</EmptyState>
            ) : (
              <ul className="space-y-2" aria-label="Cross-case alerts">
                {data.items.map((item) => <AlertItem key={item.pair_id} item={item} />)}
              </ul>
            )}
            {!data.can_view_details && data.items.length > 0 && (
              <p className="text-xs text-ink-subtle" role="note">
                Linked-case details (the other application, its documents and the match evidence) are restricted to
                reviewers with the cross-case reviewer permission. Ask an administrator if you need access.
              </p>
            )}
          </>
        )}
      </div>
    </Card>
  );
}

const STAGES: [string, string, (c: AiCapabilities) => boolean | null][] = [
  ["Text layer & OCR", "Reads page text; scanned pages need OCR", (c) => c.ocr.available],
  ["L0 exact hash", "SHA-256 identity", () => true],
  ["L1 text similarity", "Whitespace-insensitive shingles", () => true],
  ["L2 page images", "Perceptual hash with rotation and photo rectification", (c) => c.computer_vision.available],
  ["L3 geometry", "ORB + RANSAC alignment, difference regions", (c) => c.computer_vision.available],
  ["Fields", "Grounded critical-field comparison", () => true],
  ["L4 fusion", "Rule-based evidence fusion and explanation", () => true],
];

function Capabilities({ caps }: { caps: AiCapabilities }) {
  return (
    <div className="rounded-control border border-line bg-surface-muted p-3 text-sm" data-testid="analysis-capabilities">
      <p className="font-medium text-ink">Analysis components on this server</p>
      <ul className="mt-1 space-y-0.5 text-ink-muted">
        <li>OCR: {caps.ocr.available
          ? <>{caps.ocr.engine} ({caps.ocr.version}) — local</>
          : <span className="font-medium text-warning-800">not available — scanned or photographed pages have no text, so text and field evidence will be missing for them</span>}</li>
        <li>Computer vision: {caps.computer_vision.available ? `OpenCV ${caps.computer_vision.version}` : "not available"}</li>
        <li>Local language or vision model: {caps.local_text_model.configured || caps.local_vision_model.configured
          ? "configured" : "none configured (explanations are generated deterministically from the evidence)"}</li>
      </ul>
      <ol className="mt-2 flex flex-wrap gap-1" aria-label="Scan stages">
        {STAGES.map(([name, desc, ok]) => {
          const state = ok(caps);
          return (
            <li key={name} title={desc}>
              <Badge tone={state ? "success" : "warning"}>{name}{state ? "" : " — unavailable"}</Badge>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function AlertItem({ item }: { item: CaseAlert }) {
  return (
    <li className="rounded-control border border-line bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={REUSE_OUTCOME_TONES[item.outcome]}>{REUSE_OUTCOME_LABELS[item.outcome]}</Badge>
        <span className="font-medium text-ink [overflow-wrap:anywhere]">{item.local_document.filename ?? "Document"}</span>
        <span className="text-xs text-ink-subtle">· {PAIR_REVIEW_LABELS[item.review_status]} · detected {formatDateTime(item.detected_at)}</span>
      </div>
      {item.restricted || !item.linked ? (
        <p className="mt-1 text-ink-muted">May share content with a document in another case. Linked-case details are restricted.</p>
      ) : (
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          <p className="text-ink-muted [overflow-wrap:anywhere]">
            Linked: <span className="font-mono">{item.linked.application_code}</span> · {item.linked.institution_name} ·{" "}
            {item.linked.filename}
          </p>
          <Link to={`/case-pairs/${item.pair_id}`} className={`${buttonStyles.link} text-sm`}>Open comparison</Link>
        </div>
      )}
    </li>
  );
}

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";

import {
  PAIR_ACTION_LABELS,
  PAIR_REVIEW_LABELS,
  REUSE_OUTCOME_LABELS,
  REUSE_OUTCOME_TONES,
  formatDateTime,
} from "../app/labels";
import { useToast } from "../components/Toast";
import {
  Alert,
  Badge,
  Card,
  Dialog,
  ErrorState,
  EvidenceQuote,
  LoadingState,
  PageHeader,
  TABLE,
  TextArea,
  buttonStyles,
} from "../components/ui";
import { ApiError, apiClient } from "../services/apiClient";
import type {
  DifferenceRegion,
  FieldComparison,
  FusionRecord,
  FusionSignal,
  MatchEvidence,
  PairActionType,
  PairDetail,
  PairSide,
  TextProvenance,
} from "../types/api";

const MIN_REASON = 10;
const FIELD_TONES = { agree: "success", conflict: "danger", inconclusive: "neutral" } as const;

export function CasePairPage() {
  const { pairId = "" } = useParams();
  const [pair, setPair] = useState<PairDetail | null>(null);
  const [error, setError] = useState<{ status?: number; message: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    apiClient.getCasePair(pairId)
      .then(setPair)
      .catch((err: unknown) => setError(err instanceof ApiError ? { status: err.status, message: err.message }
        : { message: "Could not load the case pair." }))
      .finally(() => setLoading(false));
  }, [pairId]);
  useEffect(load, [load]);

  const crumbs = [{ label: "Overview", to: "/" }, { label: "Cross-case reuse", to: "/cross-case" }, { label: "Comparison" }];
  if (loading && !pair) return <LoadingState label="Loading comparison…" />;
  if (error?.status === 403) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Cross-case comparison" title="Restricted" breadcrumbs={crumbs} />
        <Alert tone="warning" title="Cross-case reviewer permission required">
          Linked-case identities, documents and match evidence are available only to reviewers with the cross-case
          reviewer permission. The attempt was recorded in the audit trail. Ask an administrator if you need access.
        </Alert>
      </div>
    );
  }
  if (error || !pair) return <ErrorState message={error?.message ?? "Not found."} onRetry={load} />;

  const ev = pair.evidence;
  const geo = ev.geometric;
  const matched = ev.matched_pages[0];
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Cross-case comparison" breadcrumbs={crumbs} title="Document pair"
        description={<span className="flex flex-wrap items-center gap-2">
          <Badge tone={REUSE_OUTCOME_TONES[pair.outcome]}>{REUSE_OUTCOME_LABELS[pair.outcome]}</Badge>
          <span>{pair.outcome_meaning}</span></span>} />

      <Alert tone="warning" title="Not a misconduct finding">{pair.notice} Outcomes are produced by a deterministic
        matching pipeline ({pair.pipeline_version}, thresholds {pair.config_version}).</Alert>

      <ExplanationCard evidence={ev} />

      <div className="grid gap-5 lg:grid-cols-2">
        <SideCard label="Case A" side={pair.a} pairId={pair.id} which="a" initialPage={matched?.page_a ?? 1}
          regions={geo?.status === "verified" ? geo.differences?.regions ?? [] : []}
          fieldBoxes={fieldBoxes(ev.fields.comparisons, "a", matched?.page_a ?? 1)} provenance={ev.text.provenance?.a} />
        <SideCard label="Case B" side={pair.b} pairId={pair.id} which="b" initialPage={matched?.page_b ?? 1} regions={[]}
          fieldBoxes={fieldBoxes(ev.fields.comparisons, "b", matched?.page_b ?? 1)} provenance={ev.text.provenance?.b} />
      </div>

      <Card title="Matching evidence" description="Raw metrics from each stage, with method and version.">
        <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Matching metrics">
          <Metric term="L0 · Exact file (SHA-256)" value={ev.exact.equal ? "Identical bytes" : "Different bytes"}
            detail={ev.exact.note} />
          <Metric term={`L1 · Text (${ev.text.normalization})`}
            value={ev.text.status === "computed" ? `Jaccard ${ev.text.jaccard} · containment ${ev.text.containment}` : "Unavailable"}
            detail={ev.text.status === "computed" ? (ev.text.low_quality ? ev.text.quality_note : ev.text.method) : ev.text.reason} />
          <Metric term={`L2 · Visual (${ev.visual.method})`}
            value={ev.visual.status === "computed" ? `pHash distance ${ev.visual.distance}/64` : "Unavailable"}
            detail={ev.visual.status === "computed"
              ? `Pages ${ev.visual.page_a} ↔ ${ev.visual.page_b}${ev.visual.rotation_b_degrees ? `, B rotated ${ev.visual.rotation_b_degrees}°` : ""}. Candidate retrieval only.`
              : ev.visual.reason} />
          <Metric term={`L3 · Geometry (${geo?.method ?? "not run"})`}
            value={!geo ? "Not needed (identical bytes)" : geo.status.replace("_", " ")}
            detail={geo && geo.inliers !== undefined && geo.status !== "unavailable"
              ? `${geo.detector ?? "ORB"} · ${geo.inliers} inliers / ${geo.tentative_matches ?? 0} matches · ratio ${geo.inlier_ratio ?? 0} · coverage ${geo.coverage ?? 0}`
                + (geo.differences ? ` · ${geo.differences.cells_different} localized difference region(s)` : "")
              : geo?.reason} />
        </dl>
      </Card>

      <Card title="Critical-field comparison"
        description="Only values extracted with a quote grounded in the page text are compared. Missing or unreadable values are inconclusive, never conflicts.">
        {ev.fields.comparisons.length === 0 ? <p className="text-sm text-ink-muted">No comparable critical fields.</p> : (
          <div className={TABLE.wrap}>
            <table className={`${TABLE.table} min-w-[52rem]`}>
              <caption className="sr-only">Critical-field comparison</caption>
              <thead><tr>
                <th scope="col" className={TABLE.th}>Field</th>
                <th scope="col" className={TABLE.th}>Case A</th>
                <th scope="col" className={TABLE.th}>Case B</th>
                <th scope="col" className={TABLE.th}>Outcome</th>
              </tr></thead>
              <tbody className="divide-y divide-line">
                {ev.fields.comparisons.map((c) => <FieldRow key={c.field} c={c} />)}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Why this pair was surfaced">
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink" aria-label="Reasons">
            {ev.reasons.map((r) => <li key={r}>{r}</li>)}
          </ul>
          <p className="mt-2 text-xs text-ink-subtle">Retrieved by: {pair.candidate_methods.join(", ") || "—"}.</p>
        </Card>
        <Card title="Uncertainty and limitations">
          {ev.uncertainties.length > 0 && (
            <ul className="mb-2 list-disc space-y-1 pl-5 text-sm text-warning-800" aria-label="Uncertainties">
              {ev.uncertainties.map((u) => <li key={u}>{u}</li>)}
            </ul>
          )}
          <ul className="list-disc space-y-1 pl-5 text-xs text-ink-muted" aria-label="Limitations">
            {pair.limitations.map((l) => <li key={l}>{l}</li>)}
          </ul>
          <p className="mt-2 text-xs text-ink-subtle">Stages: {Object.entries(ev.stage_status).map(([k, v]) => `${k} ${v}`).join(" · ")}</p>
        </Card>
      </div>

      {ev.fusion && <FusionCard fusion={ev.fusion} />}

      <ReviewCard pair={pair} onChange={setPair} />
    </div>
  );
}

const KIND_TONES = { supports: "success", contradicts: "danger", unavailable: "warning", neutral: "neutral" } as const;
const KIND_LABELS = { supports: "Supports", contradicts: "Contradicts", unavailable: "Not available", neutral: "Context" };

function fieldBoxes(comparisons: FieldComparison[], side: "a" | "b", page: number) {
  return comparisons.flatMap((c) => {
    const v = c[side];
    return v?.evidence_box && v.page_number === page
      ? [{ field: c.field, box: v.evidence_box, outcome: c.outcome }] : [];
  });
}

function ExplanationCard({ evidence }: { evidence: MatchEvidence }) {
  const ex = evidence.explanation;
  if (!ex) {
    return (
      <Alert tone="info" title="No explanation for this evaluation">
        This pair was evaluated before evidence fusion and explanations were introduced. The metrics below remain the
        record; re-run the cross-case scan to produce an evaluation with an explanation.
      </Alert>
    );
  }
  return (
    <Card title="Explanation" description={`Generated ${ex.generator === "deterministic" ? "deterministically" : `by ${ex.generator}`} from this pair's stored evidence (${ex.version}). The evidence record remains authoritative.`}>
      <ul className="space-y-2" aria-label="Explanation statements">
        {ex.statements.map((st, i) => (
          <li key={i} className="text-sm text-ink">
            <Badge tone={KIND_TONES[st.kind]}>{KIND_LABELS[st.kind]}</Badge>{" "}
            <span className="[overflow-wrap:anywhere]">{st.text}</span>
            <details className="mt-0.5 text-xs text-ink-subtle">
              <summary className="cursor-pointer">Evidence reference</summary>
              <ul className="font-mono">{Object.entries(st.refs).map(([k, v]) => <li key={k}>{k} = {String(v)}</li>)}</ul>
            </details>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-sm"><span className="font-medium text-ink">Outcome rule:</span> {ex.rule}</p>
      <p className="mt-1 text-xs text-ink-subtle">{ex.disclaimer}</p>
    </Card>
  );
}

function SignalList({ title, items, tone }: { title: string; items: FusionSignal[]; tone: "success" | "danger" | "warning" | "neutral" }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">{title} ({items.length})</h3>
      {items.length === 0 ? <p className="text-sm text-ink-subtle">None</p> : (
        <ul className="mt-1 space-y-1 text-sm" aria-label={title}>
          {items.map((it, i) => (
            <li key={i} className="[overflow-wrap:anywhere]"><Badge tone={tone}>{it.signal.replace("field:", "field: ").replace(/_/g, " ")}</Badge>{" "}
              <span className="text-ink-muted">{it.detail}</span></li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FusionCard({ fusion }: { fusion: FusionRecord }) {
  return (
    <Card title="Evidence fusion" description={`${fusion.version}: how each signal bears on the outcome. Rule-based; nothing is trained on the small labelled set.`}>
      <div className="grid gap-4 md:grid-cols-3">
        <SignalList title="Supporting" items={fusion.supporting} tone="success" />
        <SignalList title="Contradicting" items={fusion.contradicting} tone="danger" />
        <SignalList title="Unavailable" items={fusion.unavailable} tone="warning" />
      </div>
      <p className="mt-3 text-xs text-ink-subtle">
        Difference regions: {fusion.regions.regions_total} total, {fusion.regions.regions_on_critical_fields} on critical-field
        evidence, {fusion.regions.regions_elsewhere} elsewhere. Text sources — A: {describeProvenance(fusion.quality.a)}; B:{" "}
        {describeProvenance(fusion.quality.b)}.
      </p>
    </Card>
  );
}

function describeProvenance(p?: TextProvenance) {
  if (!p) return "unknown";
  const parts = [];
  if (p.text_layer_pages) parts.push(`${p.text_layer_pages} text-layer page(s)`);
  if (p.ocr_pages) parts.push(`${p.ocr_pages} OCR page(s)${p.ocr_mean_confidence != null ? ` (score ${p.ocr_mean_confidence.toFixed(2)})` : ""}`);
  if (p.unreadable_pages) parts.push(`${p.unreadable_pages} unreadable page(s)`);
  return parts.join(", ") || "no readable text";
}

function Metric({ term, value, detail }: { term: string; value: string; detail?: string }) {
  return (
    <div className="rounded-control border border-line bg-surface-muted p-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-subtle">{term}</dt>
      <dd className="mt-1 text-sm font-semibold text-ink">{value}</dd>
      {detail && <dd className="mt-1 text-xs text-ink-muted [overflow-wrap:anywhere]">{detail}</dd>}
    </div>
  );
}

function FieldRow({ c }: { c: FieldComparison }) {
  const cell = (v: FieldComparison["a"]) => !v ? <span className="text-ink-subtle">—</span> : v.raw_value === null ? (
    <span className="text-ink-subtle">{v.status.replace("_", " ")}</span>
  ) : (
    <div className="space-y-1">
      <div className="font-medium text-ink [overflow-wrap:anywhere]">{v.raw_value}</div>
      {v.evidence_quote && <EvidenceQuote quote={v.evidence_quote} source={`Page ${v.page_number ?? "?"} · ${v.status} · ${
        v.evidence_source === "ocr" ? `OCR${v.ocr_confidence != null ? ` score ${v.ocr_confidence.toFixed(2)}` : ""}` : "text layer"}${
        v.evidence_box ? "" : " · no coordinates"}`} />}
    </div>
  );
  return (
    <tr>
      <th scope="row" className={`${TABLE.td} font-medium`}>{c.field.replace(/_/g, " ")}</th>
      <td className={TABLE.td}>{cell(c.a)}</td>
      <td className={TABLE.td}>{cell(c.b)}</td>
      <td className={TABLE.td}>
        <Badge tone={FIELD_TONES[c.outcome]}>{c.outcome}</Badge>
        {c.visual_difference && <span className="ml-1"><Badge tone="danger">pixels differ here</Badge></span>}
        <p className="mt-1 text-xs text-ink-muted">{c.explanation}</p>
      </td>
    </tr>
  );
}

function SideCard({ label, side, pairId, which, initialPage, regions, fieldBoxes: boxes, provenance }: {
  label: string; side: PairSide; pairId: string; which: "a" | "b"; initialPage: number; regions: DifferenceRegion[];
  fieldBoxes: { field: string; box: [number, number, number, number]; outcome: string }[]; provenance?: TextProvenance;
}) {
  const [page, setPage] = useState(initialPage);
  const [url, setUrl] = useState<string | null>(null);
  const [imgError, setImgError] = useState<string | null>(null);
  const pages = side.page_count ?? 1;

  useEffect(() => {
    if (!side.document_available) return;
    let revoked: string | null = null;
    let cancelled = false;
    setImgError(null);
    apiClient.casePairPageImage(pairId, which, page)
      .then((blob) => {
        if (cancelled) return;
        revoked = URL.createObjectURL(blob);
        setUrl(revoked);
      })
      .catch((err: unknown) => !cancelled && setImgError(err instanceof ApiError ? err.message : "Image unavailable."));
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [pairId, which, page, side.document_available]);

  return (
    <Card title={label}>
      <dl className="mb-3 grid gap-1 text-sm">
        <div className="flex flex-wrap gap-1"><dt className="text-ink-subtle">Application:</dt><dd>
          {side.application_code ? <Link className={buttonStyles.link} to={`/applications/${side.application_code}`}>
            <span className="font-mono">{side.application_code}</span></Link> : "—"}</dd></div>
        <div className="flex flex-wrap gap-1"><dt className="text-ink-subtle">Institution:</dt><dd className="[overflow-wrap:anywhere]">{side.institution_name ?? "—"}</dd></div>
        <div className="flex flex-wrap gap-1"><dt className="text-ink-subtle">File:</dt><dd className="[overflow-wrap:anywhere]">{side.filename ?? "—"} ({side.category?.replace(/_/g, " ")})</dd></div>
        <div className="flex flex-wrap gap-1"><dt className="text-ink-subtle">SHA-256:</dt><dd className="font-mono text-xs [overflow-wrap:anywhere]">{side.sha256}</dd></div>
        <div className="flex flex-wrap gap-1"><dt className="text-ink-subtle">Text source:</dt><dd>{describeProvenance(provenance)}</dd></div>
      </dl>
      {!side.document_available ? (
        <p className="rounded-control border border-dashed border-line-strong p-4 text-sm text-ink-muted">
          This document is no longer stored. The recorded evidence above and below remains.
        </p>
      ) : (
        <figure>
          <div className="relative overflow-hidden rounded-control border border-line bg-surface-muted">
            {imgError ? <p className="p-4 text-sm text-danger-700">{imgError}</p> : url ? (
              <>
                <img src={url} alt={`${label}, page ${page}`} className="block h-auto w-full" />
                {page === initialPage && boxes.map((b) => (
                  <span key={b.field} aria-hidden="true" title={b.field.replace(/_/g, " ")}
                    className={`absolute border-2 ${b.outcome === "conflict" ? "border-saffron-500" : "border-teal-700"}`}
                    style={{ left: `${b.box[0] * 100}%`, top: `${b.box[1] * 100}%`, width: `${(b.box[2] - b.box[0]) * 100}%`,
                      height: `${(b.box[3] - b.box[1]) * 100}%` }} />
                ))}
                {page === initialPage && regions.map((r, i) => (
                  <span key={i} aria-hidden="true" className="absolute border-2 border-danger-700 bg-danger-bg/30"
                    style={{ left: `${r.box[0] * 100}%`, top: `${r.box[1] * 100}%`, width: `${(r.box[2] - r.box[0]) * 100}%`,
                      height: `${(r.box[3] - r.box[1]) * 100}%` }} />
                ))}
              </>
            ) : <LoadingState label="Rendering page…" />}
          </div>
          <figcaption className="mt-2 flex items-center justify-between gap-2 text-xs text-ink-muted">
            <span>Page {page} of {pages}{regions.length > 0 && ` · ${regions.length} localized difference region(s) outlined in red`}
              {boxes.length > 0 && ` · ${boxes.length} field evidence box(es) (teal agree/other, saffron conflict)`}</span>
            <span className="flex gap-1">
              <button type="button" className={buttonStyles.ghost} aria-label={`${label}: previous page`} disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}><ChevronLeft aria-hidden="true" className="h-4 w-4" /></button>
              <button type="button" className={buttonStyles.ghost} aria-label={`${label}: next page`} disabled={page >= pages}
                onClick={() => setPage((p) => p + 1)}><ChevronRight aria-hidden="true" className="h-4 w-4" /></button>
            </span>
          </figcaption>
        </figure>
      )}
    </Card>
  );
}

function ReviewCard({ pair, onChange }: { pair: PairDetail; onChange: (p: PairDetail) => void }) {
  const [action, setAction] = useState<PairActionType | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const needsReason = action !== null && action !== "note";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!action || busy) return;
    if (needsReason && note.trim().length < MIN_REASON) {
      setError(`A reason of at least ${MIN_REASON} characters is required.`);
      return;
    }
    if (action === "note" && !note.trim()) {
      setError("Enter the observation.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await apiClient.addPairAction(pair.id, action, note.trim(), pair.review_version);
      onChange(updated);
      toast(`${PAIR_ACTION_LABELS[action]} recorded.`);
      setAction(null);
      setNote("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The action failed."); // input is kept for retry
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Reviewer disposition" description="Stored separately from the system evidence, with your name, reason and time.">
      <p className="mb-3 text-sm">Current state: <Badge tone="brand">{PAIR_REVIEW_LABELS[pair.review_status]}</Badge></p>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Pair review actions">
        {(["confirm_candidate", "dismiss", "escalate", "note"] as PairActionType[]).map((a) => (
          <button key={a} type="button" className={a === "dismiss" ? buttonStyles.secondary : buttonStyles.primary}
            onClick={() => { setAction(a); setError(null); }}>{PAIR_ACTION_LABELS[a]}</button>
        ))}
      </div>
      <Dialog open={action !== null} title={action ? PAIR_ACTION_LABELS[action] ?? action : ""} onClose={() => !busy && setAction(null)}>
        <form noValidate onSubmit={submit} aria-label="Pair review form" className="space-y-3">
          {action === "confirm_candidate" && <p className="text-sm text-ink-muted">Confirms the pair needs further review.
            It is not a finding of forgery, fraud or misconduct.</p>}
          <TextArea label={needsReason ? "Reason (required)" : "Observation"} value={note} maxLength={2000}
            hint={needsReason ? `At least ${MIN_REASON} characters. Say what you checked.` : undefined}
            error={error ?? undefined} onChange={(e) => setNote(e.target.value)} />
          <div className="flex justify-end gap-2">
            <button type="button" className={buttonStyles.secondary} disabled={busy} onClick={() => setAction(null)}>Cancel</button>
            <button type="submit" className={buttonStyles.primary} disabled={busy}>
              {busy ? "Saving…" : `Save: ${action ? PAIR_ACTION_LABELS[action] : ""}`}</button>
          </div>
        </form>
      </Dialog>
      <h3 className="mt-4 text-sm font-semibold text-ink">History</h3>
      {pair.actions.length === 0 ? <p className="text-sm text-ink-subtle">No reviewer actions yet.</p> : (
        <ol className="mt-1 space-y-1 text-sm" aria-label="Pair review history">
          {pair.actions.map((h) => (
            <li key={h.id} className="rounded-control border border-line bg-surface px-2 py-1 [overflow-wrap:anywhere]">
              <span className="font-medium">{PAIR_ACTION_LABELS[h.action_type]}</span> by {h.actor_username} ·{" "}
              {PAIR_REVIEW_LABELS[h.previous_status]} → {PAIR_REVIEW_LABELS[h.new_status]} ·{" "}
              <span className="text-xs text-ink-subtle">{formatDateTime(h.created_at)}</span>
              {h.note && <p className="text-ink">“{h.note}”</p>}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

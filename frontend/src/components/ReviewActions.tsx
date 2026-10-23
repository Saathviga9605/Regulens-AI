import { useState, type FormEvent } from "react";

import { REASON_REQUIRED, REVIEW_ACTION_LABELS, REVIEW_STATUS_LABELS, REVIEW_STATUS_STYLES, formatDateTime } from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { ApiError, apiClient } from "../services/apiClient";
import type { FindingDetail, ReviewActionType } from "../types/api";
import { Alert, Pill, TextArea, TextField, buttonStyles } from "./ui";

const MIN_REASON = 10;

/** Human review of one finding: current state, permitted actions (from the server) and the append-only history. */
export function ReviewActions({ applicationCode, finding, onChanged }: {
  applicationCode: string; finding: FindingDetail; onChanged: () => void;
}) {
  const history = useApiQuery(() => apiClient.listFindingActions(applicationCode, finding.id),
    `${finding.id}:${finding.review_version}`);
  const [action, setAction] = useState<ReviewActionType | null>(null);
  const [note, setNote] = useState("");
  const [requested, setRequested] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  function choose(next: ReviewActionType) {
    setAction(next);
    setErrors({});
    setMessage(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!action || busy) return;
    const found: Record<string, string> = {};
    if (REASON_REQUIRED.includes(action) && note.trim().length < MIN_REASON) found.note = `A reason of at least ${MIN_REASON} characters is required.`;
    if (action === "request_evidence" && requested.trim().length < 5) found.requested = "Describe the evidence you need.";
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      await apiClient.reviewAction(applicationCode, finding.id, {
        action, expected_version: finding.review_version, note: note.trim() || null,
        ...(action === "request_evidence" ? { requested_evidence: requested.trim(), due_date: dueDate || null } : {}),
      });
      setMessage({ tone: "success", text: `${REVIEW_ACTION_LABELS[action]} recorded.` });
      setAction(null);
      setNote("");
      setRequested("");
      setDueDate("");
      onChanged();
    } catch (err) {
      if (err instanceof ApiError && err.code === "stale_review") {
        setMessage({ tone: "error", text: "Someone else updated this finding. The latest state has been reloaded; review it and try again." });
        onChanged();
      } else {
        if (err instanceof ApiError) setErrors({ note: err.fieldErrors.note ?? "" });
        setMessage({ tone: "error", text: err instanceof ApiError ? err.message : "The action failed." });
      }
    } finally {
      setBusy(false);
    }
  }

  const options = finding.allowed_actions.filter((a) => a !== "carried_forward");
  return (
    <section aria-label="Human review" className="space-y-3 border-t border-line pt-3">
      <h5 className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">Human review (separate from the system result)</h5>
      <p className="flex flex-wrap items-center gap-2 text-sm">
        Current state: <Pill className={REVIEW_STATUS_STYLES[finding.review_status]}>{REVIEW_STATUS_LABELS[finding.review_status]}</Pill>
        {finding.reviewed_at && <span className="text-xs text-ink-subtle">{formatDateTime(finding.reviewed_at)}</span>}
      </p>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Review actions">
        {options.map((a) => (
          <button key={a} type="button" aria-pressed={action === a} onClick={() => choose(a)}
            className={action === a ? buttonStyles.primary : buttonStyles.secondary}>
            {REVIEW_ACTION_LABELS[a]}
          </button>
        ))}
      </div>
      {action && (
        <form noValidate onSubmit={submit} aria-label={`${REVIEW_ACTION_LABELS[action]} form`} className="space-y-2 rounded-control border border-line bg-surface-muted p-3">
          {action === "request_evidence" && (
            <div className="grid gap-2 sm:grid-cols-2">
              <TextField label="Evidence requested" value={requested} error={errors.requested} maxLength={2000}
                onChange={(e) => setRequested(e.target.value)} />
              <TextField label="Due date (optional)" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
            </div>
          )}
          <TextArea label={REASON_REQUIRED.includes(action) ? "Reason (required)" : "Reason or note (optional)"}
            hint={REASON_REQUIRED.includes(action) ? `At least ${MIN_REASON} characters. Explain what you checked.` : undefined}
            value={note} error={errors.note || undefined} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
          <p className="text-xs text-ink-subtle">
            {action === "confirm" ? "Confirming means you agree this needs attention — it is not a finding of fraud or non-compliance."
              : "Your action is added to the history; the system-generated finding is never changed."}
          </p>
          <div className="flex gap-2">
            <button type="submit" className={buttonStyles.primary} disabled={busy}>{busy ? "Saving…" : `Save: ${REVIEW_ACTION_LABELS[action]}`}</button>
            <button type="button" className={buttonStyles.secondary} onClick={() => setAction(null)} disabled={busy}>Cancel</button>
          </div>
        </form>
      )}
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
      <div>
        <h6 className="text-xs font-semibold text-ink">Review history</h6>
        {history.error ? <p className="text-sm text-danger-700">{history.error}</p> : (history.data ?? []).length === 0 ? (
          <p className="text-sm text-ink-subtle">No reviewer actions yet.</p>
        ) : (
          <ol className="mt-1 space-y-1 text-sm" aria-label="Review history">
            {(history.data ?? []).map((h) => (
              <li key={h.id} className="rounded-control border border-line bg-surface px-2 py-1 [overflow-wrap:anywhere]">
                <span className="font-medium">{REVIEW_ACTION_LABELS[h.action_type]}</span> by {h.actor_username} ·{" "}
                {REVIEW_STATUS_LABELS[h.previous_status]} → {REVIEW_STATUS_LABELS[h.new_status]} ·{" "}
                <span className="text-xs text-ink-subtle">{formatDateTime(h.created_at)}</span>
                {h.note && <p className="text-ink">“{h.note}”</p>}
                {h.evidence_refs.length > 0 && (
                  <p className="text-xs text-ink-subtle">References: {h.evidence_refs.map((r) => `${r.document_filename}${r.page_number ? ` p.${r.page_number}` : ""}`).join("; ")}</p>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

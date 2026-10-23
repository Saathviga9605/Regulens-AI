import { useState, type FormEvent } from "react";

import { formatDateTime } from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { ApiError, apiClient } from "../services/apiClient";
import type { EvidenceRequest } from "../types/api";
import { Alert, Card, EmptyState, ErrorState, LoadingState, Pill, SelectField, TextField, buttonStyles } from "./ui";

const STATUS_STYLE = {
  open: "bg-warning-bg text-warning-800 ring-warning-line",
  fulfilled: "bg-success-bg text-success-700 ring-success-line",
  cancelled: "bg-surface-muted text-ink-muted ring-line",
} as const;

function RequestItem({ applicationCode, request, documents, onChanged }: {
  applicationCode: string; request: EvidenceRequest; documents: { id: string; name: string }[]; onChanged: () => void;
}) {
  const [mode, setMode] = useState<"link" | "fulfil" | "cancel" | null>(null);
  const [documentId, setDocumentId] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const linked = new Set(request.documents.map((d) => d.document_id));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (mode === "link" && !documentId) return setError("Choose a document.");
    if (mode === "cancel" && note.trim().length < 10) return setError("Give a reason of at least 10 characters.");
    setBusy(true);
    try {
      if (mode === "link") await apiClient.linkEvidenceDocument(applicationCode, request.id, documentId);
      if (mode === "fulfil") await apiClient.fulfilEvidenceRequest(applicationCode, request.id, request.version, note);
      if (mode === "cancel") await apiClient.cancelEvidenceRequest(applicationCode, request.id, request.version, note);
      setMode(null);
      setNote("");
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The update failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="space-y-2 rounded-control border border-line bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Pill className={STATUS_STYLE[request.status]}>{request.status}</Pill>
        {request.is_overdue && <Pill className="bg-danger-700 text-white ring-danger-700">Overdue</Pill>}
        <strong className="text-ink">{request.requested_evidence}</strong>
      </div>
      <p className="text-ink">Reason: {request.reason}</p>
      <p className="text-xs text-ink-subtle">
        Requested by {request.created_by} · {formatDateTime(request.created_at)}{request.due_date && ` · due ${request.due_date}`}
        {request.finding_title && ` · for finding “${request.finding_title}”`}
      </p>
      <p className="text-xs text-ink-muted">
        Linked documents: {request.documents.length ? request.documents.map((d) => d.document_filename).join(", ") : "none yet"}
      </p>
      {request.closed_at && (
        <p className="text-xs text-ink-muted">{request.status === "fulfilled" ? "Fulfilled" : "Cancelled"} by {request.closed_by} ·{" "}
          {formatDateTime(request.closed_at)}{request.closing_note && ` · “${request.closing_note}”`}</p>
      )}
      {request.status === "open" && (
        <div className="flex flex-wrap gap-2">
          <button type="button" className={buttonStyles.secondary} onClick={() => setMode("link")}>Link uploaded document</button>
          <button type="button" className={buttonStyles.secondary} onClick={() => setMode("fulfil")}
            disabled={request.documents.length === 0} title={request.documents.length === 0 ? "Link at least one document first" : undefined}>
            Mark fulfilled
          </button>
          <button type="button" className={buttonStyles.secondary} onClick={() => setMode("cancel")}>Cancel request</button>
        </div>
      )}
      {request.status === "open" && request.documents.length === 0 && (
        <p className="text-xs text-ink-subtle">“Mark fulfilled” is available once a document is linked.</p>
      )}
      {mode && (
        <form noValidate onSubmit={submit} className="space-y-2 rounded border border-line bg-surface-muted p-2"
          aria-label={mode === "link" ? "Link document" : mode === "fulfil" ? "Fulfil request" : "Cancel request"}>
          {mode === "link" ? (
            <SelectField label="Document" value={documentId} placeholder="Choose a document"
              options={documents.filter((d) => !linked.has(d.id)).map((d) => [d.id, d.name])}
              onChange={(e) => setDocumentId(e.target.value)} />
          ) : (
            <TextField label={mode === "cancel" ? "Reason for cancelling (required)" : "Fulfilment note (optional)"}
              value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} />
          )}
          {error && <p role="alert" className="text-sm text-danger-700">{error}</p>}
          <div className="flex gap-2">
            <button type="submit" className={buttonStyles.primary} disabled={busy}>
              {mode === "link" ? "Link document" : mode === "fulfil" ? "Confirm fulfilled" : "Confirm cancellation"}
            </button>
            <button type="button" className={buttonStyles.secondary} onClick={() => setMode(null)}>Close</button>
          </div>
        </form>
      )}
    </li>
  );
}

export function EvidenceRequestsPanel({ applicationCode, version, onChanged }: {
  applicationCode: string; version: number; onChanged: () => void;
}) {
  const [status, setStatus] = useState("");
  const requests = useApiQuery(() => apiClient.listEvidenceRequests(applicationCode, status || undefined),
    `${applicationCode}:${status}:${version}`);
  const docs = useApiQuery(() => apiClient.listDocuments(applicationCode), `${applicationCode}:${version}`);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ requested_evidence: "", reason: "", due_date: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    const found: Record<string, string> = {};
    if (form.requested_evidence.trim().length < 5) found.requested_evidence = "Describe the evidence (at least 5 characters).";
    if (form.reason.trim().length < 10) found.reason = "Give a reason (at least 10 characters).";
    setErrors(found);
    if (Object.keys(found).length) return;
    try {
      await apiClient.createEvidenceRequest(applicationCode, { ...form, due_date: form.due_date || null });
      setCreating(false);
      setForm({ requested_evidence: "", reason: "", due_date: "" });
      setMessage(null);
      onChanged();
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors);
      setMessage(err instanceof ApiError ? err.message : "Could not create the request.");
    }
  }

  const documentOptions = (docs.data?.items ?? []).filter((d) => d.status !== "intake_failed")
    .map((d) => ({ id: d.id, name: d.original_filename }));
  return (
    <Card title="Additional evidence requests" actions={!creating && (
      <button type="button" className={buttonStyles.primary} onClick={() => setCreating(true)}>New request</button>
    )}>
      <div className="space-y-3">
        <p className="text-xs text-ink-subtle">In-app only — no email or SMS is sent. Upload documents in “Supporting documents” and link them here, or pick the request while uploading.</p>
        {creating && (
          <form noValidate onSubmit={create} aria-label="New evidence request" className="grid gap-2 rounded-control border border-line bg-surface-muted p-3 sm:grid-cols-2">
            <TextField label="Evidence requested" value={form.requested_evidence} error={errors.requested_evidence}
              onChange={(e) => setForm({ ...form, requested_evidence: e.target.value })} />
            <TextField label="Due date (optional)" type="date" value={form.due_date} error={errors.due_date}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            <div className="sm:col-span-2">
              <TextField label="Reason" value={form.reason} error={errors.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
            </div>
            {message && <div className="sm:col-span-2"><Alert tone="error">{message}</Alert></div>}
            <div className="flex gap-2 sm:col-span-2">
              <button type="submit" className={buttonStyles.primary}>Create request</button>
              <button type="button" className={buttonStyles.secondary} onClick={() => setCreating(false)}>Cancel</button>
            </div>
          </form>
        )}
        <SelectField label="Show" value={status} placeholder="All requests"
          options={[["open", "Open"], ["overdue", "Overdue"], ["fulfilled", "Fulfilled"], ["cancelled", "Cancelled"]]}
          onChange={(e) => setStatus(e.target.value)} />
        {requests.loading && !requests.data ? <LoadingState label="Loading evidence requests…" /> : requests.error ? (
          <ErrorState message={requests.error} onRetry={requests.reload} />
        ) : (requests.data ?? []).length === 0 ? <EmptyState>No evidence requests{status ? ` with status “${status}”` : ""}.</EmptyState> : (
          <ul className="space-y-2" aria-label="Evidence requests">
            {(requests.data ?? []).map((r) => (
              <RequestItem key={r.id} applicationCode={applicationCode} request={r} documents={documentOptions} onChanged={onChanged} />
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

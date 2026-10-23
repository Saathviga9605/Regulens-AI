import { Cog, Download, ExternalLink, Info, Trash2, Upload } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import {
  DOCUMENT_CATEGORY_LABELS,
  DOCUMENT_STATUS_LABELS,
  DOCUMENT_STATUS_STYLES,
  PROCESSING_STATUS_LABELS,
  PROCESSING_STATUS_STYLES,
  entries,
  formatBytes,
  formatDateTime,
} from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { ApiError, apiClient } from "../services/apiClient";
import type { ApplicationDocument, DocumentCategory, IntakePolicy } from "../types/api";
import { DocumentAnalysis } from "./DocumentAnalysis";
import {
  Alert,
  Card,
  DefinitionGrid,
  EmptyState,
  ErrorState,
  LoadingState,
  Pill,
  SelectField,
  TABLE,
  TextField,
  buttonStyles,
} from "./ui";

function StatusPill({ doc }: { doc: ApplicationDocument }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${DOCUMENT_STATUS_STYLES[doc.status]}`}>
      {DOCUMENT_STATUS_LABELS[doc.status]}
    </span>
  );
}

// --- Upload form -------------------------------------------------------------------------------

function UploadForm({
  applicationCode,
  policy,
  onUploaded,
  onCancel,
}: {
  applicationCode: string;
  policy: IntakePolicy;
  onUploaded: (doc: ApplicationDocument) => void;
  onCancel: () => void;
}) {
  const fileId = useId();
  const [category, setCategory] = useState<DocumentCategory | "">("");
  const [file, setFile] = useState<File | null>(null);
  const [description, setDescription] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const limit = formatBytes(policy.max_upload_bytes);

  function validate(): Record<string, string> {
    const found: Record<string, string> = {};
    if (!category) found.category = "Select a document category.";
    if (!file) found.file = "Choose a PDF file.";
    else if (!file.name.toLowerCase().endsWith(".pdf")) found.file = "Only .pdf files are accepted.";
    else if (file.size === 0) found.file = "The selected file is empty.";
    else if (file.size > policy.max_upload_bytes) found.file = `File is ${formatBytes(file.size)}; the limit is ${limit}.`;
    return found;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0 || !file || !category) {
      setFormError("Please correct the highlighted fields.");
      return;
    }
    setUploading(true);
    try {
      const trimmed = description.trim();
      onUploaded(await apiClient.uploadDocument(applicationCode, { file, category, ...(trimmed ? { description: trimmed } : {}) }));
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setFormError(err.message);
      } else {
        setFormError("Upload failed unexpectedly. Please try again.");
      }
    } finally {
      setUploading(false);
    }
  }

  return (
    <form noValidate onSubmit={handleSubmit} aria-label="Upload document" aria-busy={uploading}
      className="space-y-4 rounded-md border border-slate-200 bg-slate-50 p-4">
      {formError && <Alert tone="error">{formError}</Alert>}
      <div className="grid gap-4 md:grid-cols-2">
        <SelectField
          label="Document category"
          value={category}
          onChange={(e) => setCategory(e.target.value as DocumentCategory | "")}
          options={entries(DOCUMENT_CATEGORY_LABELS)}
          placeholder="Select a category"
          error={errors.category}
          hint="Categories are for organisation only; not every category is required for every application."
        />
        <div>
          <label htmlFor={fileId} className="block text-sm font-medium text-slate-700">
            PDF file
          </label>
          <input
            id={fileId}
            type="file"
            accept={[...policy.accepted_content_types, ...policy.accepted_extensions].join(",")}
            aria-invalid={errors.file ? true : undefined}
            aria-describedby={`${fileId}-help`}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white text-sm text-slate-700 file:mr-3 file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
          />
          <p id={`${fileId}-help`} className={`mt-1 text-xs ${errors.file ? "text-red-700" : "text-slate-500"}`}>
            {errors.file ?? `PDF only, up to ${limit}. The file is checked on the server.`}
          </p>
        </div>
        <div className="md:col-span-2">
          <TextField label="Description (optional)" value={description} maxLength={500}
            onChange={(e) => setDescription(e.target.value)} error={errors.description} />
        </div>
      </div>
      <div className="flex gap-2">
        <button type="submit" className={buttonStyles.primary} disabled={uploading}>
          <Upload aria-hidden="true" className="h-4 w-4" /> {uploading ? "Uploading…" : "Upload"}
        </button>
        <button type="button" className={buttonStyles.secondary} onClick={onCancel} disabled={uploading}>
          Cancel
        </button>
      </div>
    </form>
  );
}

// --- Detail view -------------------------------------------------------------------------------

function DocumentDetails({ doc }: { doc: ApplicationDocument }) {
  return (
    <div className="space-y-3">
      <DefinitionGrid
        items={[
          ["File name", doc.original_filename],
          ["Category", DOCUMENT_CATEGORY_LABELS[doc.category]],
          ["Intake status", <StatusPill doc={doc} />],
          ["Size", `${formatBytes(doc.size_bytes)} (${doc.size_bytes.toLocaleString("en-IN")} bytes)`],
          ["Detected type", doc.mime_type],
          ["Uploaded", formatDateTime(doc.uploaded_at)],
          ["Description", doc.description ?? "—"],
          ["Stored content", doc.content_available ? "Available" : "Not available"],
          ["SHA-256", <span className="font-mono text-xs break-all">{doc.sha256}</span>],
          [
            "Identical content",
            doc.duplicate_of
              ? `Same content as “${doc.duplicate_of.original_filename}” (uploaded ${formatDateTime(doc.duplicate_of.uploaded_at)}) in this application`
              : doc.other_application_match_count > 0
                ? `Identical content exists in ${doc.other_application_match_count} other application(s); details are not shown`
                : "No identical content found",
          ],
        ]}
      />
      <p className="text-xs text-slate-500">
        The SHA-256 checksum identifies the exact file content for comparison. It does not establish that the document
        is authentic or that its issuer is legitimate.
      </p>
    </div>
  );
}

// --- Panel -------------------------------------------------------------------------------------

interface PanelProps {
  applicationCode: string;
  intakeOpen: boolean;
  /** Changing this value reloads the inventory (e.g. after a scrutiny run processed documents). */
  refreshKey?: number;
}

export function DocumentsPanel({ applicationCode, intakeOpen, refreshKey = 0 }: PanelProps) {
  const docs = useApiQuery(() => apiClient.listDocuments(applicationCode), `${applicationCode}:${refreshKey}`);
  const policy = useApiQuery(() => apiClient.getIntakePolicy(), "policy");
  const [uploading, setUploading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<ApplicationDocument | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [flash, setFlash] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [batch, setBatch] = useState<string | null>(null);

  async function processAll() {
    const pending = (docs.data?.items ?? []).filter((d) => d.status !== "intake_failed" && !d.processing?.is_current);
    setFlash(null);
    let failed = 0;
    for (const [i, d] of pending.entries()) {
      setBatch(`Processing ${i + 1} of ${pending.length}: ${d.original_filename}…`);
      try {
        const result = await apiClient.processDocument(d.id);
        if (result.status === "failed") failed += 1;
      } catch {
        failed += 1;
      }
    }
    setBatch(null);
    setFlash(pending.length === 0
      ? { tone: "success", text: "All documents already have current processing results." }
      : { tone: failed ? "error" : "success",
          text: `Processed ${pending.length} document(s)${failed ? `; ${failed} could not be read — see each document's details` : ""}.` });
    docs.reload();
  }

  function onUploaded(doc: ApplicationDocument) {
    setUploading(false);
    setFlash({
      tone: "success",
      text:
        doc.status === "duplicate_detected" && doc.duplicate_of
          ? `Uploaded “${doc.original_filename}”. Its content is identical to “${doc.duplicate_of.original_filename}”, so it is marked as a duplicate. The original was not changed.`
          : `Uploaded “${doc.original_filename}”.`,
    });
    docs.reload();
  }

  async function confirmDelete() {
    if (!confirming) return;
    setDeleting(true);
    try {
      await apiClient.deleteDocument(confirming.id);
      setFlash({ tone: "success", text: `Deleted “${confirming.original_filename}”.` });
      setConfirming(null);
      setExpanded(null);
      docs.reload();
    } catch (err) {
      setFlash({ tone: "error", text: err instanceof ApiError ? err.message : "Delete failed. Please try again." });
      setConfirming(null);
    } finally {
      setDeleting(false);
    }
  }

  const items = docs.data?.items ?? [];

  return (
    <Card
      title="Supporting documents"
      actions={
        <div className="flex flex-wrap gap-2">
          {items.length > 0 && (
            <button type="button" className={buttonStyles.secondary} onClick={processAll} disabled={batch !== null}>
              <Cog aria-hidden="true" className="h-4 w-4" /> {batch ? "Processing…" : "Process all"}
            </button>
          )}
          {intakeOpen && !uploading && policy.data && (
            <button type="button" className={buttonStyles.primary} onClick={() => { setFlash(null); setUploading(true); }}>
              <Upload aria-hidden="true" className="h-4 w-4" /> Upload PDF
            </button>
          )}
        </div>
      }
    >
      <div className="space-y-4">
        {!intakeOpen && (
          <Alert tone="info">
            Documents can be added or removed only while the application is a draft or awaiting additional evidence.
          </Alert>
        )}
        {batch && <div role="status" className="text-sm text-slate-700">{batch}</div>}
        {flash && <Alert tone={flash.tone}>{flash.text}</Alert>}
        {policy.error && <ErrorState message={policy.error} onRetry={policy.reload} />}
        {uploading && policy.data && (
          <UploadForm applicationCode={applicationCode} policy={policy.data} onUploaded={onUploaded}
            onCancel={() => setUploading(false)} />
        )}

        {docs.loading && !docs.data ? (
          <LoadingState label="Loading documents…" />
        ) : docs.error ? (
          <ErrorState message={docs.error} onRetry={docs.reload} />
        ) : items.length === 0 ? (
          <EmptyState>No documents have been uploaded for this application.</EmptyState>
        ) : (
          <div className={TABLE.wrap}>
            <table className={TABLE.table}>
              <caption className="sr-only">Documents for {applicationCode}</caption>
              <thead>
                <tr>
                  <th scope="col" className={TABLE.th}>File</th>
                  <th scope="col" className={TABLE.th}>Category</th>
                  <th scope="col" className={TABLE.th}>Size</th>
                  <th scope="col" className={TABLE.th}>Uploaded</th>
                  <th scope="col" className={TABLE.th}>Intake status</th>
                  <th scope="col" className={TABLE.th}>Processing</th>
                  <th scope="col" className={TABLE.th}>Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((doc) => (
                  <DocumentRow
                    key={doc.id}
                    doc={doc}
                    expanded={expanded === doc.id}
                    onToggle={() => setExpanded(expanded === doc.id ? null : doc.id)}
                    canDelete={intakeOpen}
                    confirming={confirming?.id === doc.id}
                    deleting={deleting}
                    onAskDelete={() => { setFlash(null); setConfirming(doc); }}
                    onCancelDelete={() => setConfirming(null)}
                    onConfirmDelete={confirmDelete}
                    onProcessed={docs.reload}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}

interface RowProps {
  doc: ApplicationDocument;
  expanded: boolean;
  onToggle: () => void;
  canDelete: boolean;
  confirming: boolean;
  deleting: boolean;
  onAskDelete: () => void;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
  onProcessed: () => void;
}

function ProcessingCell({ doc }: { doc: ApplicationDocument }) {
  const p = doc.processing;
  if (!p) return <span className="text-xs text-slate-500">Not processed</span>;
  return (
    <>
      <Pill className={PROCESSING_STATUS_STYLES[p.status]}>{PROCESSING_STATUS_LABELS[p.status]}</Pill>
      {!p.is_current && <div className="mt-1 text-xs text-amber-800">Outdated — reprocess</div>}
      {p.status !== "failed" && (
        <div className="mt-1 text-xs text-slate-600">
          {p.predicted_category
            ? `Detected: ${DOCUMENT_CATEGORY_LABELS[p.predicted_category]}${p.predicted_category !== doc.category ? " (differs)" : ""}`
            : "Type uncertain"}
        </div>
      )}
    </>
  );
}

function DocumentRow({ doc, expanded, onToggle, canDelete, confirming, deleting, onAskDelete, onCancelDelete, onConfirmDelete, onProcessed }: RowProps) {
  const detailsId = `doc-details-${doc.id}`;
  const small = "inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600";
  return (
    <>
      <tr>
        <td className={TABLE.td}>
          <div className="font-medium text-slate-900 [overflow-wrap:anywhere]">{doc.original_filename}</div>
          {doc.description && <div className="text-xs text-slate-500">{doc.description}</div>}
        </td>
        <td className={TABLE.td}>{DOCUMENT_CATEGORY_LABELS[doc.category]}</td>
        <td className={`${TABLE.td} whitespace-nowrap tabular-nums`}>{formatBytes(doc.size_bytes)}</td>
        <td className={`${TABLE.td} whitespace-nowrap`}>{formatDateTime(doc.uploaded_at)}</td>
        <td className={TABLE.td}>
          <StatusPill doc={doc} />
          {doc.duplicate_of && (
            <div className="mt-1 text-xs text-slate-600">Same content as “{doc.duplicate_of.original_filename}”</div>
          )}
          {doc.other_application_match_count > 0 && (
            <div className="mt-1 text-xs text-slate-600">Also present in another application</div>
          )}
        </td>
        <td className={TABLE.td}>
          <ProcessingCell doc={doc} />
        </td>
        <td className={TABLE.td}>
          <div className="flex flex-wrap gap-1">
            <button type="button" className={`${small} text-slate-700 hover:bg-slate-100`} aria-expanded={expanded}
              aria-controls={detailsId} onClick={onToggle} aria-label={`Details for ${doc.original_filename}`}>
              <Info aria-hidden="true" className="h-3.5 w-3.5" /> Details
            </button>
            {doc.content_available && (
              <>
                <a href={apiClient.documentContentUrl(doc.id)} target="_blank" rel="noopener noreferrer"
                  className={`${small} text-blue-700 hover:bg-blue-50`} aria-label={`Open ${doc.original_filename}`}>
                  <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" /> Open
                </a>
                <a href={apiClient.documentContentUrl(doc.id, "attachment")} download
                  className={`${small} text-blue-700 hover:bg-blue-50`} aria-label={`Download ${doc.original_filename}`}>
                  <Download aria-hidden="true" className="h-3.5 w-3.5" /> Download
                </a>
              </>
            )}
            {canDelete && (
              <button type="button" className={`${small} text-red-700 hover:bg-red-50`} onClick={onAskDelete}
                aria-label={`Delete ${doc.original_filename}`}>
                <Trash2 aria-hidden="true" className="h-3.5 w-3.5" /> Delete
              </button>
            )}
          </div>
        </td>
      </tr>
      {confirming && (
        <tr>
          <td colSpan={7} className="bg-red-50 px-4 py-3">
            <div role="alertdialog" aria-labelledby={`${detailsId}-confirm`} className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p id={`${detailsId}-confirm`} className="text-sm text-red-900">
                Delete “{doc.original_filename}”? The stored file and its metadata are removed permanently.
                {doc.status === "uploaded" && " If identical duplicates exist, the earliest one becomes the original."}
              </p>
              <div className="flex gap-2">
                <button type="button" className={`${buttonStyles.primary} bg-red-700 hover:bg-red-800`} onClick={onConfirmDelete} disabled={deleting}>
                  {deleting ? "Deleting…" : "Confirm delete"}
                </button>
                <button type="button" className={buttonStyles.secondary} onClick={onCancelDelete} disabled={deleting}>
                  Cancel
                </button>
              </div>
            </div>
          </td>
        </tr>
      )}
      {expanded && (
        <tr>
          <td id={detailsId} colSpan={7} className="space-y-4 bg-slate-50 px-4 py-4">
            <DocumentDetails doc={doc} />
            {doc.status !== "intake_failed" && <DocumentAnalysis doc={doc} onProcessed={onProcessed} />}
          </td>
        </tr>
      )}
    </>
  );
}

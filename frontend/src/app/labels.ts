/** Display labels for backend enum values (backend/app/models/enums.py). */

import type {
  ApplicationStatus,
  ApplicationType,
  DocumentCategory,
  DocumentStatus,
  FieldStatus,
  FindingKind,
  PageStatus,
  ProcessingStatus,
  ReviewStatus,
  ReviewActionType,
  RuleOutcome,
  Severity,
  VerificationOutcome,
  InstitutionType,
  ProgrammeLevel,
  RecordStatus,
  Shift,
} from "../types/api";

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  draft: "Draft",
  ready_for_preliminary_scrutiny: "Ready for preliminary scrutiny",
  under_preliminary_scrutiny: "Under preliminary scrutiny",
  awaiting_additional_evidence: "Awaiting additional evidence",
  preliminary_scrutiny_completed: "Preliminary scrutiny completed",
};

export const STATUS_DESCRIPTIONS: Record<ApplicationStatus, string> = {
  draft: "Being prepared in ReguLens. Details can still be edited.",
  ready_for_preliminary_scrutiny:
    "Details are frozen for internal scrutiny. This is a prototype workflow step: it does not confirm that required documents are present, valid or authentic.",
  under_preliminary_scrutiny: "A reviewer is carrying out internal preliminary scrutiny.",
  awaiting_additional_evidence: "Internal scrutiny is paused until additional evidence is provided.",
  preliminary_scrutiny_completed:
    "Internal preliminary scrutiny is finished. This is not an AICTE approval or rejection; final decisions rest with authorised officials.",
};

/** Button text for each target status, from the user's point of view. */
export const TRANSITION_ACTIONS: Record<ApplicationStatus, string> = {
  draft: "Return to draft",
  ready_for_preliminary_scrutiny: "Mark ready for preliminary scrutiny",
  under_preliminary_scrutiny: "Start preliminary scrutiny",
  awaiting_additional_evidence: "Request additional evidence",
  preliminary_scrutiny_completed: "Complete preliminary scrutiny",
};

export const STATUS_STYLES: Record<ApplicationStatus, string> = {
  draft: "bg-surface-muted text-ink ring-line",
  ready_for_preliminary_scrutiny: "bg-info-bg text-brand-800 ring-info-line",
  under_preliminary_scrutiny: "bg-info-bg text-info-700 ring-info-line",
  awaiting_additional_evidence: "bg-warning-bg text-warning-800 ring-warning-line",
  preliminary_scrutiny_completed: "bg-success-bg text-success-700 ring-success-line",
};

export const APPLICATION_TYPE_LABELS: Record<ApplicationType, string> = {
  eoa_no_change: "EoA — no change",
  increase_in_intake: "Increase in intake",
  reduction_in_intake: "Reduction in intake",
  introduction_of_new_course: "Introduction of new course",
  change_of_institution_name: "Change of institution name",
};

export const INSTITUTION_TYPE_LABELS: Record<InstitutionType, string> = {
  government: "Government",
  government_aided: "Government aided",
  private_self_financing: "Private (self-financing)",
  deemed_university: "Deemed to be university",
  state_private_university: "State private university",
};

export const RECORD_STATUS_LABELS: Record<RecordStatus, string> = { active: "Active", inactive: "Inactive" };

export const PROGRAMME_LEVEL_LABELS: Record<ProgrammeLevel, string> = {
  diploma: "Diploma",
  undergraduate: "Undergraduate",
  postgraduate: "Postgraduate",
};

export const SHIFT_LABELS: Record<Shift, string> = { first: "First shift", second: "Second shift" };

export const DOCUMENT_CATEGORY_LABELS: Record<DocumentCategory, string> = {
  fire_safety_certificate: "Fire Safety Certificate",
  occupancy_certificate: "Occupancy Certificate",
  completion_certificate: "Completion Certificate",
  structural_stability_certificate: "Structural Stability Certificate",
  building_plan: "Building Plan",
  university_noc: "University NOC",
  trust_resolution: "Trust Resolution",
  other: "Other / Unclassified",
};

export const DOCUMENT_STATUS_LABELS: Record<DocumentStatus, string> = {
  uploaded: "Uploaded",
  duplicate_detected: "Duplicate detected",
  intake_failed: "Intake failed",
};

export const DOCUMENT_STATUS_STYLES: Record<DocumentStatus, string> = {
  uploaded: "bg-surface-muted text-ink ring-line",
  duplicate_detected: "bg-warning-bg text-warning-800 ring-warning-line",
  intake_failed: "bg-danger-bg text-danger-700 ring-danger-line",
};

export const PROCESSING_STATUS_LABELS: Record<ProcessingStatus, string> = {
  completed: "Processed",
  completed_with_warnings: "Processed with warnings",
  failed: "Processing failed",
};

export const PROCESSING_STATUS_STYLES: Record<ProcessingStatus, string> = {
  completed: "bg-success-bg text-success-700 ring-success-line",
  completed_with_warnings: "bg-warning-bg text-warning-800 ring-warning-line",
  failed: "bg-danger-bg text-danger-700 ring-danger-line",
};

export const PAGE_STATUS_LABELS: Record<PageStatus, string> = {
  ok: "Readable",
  insufficient_text: "Too little text (OCR not available)",
  ocr_failed: "OCR failed",
  ocr_low_text: "OCR produced little text",
};

export const FIELD_STATUS_LABELS: Record<FieldStatus, string> = {
  extracted: "Extracted",
  not_found: "Not found",
  ambiguous: "Ambiguous",
  unverified: "Unverified",
};

export const FIELD_STATUS_STYLES: Record<FieldStatus, string> = {
  extracted: "bg-success-bg text-success-700 ring-success-line",
  not_found: "bg-surface-muted text-ink ring-line",
  ambiguous: "bg-warning-bg text-warning-800 ring-warning-line",
  unverified: "bg-danger-bg text-danger-700 ring-danger-line",
};

export function fieldLabel(name: string): string {
  const label = name.replace(/_/g, " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

export const OUTCOME_LABELS: Record<RuleOutcome, string> = {
  pass: "Pass",
  issue: "Issue",
  inconclusive: "Inconclusive",
  not_applicable: "Not applicable",
};

export const OUTCOME_STYLES: Record<RuleOutcome, string> = {
  pass: "bg-success-bg text-success-700 ring-success-line",
  issue: "bg-danger-bg text-danger-700 ring-danger-line",
  inconclusive: "bg-warning-bg text-warning-800 ring-warning-line",
  not_applicable: "bg-surface-muted text-ink-muted ring-line",
};

export const SEVERITY_LABELS: Record<Severity, string> = { high: "High", medium: "Medium", low: "Low", info: "Info" };

export const SEVERITY_STYLES: Record<Severity, string> = {
  high: "bg-danger-700 text-white ring-danger-700",
  medium: "bg-saffron-100 text-warning-800 ring-warning-line",
  low: "bg-info-bg text-info-700 ring-info-line",
  info: "bg-surface-muted text-ink ring-line",
};

export const FINDING_KIND_LABELS: Record<FindingKind, string> = {
  rule_finding: "Rule finding",
  anomaly_indicator: "Anomaly indicator",
};

export const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  not_reviewed: "Not reviewed",
  confirmed: "Confirmed by reviewer",
  dismissed: "Dismissed",
  escalated: "Escalated",
  awaiting_evidence: "Awaiting evidence",
  resolved: "Resolved",
};

export const REVIEW_STATUS_STYLES: Record<ReviewStatus, string> = {
  not_reviewed: "bg-surface-muted text-ink ring-line",
  confirmed: "bg-brand-50 text-brand-800 ring-brand-100",
  dismissed: "bg-surface-muted text-ink-subtle ring-line",
  escalated: "bg-danger-bg text-danger-700 ring-danger-line",
  awaiting_evidence: "bg-warning-bg text-warning-800 ring-warning-line",
  resolved: "bg-success-bg text-success-700 ring-success-line",
};

export const REVIEW_ACTION_LABELS: Record<ReviewActionType, string> = {
  confirm: "Confirm finding",
  dismiss: "Dismiss",
  escalate: "Escalate",
  request_evidence: "Request evidence",
  resolve: "Mark resolved",
  reopen: "Reopen",
  note: "Add observation",
  carried_forward: "Carried forward from previous run",
};

/** Actions that require a reason of at least 10 characters (enforced by the server too). */
export const REASON_REQUIRED: ReviewActionType[] = ["dismiss", "escalate", "resolve", "reopen", "request_evidence", "note"];

export const REVIEW_STATE_LABELS: Record<string, string> = {
  no_scrutiny: "No scrutiny yet",
  not_started: "Review not started",
  in_progress: "Review in progress",
  complete: "No unresolved findings",
};

export const ALERT_EVENT_LABELS: Record<string, string> = {
  high_severity_finding: "High-severity finding",
  scrutiny_completed_with_issues: "Scrutiny completed with issues",
  evidence_requested: "Evidence requested",
  evidence_due_soon: "Evidence due soon",
  evidence_overdue: "Evidence overdue",
  evidence_uploaded: "Evidence uploaded",
  finding_escalated: "Finding escalated",
  processing_failed: "Processing failure",
};

export const VERIFICATION_OUTCOME_LABELS: Record<VerificationOutcome, string> = {
  simulated_match: "Simulated match",
  simulated_mismatch: "Simulated mismatch",
  simulated_expired: "Simulated expired",
  simulated_unavailable: "Simulated registry unavailable",
  manual_review: "Manual review required",
  unsupported: "Unsupported document type",
};

export const SIMULATION_LABEL = "SIMULATED — NOT VERIFIED WITH THE ISSUING AUTHORITY";

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const ACADEMIC_YEARS = ["2024-25", "2025-26", "2026-27", "2027-28"];

export function entries<K extends string>(labels: Record<K, string>): [K, string][] {
  return Object.entries(labels) as [K, string][];
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

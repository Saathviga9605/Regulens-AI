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
  draft: "bg-slate-100 text-slate-700 ring-slate-300",
  ready_for_preliminary_scrutiny: "bg-blue-50 text-blue-800 ring-blue-200",
  under_preliminary_scrutiny: "bg-indigo-50 text-indigo-800 ring-indigo-200",
  awaiting_additional_evidence: "bg-amber-50 text-amber-900 ring-amber-200",
  preliminary_scrutiny_completed: "bg-emerald-50 text-emerald-800 ring-emerald-200",
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
  uploaded: "bg-slate-100 text-slate-700 ring-slate-300",
  duplicate_detected: "bg-amber-50 text-amber-900 ring-amber-200",
  intake_failed: "bg-red-50 text-red-800 ring-red-200",
};

export const PROCESSING_STATUS_LABELS: Record<ProcessingStatus, string> = {
  completed: "Processed",
  completed_with_warnings: "Processed with warnings",
  failed: "Processing failed",
};

export const PROCESSING_STATUS_STYLES: Record<ProcessingStatus, string> = {
  completed: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  completed_with_warnings: "bg-amber-50 text-amber-900 ring-amber-200",
  failed: "bg-red-50 text-red-800 ring-red-200",
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
  extracted: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  not_found: "bg-slate-100 text-slate-700 ring-slate-300",
  ambiguous: "bg-amber-50 text-amber-900 ring-amber-200",
  unverified: "bg-red-50 text-red-800 ring-red-200",
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
  pass: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  issue: "bg-red-50 text-red-800 ring-red-200",
  inconclusive: "bg-amber-50 text-amber-900 ring-amber-200",
  not_applicable: "bg-slate-100 text-slate-600 ring-slate-300",
};

export const SEVERITY_LABELS: Record<Severity, string> = { high: "High", medium: "Medium", low: "Low", info: "Info" };

export const SEVERITY_STYLES: Record<Severity, string> = {
  high: "bg-red-700 text-white ring-red-700",
  medium: "bg-orange-100 text-orange-900 ring-orange-300",
  low: "bg-sky-50 text-sky-900 ring-sky-200",
  info: "bg-slate-100 text-slate-700 ring-slate-300",
};

export const FINDING_KIND_LABELS: Record<FindingKind, string> = {
  rule_finding: "Rule finding",
  anomaly_indicator: "Anomaly indicator",
};

export const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  not_reviewed: "Not reviewed",
  acknowledged: "Acknowledged",
  needs_follow_up: "Needs follow-up",
  dismissed: "Dismissed",
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

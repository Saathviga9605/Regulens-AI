/** Display labels for backend enum values (backend/app/models/enums.py). */

import type {
  ApplicationStatus,
  ApplicationType,
  DocumentCategory,
  DocumentStatus,
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
    "Details are frozen for internal scrutiny. This is a prototype step: document intake and validation are not implemented yet, so it does not confirm that required documents are present.",
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

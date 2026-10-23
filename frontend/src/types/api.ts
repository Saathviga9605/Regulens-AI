/** Types mirroring backend schemas in backend/app/schemas/*.py. Keep both in sync. */

export interface DependencyStatus {
  status: "ok" | "unavailable";
  detail: string | null;
}

export interface HealthResponse {
  app_name: string;
  api_version: string;
  status: "ok" | "degraded";
  database: DependencyStatus;
}

export interface SystemInfoResponse {
  app_name: string;
  app_version: string;
  api_version: string;
  environment: string;
  demo_mode: boolean;
  database_backend: string;
  implemented_capabilities: string[];
  planned_capabilities: string[];
}

export interface ApiErrorDetail {
  loc?: string[];
  msg?: string;
  allowed_transitions?: ApplicationStatus[];
}

export interface ApiErrorBody {
  error: { code: string; message: string; request_id: string; details?: ApiErrorDetail[] };
}

/** Connection state shown in the UI, derived from the real /health response. */
export type ConnectionState =
  | { kind: "loading" }
  | { kind: "connected"; health: HealthResponse; checkedAt: Date }
  | { kind: "degraded"; health: HealthResponse; checkedAt: Date }
  | { kind: "disconnected"; message: string; checkedAt: Date };

// --- Pagination ------------------------------------------------------------------------------

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// --- Institutions ----------------------------------------------------------------------------

export type InstitutionType =
  | "government"
  | "government_aided"
  | "private_self_financing"
  | "deemed_university"
  | "state_private_university";

export type RecordStatus = "active" | "inactive";

export interface InstitutionInput {
  name: string;
  institution_type: InstitutionType;
  state: string;
  district: string;
  address: string;
  trust_name: string;
  property_identifier: string;
}

export type InstitutionUpdate = Partial<InstitutionInput> & { status?: RecordStatus };

export interface InstitutionSummary {
  institution_code: string;
  name: string;
  institution_type: InstitutionType;
  state: string;
  district: string;
  status: RecordStatus;
}

export interface Institution extends InstitutionSummary {
  address: string;
  trust_name: string;
  property_identifier: string;
  created_at: string;
  updated_at: string;
}

export interface InstitutionQuery {
  q?: string;
  state?: string;
  status?: RecordStatus;
  page?: number;
  page_size?: number;
}

// --- Applications ----------------------------------------------------------------------------

export type ApplicationStatus =
  | "draft"
  | "ready_for_preliminary_scrutiny"
  | "under_preliminary_scrutiny"
  | "awaiting_additional_evidence"
  | "preliminary_scrutiny_completed";

export type ApplicationType =
  | "eoa_no_change"
  | "increase_in_intake"
  | "reduction_in_intake"
  | "introduction_of_new_course"
  | "change_of_institution_name";

export type ProgrammeLevel = "diploma" | "undergraduate" | "postgraduate";
export type Shift = "first" | "second";

export interface Programme {
  programme_level: ProgrammeLevel;
  course_name: string;
  shift: Shift;
  existing_intake: number;
  proposed_intake: number;
}

export interface ApplicationInput {
  institution_code: string;
  academic_year: string;
  application_type: ApplicationType;
  programmes: Programme[];
}

export interface ApplicationListItem {
  application_code: string;
  category: "extension_of_approval";
  academic_year: string;
  application_type: ApplicationType;
  status: ApplicationStatus;
  institution: InstitutionSummary;
  programme_count: number;
  total_proposed_intake: number;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InstitutionSnapshot {
  institution_code: string;
  name: string;
  institution_type: InstitutionType;
  state: string;
  district: string;
  address: string;
  trust_name: string;
  property_identifier: string;
  captured_at: string;
}

export interface Application extends ApplicationListItem {
  programmes: Programme[];
  status_changed_at: string;
  is_editable: boolean;
  document_intake_open: boolean;
  allowed_transitions: ApplicationStatus[];
  institution_snapshot: InstitutionSnapshot | null;
}

export interface ApplicationQuery {
  q?: string;
  status?: ApplicationStatus;
  academic_year?: string;
  application_type?: ApplicationType;
  institution_code?: string;
  page?: number;
  page_size?: number;
}

// --- Documents -------------------------------------------------------------------------------

export type DocumentCategory =
  | "fire_safety_certificate"
  | "occupancy_certificate"
  | "completion_certificate"
  | "structural_stability_certificate"
  | "building_plan"
  | "university_noc"
  | "trust_resolution"
  | "other";

/** Intake status only — no OCR, validation or authenticity checks exist yet. */
export type DocumentStatus = "uploaded" | "duplicate_detected" | "intake_failed";

export interface DuplicateReference {
  id: string;
  original_filename: string;
  category: DocumentCategory;
  uploaded_at: string;
}

/** Named to avoid clashing with the DOM `Document` type. */
export interface ApplicationDocument {
  id: string;
  application_code: string;
  original_filename: string;
  category: DocumentCategory;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  status: DocumentStatus;
  duplicate_of: DuplicateReference | null;
  other_application_match_count: number;
  content_available: boolean;
  processing: ProcessingSummary | null;
  description: string | null;
  uploaded_at: string;
  created_at: string;
  updated_at: string;
}

export interface IntakePolicy {
  max_upload_bytes: number;
  accepted_content_types: string[];
  accepted_extensions: string[];
  categories: DocumentCategory[];
  intake_open_statuses: ApplicationStatus[];
}

export interface DocumentUpload {
  file: File;
  category: DocumentCategory;
  description?: string;
  /** Explicitly link the upload to this open evidence request. */
  evidenceRequestId?: string;
}

// --- Processing (Deliverable 4) ---------------------------------------------------------------

export type ProcessingStatus = "completed" | "completed_with_warnings" | "failed";
export type PageMethod = "text_layer" | "ocr" | "none";
export type PageStatus = "ok" | "insufficient_text" | "ocr_failed" | "ocr_low_text";
export type FieldStatus = "extracted" | "not_found" | "ambiguous" | "unverified";
export type ConfidenceLevel = "high" | "medium" | "low";
export type ClassificationConfidence = "high" | "medium" | "uncertain";

export interface ProcessingSummary {
  status: ProcessingStatus;
  pipeline_version: string;
  is_current: boolean;
  predicted_category: DocumentCategory | null;
  classification_confidence: ClassificationConfidence;
  warning_count: number;
  finished_at: string;
}

export interface ExtractedField {
  id: string;
  document_id: string;
  field_name: string;
  raw_value: string | null;
  normalized_value: Record<string, string | number | null> | null;
  page_number: number | null;
  evidence_quote: string | null;
  method: string;
  confidence: ConfidenceLevel;
  status: FieldStatus;
  warnings: string[];
  candidates: { value: string; page_number: number; evidence_quote: string }[];
}

export interface ClassificationSignal {
  signal: string;
  weight: number;
  in_heading: boolean;
}

export interface Classification {
  predicted_category: DocumentCategory | null;
  selected_category: DocumentCategory;
  confidence: ClassificationConfidence;
  score: number;
  signals: ClassificationSignal[];
  alternatives: { category: string; score: number; signals: ClassificationSignal[] }[];
  agrees_with_selected: boolean | null;
}

export interface PageSummary {
  page_number: number;
  method: PageMethod;
  status: PageStatus;
  char_count: number;
  warnings: string[];
}

export interface DocumentPageText extends PageSummary {
  text: string;
}

export interface ProcessingResult {
  document_id: string;
  application_code: string;
  status: ProcessingStatus;
  failure_code: string | null;
  failure_reason: string | null;
  pipeline_version: string;
  is_current: boolean;
  reused_from_cache: boolean;
  ocr_available: boolean;
  page_count: number;
  pages_processed: number;
  warnings: string[];
  classification: Classification;
  pages: PageSummary[];
  fields: ExtractedField[];
  started_at: string;
  finished_at: string;
}

// --- Scrutiny ---------------------------------------------------------------------------------

export type RuleOutcome = "pass" | "issue" | "inconclusive" | "not_applicable";
export type Severity = "info" | "low" | "medium" | "high";
export type FindingKind = "rule_finding" | "anomaly_indicator";
export type ReviewStatus = "not_reviewed" | "confirmed" | "dismissed" | "escalated" | "awaiting_evidence" | "resolved";
export type RunStatus = "running" | "completed" | "completed_with_warnings" | "failed";
export type SourceVerificationStatus = "verified" | "unverified" | "not_applicable";

export interface ScrutinyRule {
  rule_id: string;
  title: string;
  description: string;
  rule_type: string;
  parameters: Record<string, unknown>;
  severity: Severity;
  enabled: boolean;
  source: string;
  source_reference: string | null;
  source_verification_status: SourceVerificationStatus;
  is_demo_only: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface RuleUpdate {
  enabled?: boolean;
  severity?: Severity;
}

export interface EvidenceRef {
  document_id: string;
  document_filename: string;
  field_id: string | null;
  field_name: string | null;
  value: string | null;
  page_number: number | null;
  quote: string | null;
}

export type ComparedValue = Record<string, unknown>;

export interface RunSummaryCounts {
  evaluation_outcomes: Record<RuleOutcome, number>;
  finding_severities: Record<Severity, number>;
  rule_findings: number;
  anomaly_indicators: number;
  documents_considered: number;
  documents_processed_ok: number;
  rules_evaluated: number;
}

export interface ScrutinyRunSummary {
  id: string;
  application_code: string;
  run_number: number;
  status: RunStatus;
  scrutiny_date: string;
  rule_set_version: string;
  summary: Partial<RunSummaryCounts>;
  warnings: string[];
  failure_reason: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface RuleEvaluation {
  id: string;
  rule_id: string;
  rule_version: number;
  subject_key: string;
  outcome: RuleOutcome;
  severity: Severity;
  explanation: string;
  document_ids: string[];
  field_ids: string[];
  evidence: EvidenceRef[];
  compared_values: ComparedValue[];
  missing_evidence: string | null;
  human_review_recommended: boolean;
}

export interface RuleSnapshot {
  rule_id: string;
  version: number;
  title: string;
  rule_type: string;
  severity: Severity;
  source: string;
  source_reference: string | null;
  source_verification_status: SourceVerificationStatus;
  is_demo_only: boolean;
}

export interface ScrutinyRun extends ScrutinyRunSummary {
  rule_snapshot: RuleSnapshot[];
  documents_considered: Record<string, unknown>[];
  evaluations: RuleEvaluation[];
}

export interface Finding {
  id: string;
  run_id: string;
  finding_key: string;
  kind: FindingKind;
  finding_type: string;
  title: string;
  severity: Severity;
  outcome: RuleOutcome;
  explanation: string;
  uncertainty: string | null;
  rule_id: string | null;
  rule_version: number | null;
  detector: string | null;
  document_ids: string[];
  field_ids: string[];
  evidence: EvidenceRef[];
  compared_values: ComparedValue[];
  missing_evidence: string | null;
  human_review_recommended: boolean;
  review_status: ReviewStatus;
  review_note: string | null;
  reviewed_at: string | null;
  review_version: number;
  allowed_actions: ReviewActionType[];
  created_at: string;
}

export interface FindingDetail extends Finding {
  application_code: string;
  run_number: number;
  rule: RuleSnapshot | null;
}

export interface FindingQuery {
  severity?: Severity;
  kind?: FindingKind;
  review_status?: ReviewStatus;
}

export type VerificationOutcome =
  | "simulated_match"
  | "simulated_mismatch"
  | "simulated_expired"
  | "simulated_unavailable"
  | "manual_review"
  | "unsupported";

export interface VerificationAttempt {
  id: string;
  document_id: string | null;
  document_filename: string;
  adapter: string;
  method: string;
  simulated: boolean;
  simulation_label: string | null;
  outcome: VerificationOutcome;
  explanation: string;
  fields_compared: { field: string; document_value: string | null; result: string }[];
  reference_code: string | null;
  created_at: string;
}

// --- Auth, review workspace, audit, alerts, copilot (Deliverable 5) ----------------------------

export type UserRole = "reviewer" | "admin";

export interface User {
  id: string;
  username: string;
  display_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface LoginResponse {
  token: string;
  token_type: string;
  expires_at: string;
  user: User;
}

export interface UserCreateInput {
  username: string;
  display_name: string;
  role: UserRole;
  password: string;
}

export interface UserUpdateInput {
  display_name?: string;
  role?: UserRole;
  is_active?: boolean;
  password?: string;
}

export type ReviewActionType =
  | "confirm"
  | "dismiss"
  | "escalate"
  | "request_evidence"
  | "resolve"
  | "reopen"
  | "note"
  | "carried_forward";

export interface ReviewActionInput {
  action: ReviewActionType;
  expected_version: number;
  note?: string | null;
  evidence_refs?: { document_id: string; page_number?: number | null }[];
  requested_evidence?: string | null;
  due_date?: string | null;
}

export interface ReviewAction {
  id: string;
  finding_id: string;
  action_type: ReviewActionType;
  previous_status: ReviewStatus;
  new_status: ReviewStatus;
  actor_username: string;
  note: string | null;
  evidence_refs: { document_id: string; document_filename: string; page_number: number | null }[];
  evidence_request_id: string | null;
  created_at: string;
}

export type EvidenceRequestStatus = "open" | "fulfilled" | "cancelled";

export interface EvidenceRequest {
  id: string;
  application_code: string;
  finding_id: string | null;
  finding_title: string | null;
  requested_evidence: string;
  reason: string;
  due_date: string | null;
  status: EvidenceRequestStatus;
  is_overdue: boolean;
  version: number;
  created_by: string;
  created_at: string;
  closed_by: string | null;
  closed_at: string | null;
  closing_note: string | null;
  documents: { document_id: string | null; document_filename: string; linked_by: string; linked_at: string }[];
}

export interface EvidenceRequestInput {
  requested_evidence: string;
  reason: string;
  due_date?: string | null;
  finding_id?: string | null;
}

export interface AuditEvent {
  id: string;
  created_at: string;
  actor_username: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  application_id: string | null;
  outcome: "success" | "failure" | "denied";
  request_id: string | null;
  details: Record<string, unknown>;
}

export interface AuditQuery {
  page?: number;
  page_size?: number;
  action?: string;
  actor?: string;
  outcome?: string;
  application_code?: string;
}

export interface AlertItem {
  id: string;
  application_code: string;
  event_type: string;
  severity: string;
  title: string;
  message: string;
  finding_id: string | null;
  evidence_request_id: string | null;
  document_id: string | null;
  created_at: string;
  read: boolean;
}

export interface AlertPage extends Page<AlertItem> {
  unread_count: number;
}

export interface AlertQuery {
  page?: number;
  page_size?: number;
  unread_only?: boolean;
  application_code?: string;
  event_type?: string;
}

export interface QueueItem {
  application_code: string;
  institution_name: string;
  institution_code: string;
  application_type: ApplicationType;
  academic_year: string;
  status: ApplicationStatus;
  latest_run_number: number | null;
  latest_run_status: string | null;
  latest_run_finished_at: string | null;
  unresolved_by_severity: Partial<Record<Severity, number>>;
  unresolved_total: number;
  findings_total: number;
  open_evidence_requests: number;
  overdue_evidence_requests: number;
  review_state: "no_scrutiny" | "not_started" | "in_progress" | "complete";
}

export interface QueuePage extends Page<QueueItem> {
  counts: {
    pending_review: number;
    unresolved_high: number;
    awaiting_additional_evidence: number;
    completed_preliminary_reviews: number;
    no_scrutiny_yet: number;
  };
}

export interface QueueQuery {
  q?: string;
  status?: ApplicationStatus;
  scrutiny_status?: string;
  severity?: Severity;
  unresolved_only?: boolean;
  review_state?: string;
  sort?: string;
  page?: number;
  page_size?: number;
}

export interface CopilotSource {
  id: string;
  kind: string;
  label: string;
  finding_id: string | null;
  document_id: string | null;
  document_filename: string | null;
  page_number: number | null;
  quote: string | null;
}

export interface CopilotAnswer {
  intent: string;
  lines: string[];
  sources: CopilotSource[];
  grounded: boolean;
  limitations: string[];
  disclaimer: string;
  suggestions: string[];
}

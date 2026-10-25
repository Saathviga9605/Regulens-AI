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
  ai_capabilities?: AiCapabilities;
}

export interface AiCapabilities {
  ocr: { engine: string; available: boolean; version?: string; local_only: boolean };
  computer_vision: { engine: string; available: boolean; version: string | null; used_for: string };
  extraction: { method: string; model: string | null };
  local_vision_model: { configured: boolean; note: string };
  local_text_model: { configured: boolean; note: string };
  remote_services: string;
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
  | "building_license"
  | "form_d"
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
  evidence_source?: "text_layer" | "ocr" | null;
  evidence_box?: [number, number, number, number] | null;
  ocr_confidence?: number | null;
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
  ocr_engine?: string | null;
  ocr_confidence?: number | null;
  rotation_degrees?: number;
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
export type RuleProvenance = "regulatory" | "checklist" | "integrity" | "demo";
export type ScrutinyRulesetProfile = "production" | "aph_eoa_demo";

export interface RuleCitation {
  source_sha256: string;
  pdf_page_number: number | null;
  printed_page_label: string | null;
  clause_reference: string;
  quote: string;
  quote_sha256: string;
  ocr_derived: boolean;
}

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
  provenance: RuleProvenance;
  registry_managed: boolean;
  retired: boolean;
  effective_from: string | null;
  effective_to: string | null;
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
  scrutiny_date: string | null;
  scrutiny_date_source: string;
  rule_set_version: string;
  ruleset_profile: ScrutinyRulesetProfile;
  ruleset_profile_version: string;
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
  candidate_id?: string;
  ruleset_profile?: ScrutinyRulesetProfile;
  ruleset_version?: string;
  demo_notice?: string;
  citation?: RuleCitation;
  alternatives?: Array<{ rule_id: string; candidate_id: string; category: string; citation: RuleCitation }>;
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
  cross_case_reviewer: boolean;
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
  cross_case_reviewer?: boolean;
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

// --- Cross-case document reuse (Deliverable 7) -------------------------------------------------------

export type ReuseOutcome = "MATCH_CONFIRMED_FOR_REVIEW" | "CANDIDATE" | "NOT_MATCHED" | "INCONCLUSIVE";
export type PairReviewStatus = "not_reviewed" | "confirmed_candidate" | "dismissed" | "escalated";
export type PairActionType = "confirm_candidate" | "dismiss" | "escalate" | "note";

export interface ScanRun {
  id: string;
  status: "running" | "completed" | "failed";
  pipeline_version: string;
  config_version: string;
  triggered_by: string;
  started_at: string;
  finished_at: string | null;
  documents_scanned: number;
  comparisons: number;
  candidates: number;
  pairs_created: number;
  pairs_reused: number;
  outcome_counts: Partial<Record<ReuseOutcome, number>>;
  failure_reason: string | null;
}

export interface CaseAlert {
  pair_id: string;
  outcome: ReuseOutcome;
  review_status: PairReviewStatus;
  detected_at: string;
  local_document: { document_id: string | null; filename: string | null };
  restricted: boolean;
  linked: { application_code: string | null; institution_name: string | null; filename: string | null } | null;
}

export interface CaseAlertList {
  items: CaseAlert[];
  can_view_details: boolean;
  latest_scan: ScanRun | null;
  notice: string;
}

export interface PairSide {
  document_id: string | null;
  document_available: boolean;
  filename: string | null;
  category: string | null;
  application_code: string | null;
  institution_name: string | null;
  page_count: number | null;
  sha256: string;
}

export interface PairSummary {
  id: string;
  outcome: ReuseOutcome;
  outcome_meaning: string;
  review_status: PairReviewStatus;
  review_version: number;
  candidate_methods: string[];
  candidate_score: number | null;
  pipeline_version: string;
  config_version: string;
  created_at: string;
  updated_at: string;
  a: PairSide;
  b: PairSide;
}

export interface FieldSideView {
  raw_value: string | null;
  page_number: number | null;
  evidence_quote: string | null;
  status: string;
  evidence_source?: "text_layer" | "ocr" | null;
  evidence_box?: [number, number, number, number] | null;
  ocr_confidence?: number | null;
}

export interface FieldComparison {
  field: string;
  kind: string;
  a: FieldSideView | null;
  b: FieldSideView | null;
  normalized?: { a: string | null; b: string | null };
  outcome: "agree" | "conflict" | "inconclusive";
  explanation: string;
  visual_difference?: boolean | null;
}

export interface TextProvenance {
  text_layer_pages: number;
  ocr_pages: number;
  ocr_mean_confidence: number | null;
  unreadable_pages: number;
}

export interface FusionSignal {
  signal: string;
  detail: string;
  ref: string;
}

export interface FusionRecord {
  version: string;
  outcome: string;
  rule: string;
  supporting: FusionSignal[];
  contradicting: FusionSignal[];
  unavailable: FusionSignal[];
  neutral: FusionSignal[];
  fields: { agree: number; conflict: number; inconclusive: number };
  regions: { regions_total: number; regions_on_critical_fields: number; regions_elsewhere: number;
    alignment_verified: boolean; fields_with_visual_difference: string[] };
  quality: { a: TextProvenance; b: TextProvenance };
  note: string;
}

export interface ExplanationStatement {
  kind: "supports" | "contradicts" | "unavailable" | "neutral";
  text: string;
  refs: Record<string, string | number | boolean | null>;
}

export interface Explanation {
  version: string;
  generator: string;
  statements: ExplanationStatement[];
  rule: string;
  disclaimer: string;
}

export interface DifferenceRegion {
  box: [number, number, number, number];
  differing_px: number;
}

export interface GeometricEvidence {
  method: string;
  status: "verified" | "not_verified" | "inconclusive" | "unavailable";
  detector?: string;
  opencv_version?: string | null;
  page_a?: number;
  page_b?: number;
  keypoints_a?: number;
  keypoints_b?: number;
  tentative_matches?: number;
  inliers?: number;
  inlier_ratio?: number;
  coverage?: number;
  reason?: string;
  transform?: { type: string; scale: number; plausible: boolean };
  differences?: { cells_judged: number; cells_different: number; cells_outside_overlap: number; ecc_refined?: boolean;
    regions: DifferenceRegion[] };
  thresholds?: { min_inliers: number; min_inlier_ratio: number; min_coverage: number };
}

export interface MatchEvidence {
  exact: { method: string; equal: boolean; note: string };
  text: { method: string; status: "computed" | "unavailable"; jaccard?: number; containment?: number; reason?: string;
    normalization: string; chars_a?: number; chars_b?: number; low_quality?: boolean; quality_note?: string;
    provenance?: { a: TextProvenance; b: TextProvenance } };
  visual: { method: string; status: "computed" | "unavailable"; distance?: number; similarity?: number; page_a?: number;
    page_b?: number; rotation_b_degrees?: number; reason?: string };
  geometric: GeometricEvidence | null;
  fields: { comparisons: FieldComparison[]; agree: number; conflict: number; inconclusive: number; note: string };
  matched_pages: { page_a: number; page_b: number; basis: string; rotation_b_degrees: number }[];
  reasons: string[];
  uncertainties: string[];
  stage_status: Record<string, string>;
  config: Record<string, unknown>;
  latency_ms: number;
  fusion?: FusionRecord | null;
  explanation?: Explanation | null;
  created_at: string;
}

export interface PairAction {
  id: string;
  action_type: PairActionType;
  previous_status: PairReviewStatus;
  new_status: PairReviewStatus;
  actor_username: string;
  note: string | null;
  created_at: string;
}

export interface PairDetail extends PairSummary {
  evidence: MatchEvidence;
  actions: PairAction[];
  notice: string;
  limitations: string[];
}

export interface EvaluationSummary {
  id: string;
  created_at: string;
  created_by: string;
  eval_version: string;
  dataset_version: string;
  dataset_digest: string;
  config_version: string;
  pipeline_version: string;
  duration_ms: number;
}

export interface Ratio {
  value: number | null;
  numerator: number;
  denominator: number;
  note?: string;
}

export interface ArmMetrics {
  tp: number;
  fp: number;
  tn: number;
  fn: number;
  pairs: number;
  precision: Ratio;
  recall: Ratio;
  hard_negative_fp: number;
  hard_negative_fp_rate: Ratio;
  latency_ms_total: number;
}

export interface EvaluationDetail extends EvaluationSummary {
  results: {
    metrics: Record<string, Record<"A0" | "A1" | "A4", ArmMetrics>>;
    a4_outcomes: Record<string, Record<ReuseOutcome, number>>;
    field_exact_match: Record<string, Ratio>;
    evidence_traceability: Ratio;
    composition: { documents: number; cases: number; pairs: Record<string, Record<string, number>> };
    environment: { ocr_available: boolean; opencv_version: string | null; unavailable_stages: string[] };
    a1_threshold: number;
  };
}

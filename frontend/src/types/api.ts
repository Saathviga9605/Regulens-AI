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
}

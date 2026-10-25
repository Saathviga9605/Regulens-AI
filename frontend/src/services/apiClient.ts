import type {
  ApiErrorBody,
  ApplicationDocument,
  ApiErrorDetail,
  Application,
  ApplicationInput,
  ApplicationListItem,
  ApplicationQuery,
  ApplicationStatus,
  DocumentPageText,
  DocumentUpload,
  Finding,
  FindingDetail,
  FindingQuery,
  HealthResponse,
  Institution,
  InstitutionInput,
  InstitutionQuery,
  InstitutionUpdate,
  IntakePolicy,
  Page,
  ProcessingResult,
  AlertPage,
  AlertQuery,
  AuditEvent,
  AuditQuery,
  CopilotAnswer,
  EvidenceRequest,
  EvidenceRequestInput,
  LoginResponse,
  QueuePage,
  QueueQuery,
  ReviewAction,
  ReviewActionInput,
  RuleUpdate,
  User,
  UserCreateInput,
  UserUpdateInput,
  CaseAlertList,
  EvaluationDetail,
  EvaluationSummary,
  PairAction,
  PairActionType,
  PairDetail,
  PairReviewStatus,
  PairSummary,
  ReuseOutcome,
  ScanRun,
  ScrutinyRule,
  ScrutinyRun,
  ScrutinyRunSummary,
  ScrutinyRulesetProfile,
  SystemInfoResponse,
  VerificationAttempt,
} from "../types/api";

const DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1";
const REQUEST_TIMEOUT_MS = 8000;
// Processing and scrutiny run synchronously on the server (text extraction, optional OCR).
const LONG_TIMEOUT_MS = 180_000;

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly kind: "network" | "http" | "invalid_response",
    readonly status?: number,
    readonly code?: string,
    readonly details: ApiErrorDetail[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Field errors keyed by dotted path without the "body" prefix, e.g. "programmes.0.course_name". */
  get fieldErrors(): Record<string, string> {
    const errors: Record<string, string> = {};
    for (const d of this.details) {
      if (!d.loc || !d.msg) continue;
      const path = (d.loc[0] === "body" ? d.loc.slice(1) : d.loc).join(".");
      if (path && !errors[path]) errors[path] = d.msg.replace(/^Value error, /, "");
    }
    return errors;
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return typeof value === "object" && value !== null && "error" in value;
}

type Query = Record<string, string | number | undefined>;

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return `${API_BASE_URL}${path}${qs ? `?${qs}` : ""}`;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Query;
  timeoutMs?: number;
}

// --- Session token -------------------------------------------------------------------------------
// Kept in sessionStorage (cleared when the tab closes). Prototype auth: see docs/security.md.
const TOKEN_KEY = "regulens.token";
export const UNAUTHENTICATED_EVENT = "regulens:unauthenticated";
let memoryToken: string | null = null;

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? memoryToken;
  } catch {
    return memoryToken;
  }
}

export function setToken(token: string | null): void {
  memoryToken = token;
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: memory only */
  }
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function handleUnauthenticated(status: number, code?: string) {
  if (status === 401 && code === "not_authenticated" && getToken()) {
    setToken(null);
    window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT));
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? REQUEST_TIMEOUT_MS);
  const headers: Record<string, string> = { Accept: "application/json", ...authHeaders() };
  const isForm = options.body instanceof FormData;
  // FormData sets its own multipart Content-Type (with boundary).
  if (options.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : isForm ? (options.body as FormData) : JSON.stringify(options.body),
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(`Unable to reach the ReguLens API at ${API_BASE_URL}.`, "network");
  } finally {
    clearTimeout(timer);
  }

  if (response.status === 204) return undefined as T;

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError("The API returned a response that is not valid JSON.", "invalid_response", response.status);
  }

  if (!response.ok) {
    if (isApiErrorBody(body)) {
      const { message, code, details } = body.error;
      handleUnauthenticated(response.status, code);
      throw new ApiError(message, "http", response.status, code, details ?? []);
    }
    throw new ApiError(`Request failed with status ${response.status}.`, "http", response.status);
  }
  return body as T;
}

/** Authenticated binary download (documents, reports). Never exposes storage paths. */
async function requestBlob(path: string, query?: Query): Promise<{ blob: Blob; filename: string | null }> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), { headers: authHeaders() });
  } catch {
    throw new ApiError(`Unable to reach the ReguLens API at ${API_BASE_URL}.`, "network");
  }
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      /* not JSON */
    }
    if (isApiErrorBody(body)) {
      handleUnauthenticated(response.status, body.error.code);
      throw new ApiError(body.error.message, "http", response.status, body.error.code);
    }
    throw new ApiError(`Download failed with status ${response.status}.`, "http", response.status);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  return { blob: await response.blob(), filename: match?.[1] ?? null };
}

/** Saves a blob through a temporary object URL (download) or opens it in a new tab. */
export function deliverBlob(blob: Blob, filename: string, mode: "download" | "open"): void {
  const url = URL.createObjectURL(blob);
  if (mode === "open") {
    window.open(url, "_blank", "noopener");
  } else {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Partial<HealthResponse>;
  return (
    (v.status === "ok" || v.status === "degraded") &&
    typeof v.database === "object" &&
    v.database !== null &&
    (v.database.status === "ok" || v.database.status === "unavailable")
  );
}

const enc = encodeURIComponent;

export const apiClient = {
  async getHealth(): Promise<HealthResponse> {
    const body = await request<unknown>("/health");
    if (!isHealthResponse(body)) {
      throw new ApiError("The health endpoint returned an unexpected structure.", "invalid_response");
    }
    return body;
  },
  getSystemInfo(): Promise<SystemInfoResponse> {
    return request<SystemInfoResponse>("/system/info");
  },

  listInstitutions(query: InstitutionQuery = {}): Promise<Page<Institution>> {
    return request("/institutions", { query: { ...query } });
  },
  getInstitution(code: string): Promise<Institution> {
    return request(`/institutions/${enc(code)}`);
  },
  createInstitution(input: InstitutionInput): Promise<Institution> {
    return request("/institutions", { method: "POST", body: input });
  },
  updateInstitution(code: string, input: InstitutionUpdate): Promise<Institution> {
    return request(`/institutions/${enc(code)}`, { method: "PATCH", body: input });
  },

  listApplications(query: ApplicationQuery = {}): Promise<Page<ApplicationListItem>> {
    return request("/applications", { query: { ...query } });
  },
  getApplication(code: string): Promise<Application> {
    return request(`/applications/${enc(code)}`);
  },
  createApplication(input: ApplicationInput): Promise<Application> {
    return request("/applications", { method: "POST", body: input });
  },
  updateApplication(code: string, input: Partial<ApplicationInput>): Promise<Application> {
    return request(`/applications/${enc(code)}`, { method: "PATCH", body: input });
  },
  changeApplicationStatus(code: string, target: ApplicationStatus): Promise<Application> {
    return request(`/applications/${enc(code)}/status`, { method: "POST", body: { target_status: target } });
  },

  getIntakePolicy(): Promise<IntakePolicy> {
    return request("/documents/intake-policy");
  },
  listDocuments(applicationCode: string): Promise<Page<ApplicationDocument>> {
    return request(`/applications/${enc(applicationCode)}/documents`, { query: { page_size: 100 } });
  },
  getDocument(id: string): Promise<ApplicationDocument> {
    return request(`/documents/${enc(id)}`);
  },
  uploadDocument(applicationCode: string, upload: DocumentUpload): Promise<ApplicationDocument> {
    const form = new FormData();
    form.append("file", upload.file, upload.file.name);
    form.append("category", upload.category);
    if (upload.description) form.append("description", upload.description);
    if (upload.evidenceRequestId) form.append("evidence_request_id", upload.evidenceRequestId);
    return request(`/applications/${enc(applicationCode)}/documents`, { method: "POST", body: form });
  },
  deleteDocument(id: string): Promise<void> {
    return request(`/documents/${enc(id)}`, { method: "DELETE" });
  },
  processDocument(id: string, force = false): Promise<ProcessingResult> {
    return request(`/documents/${enc(id)}/processing`, {
      method: "POST",
      query: force ? { force: "true" } : undefined,
      timeoutMs: LONG_TIMEOUT_MS,
    });
  },
  getProcessing(id: string): Promise<ProcessingResult> {
    return request(`/documents/${enc(id)}/processing`);
  },
  getDocumentPages(id: string): Promise<Page<DocumentPageText>> {
    return request(`/documents/${enc(id)}/pages`, { query: { page_size: 100 } });
  },
  runSimulatedIssuerCheck(id: string): Promise<VerificationAttempt> {
    return request(`/documents/${enc(id)}/issuer-verifications`, { method: "POST" });
  },
  listIssuerChecks(id: string): Promise<VerificationAttempt[]> {
    return request(`/documents/${enc(id)}/issuer-verifications`);
  },

  listRules(): Promise<ScrutinyRule[]> {
    return request("/scrutiny-rules");
  },
  updateRule(ruleId: string, update: RuleUpdate): Promise<ScrutinyRule> {
    return request(`/scrutiny-rules/${enc(ruleId)}`, { method: "PATCH", body: update });
  },
  startScrutinyRun(applicationCode: string, rulesetProfile: ScrutinyRulesetProfile = "production"): Promise<ScrutinyRun> {
    return request(`/applications/${enc(applicationCode)}/scrutiny-runs`, {
      method: "POST", body: { ruleset_profile: rulesetProfile }, timeoutMs: LONG_TIMEOUT_MS,
    });
  },
  listScrutinyRuns(applicationCode: string): Promise<Page<ScrutinyRunSummary>> {
    return request(`/applications/${enc(applicationCode)}/scrutiny-runs`, { query: { page_size: 50 } });
  },
  getScrutinyRun(applicationCode: string, runId: string): Promise<ScrutinyRun> {
    return request(`/applications/${enc(applicationCode)}/scrutiny-runs/${enc(runId)}`);
  },
  listRunFindings(applicationCode: string, runId: string, query: FindingQuery = {}): Promise<Page<Finding>> {
    return request(`/applications/${enc(applicationCode)}/scrutiny-runs/${enc(runId)}/findings`, {
      query: { page_size: 100, ...query },
    });
  },
  getFinding(applicationCode: string, findingId: string): Promise<FindingDetail> {
    return request(`/applications/${enc(applicationCode)}/findings/${enc(findingId)}`);
  },
  reviewAction(applicationCode: string, findingId: string, action: ReviewActionInput): Promise<ReviewAction> {
    return request(`/applications/${enc(applicationCode)}/findings/${enc(findingId)}/actions`, { method: "POST", body: action });
  },
  listFindingActions(applicationCode: string, findingId: string): Promise<ReviewAction[]> {
    return request(`/applications/${enc(applicationCode)}/findings/${enc(findingId)}/actions`);
  },
  listApplicationActions(applicationCode: string): Promise<ReviewAction[]> {
    return request(`/applications/${enc(applicationCode)}/review-actions`);
  },

  /** Fetches document content with the session token and opens or saves it. */
  async openDocument(id: string, filename: string, mode: "open" | "download"): Promise<void> {
    const { blob } = await requestBlob(`/documents/${enc(id)}/content`, mode === "download" ? { disposition: "attachment" } : undefined);
    deliverBlob(blob, filename, mode);
  },
  async downloadReport(applicationCode: string, runId: string): Promise<string> {
    const { blob, filename } = await requestBlob(`/applications/${enc(applicationCode)}/scrutiny-runs/${enc(runId)}/report.pdf`);
    const name = filename ?? `ReguLens-preliminary-scrutiny-${applicationCode}.pdf`;
    deliverBlob(blob, name, "download");
    return name;
  },

  // --- Auth & users ------------------------------------------------------------------------------
  login(username: string, password: string): Promise<LoginResponse> {
    return request("/auth/login", { method: "POST", body: { username, password } });
  },
  logout(): Promise<void> {
    return request("/auth/logout", { method: "POST" });
  },
  me(): Promise<User> {
    return request("/auth/me");
  },
  listUsers(): Promise<User[]> {
    return request("/users");
  },
  createUser(input: UserCreateInput): Promise<User> {
    return request("/users", { method: "POST", body: input });
  },
  updateUser(id: string, input: UserUpdateInput): Promise<User> {
    return request(`/users/${enc(id)}`, { method: "PATCH", body: input });
  },

  // --- Workspace ---------------------------------------------------------------------------------
  reviewQueue(query: QueueQuery = {}): Promise<QueuePage> {
    return request("/review-queue", { query: { ...query, unresolved_only: query.unresolved_only ? "true" : undefined } });
  },
  listEvidenceRequests(applicationCode: string, status?: string): Promise<EvidenceRequest[]> {
    return request(`/applications/${enc(applicationCode)}/evidence-requests`, { query: { status } });
  },
  createEvidenceRequest(applicationCode: string, input: EvidenceRequestInput): Promise<EvidenceRequest> {
    return request(`/applications/${enc(applicationCode)}/evidence-requests`, { method: "POST", body: input });
  },
  linkEvidenceDocument(applicationCode: string, requestId: string, documentId: string): Promise<EvidenceRequest> {
    return request(`/applications/${enc(applicationCode)}/evidence-requests/${enc(requestId)}/documents`, {
      method: "POST", body: { document_id: documentId },
    });
  },
  fulfilEvidenceRequest(applicationCode: string, requestId: string, version: number, note?: string): Promise<EvidenceRequest> {
    return request(`/applications/${enc(applicationCode)}/evidence-requests/${enc(requestId)}/fulfil`, {
      method: "POST", body: { expected_version: version, note: note || null },
    });
  },
  cancelEvidenceRequest(applicationCode: string, requestId: string, version: number, reason: string): Promise<EvidenceRequest> {
    return request(`/applications/${enc(applicationCode)}/evidence-requests/${enc(requestId)}/cancel`, {
      method: "POST", body: { expected_version: version, note: reason },
    });
  },
  listAuditEvents(query: AuditQuery = {}): Promise<Page<AuditEvent>> {
    return request("/audit-events", { query: { ...query } });
  },
  listApplicationAudit(applicationCode: string, page = 1): Promise<Page<AuditEvent>> {
    return request(`/applications/${enc(applicationCode)}/audit-events`, { query: { page, page_size: 50 } });
  },
  listAlerts(query: AlertQuery = {}): Promise<AlertPage> {
    return request("/alerts", { query: { ...query, unread_only: query.unread_only ? "true" : undefined } });
  },
  markAlertsRead(ids: string[]): Promise<void> {
    return request("/alerts/read", { method: "POST", body: { alert_ids: ids } });
  },
  markAllAlertsRead(applicationCode?: string): Promise<void> {
    return request("/alerts/read-all", { method: "POST", query: { application_code: applicationCode } });
  },
  askCopilot(applicationCode: string, question: string, findingId?: string): Promise<CopilotAnswer> {
    return request(`/applications/${enc(applicationCode)}/copilot`, {
      method: "POST", body: { question, finding_id: findingId ?? null },
    });
  },

  // Cross-case reuse. Detail endpoints require the cross-case reviewer permission (403 otherwise).
  startCrossCaseScan(applicationCode: string): Promise<ScanRun> {
    return request(`/applications/${enc(applicationCode)}/cross-case-scans`, { method: "POST", timeoutMs: LONG_TIMEOUT_MS });
  },
  listCrossCaseScans(applicationCode: string): Promise<ScanRun[]> {
    return request(`/applications/${enc(applicationCode)}/cross-case-scans`);
  },
  crossCaseAlerts(applicationCode: string): Promise<CaseAlertList> {
    return request(`/applications/${enc(applicationCode)}/cross-case-alerts`);
  },
  listCasePairs(query: { page?: number; page_size?: number; application_code?: string; outcome?: ReuseOutcome;
    review_status?: PairReviewStatus } = {}): Promise<Page<PairSummary>> {
    return request("/case-pairs", { query: { ...query } });
  },
  getCasePair(pairId: string): Promise<PairDetail> {
    return request(`/case-pairs/${enc(pairId)}`);
  },
  async casePairPageImage(pairId: string, side: "a" | "b", page: number): Promise<Blob> {
    return (await requestBlob(`/case-pairs/${enc(pairId)}/pages/${side}/${page}`)).blob;
  },
  addPairAction(pairId: string, action: PairActionType, note: string, expectedVersion: number): Promise<PairDetail> {
    return request(`/case-pairs/${enc(pairId)}/review-actions`, {
      method: "POST", body: { action, note: note || null, expected_version: expectedVersion },
    });
  },
  listPairActions(pairId: string): Promise<PairAction[]> {
    return request(`/case-pairs/${enc(pairId)}/review-actions`);
  },
  runReuseEvaluation(): Promise<EvaluationDetail> {
    return request("/reuse-evaluations", { method: "POST", timeoutMs: LONG_TIMEOUT_MS });
  },
  listReuseEvaluations(): Promise<EvaluationSummary[]> {
    return request("/reuse-evaluations");
  },
  getReuseEvaluation(id: string): Promise<EvaluationDetail> {
    return request(`/reuse-evaluations/${enc(id)}`);
  },
  exportReuseEvaluation(id: string, format: "csv" | "md" | "json"): Promise<{ blob: Blob; filename: string | null }> {
    return requestBlob(`/reuse-evaluations/${enc(id)}/export`, { format });
  },
};

import type {
  ApiErrorBody,
  ApiErrorDetail,
  Application,
  ApplicationInput,
  ApplicationListItem,
  ApplicationQuery,
  ApplicationStatus,
  HealthResponse,
  Institution,
  InstitutionInput,
  InstitutionQuery,
  InstitutionUpdate,
  Page,
  SystemInfoResponse,
} from "../types/api";

const DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1";
const REQUEST_TIMEOUT_MS = 8000;

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

async function request<T>(path: string, options: { method?: string; body?: unknown; query?: Query } = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(`Unable to reach the ReguLens API at ${API_BASE_URL}.`, "network");
  } finally {
    clearTimeout(timer);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError("The API returned a response that is not valid JSON.", "invalid_response", response.status);
  }

  if (!response.ok) {
    if (isApiErrorBody(body)) {
      const { message, code, details } = body.error;
      throw new ApiError(message, "http", response.status, code, details ?? []);
    }
    throw new ApiError(`Request failed with status ${response.status}.`, "http", response.status);
  }
  return body as T;
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
};

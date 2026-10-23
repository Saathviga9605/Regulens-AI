import type { ApiErrorBody, HealthResponse, SystemInfoResponse } from "../types/api";

const DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1";
const REQUEST_TIMEOUT_MS = 8000;

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly kind: "network" | "http" | "invalid_response",
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return typeof value === "object" && value !== null && "error" in value;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
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
    const message = isApiErrorBody(body) ? body.error.message : `Request failed with status ${response.status}.`;
    throw new ApiError(message, "http", response.status);
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
};

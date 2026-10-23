/** Types mirroring backend schemas in backend/app/schemas/system.py. */

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

export interface ApiErrorBody {
  error: { code: string; message: string; request_id: string };
}

/** Connection state shown in the UI, derived from the real /health response. */
export type ConnectionState =
  | { kind: "loading" }
  | { kind: "connected"; health: HealthResponse; checkedAt: Date }
  | { kind: "degraded"; health: HealthResponse; checkedAt: Date }
  | { kind: "disconnected"; message: string; checkedAt: Date };

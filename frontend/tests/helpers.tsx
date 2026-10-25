import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import { App } from "../src/app/App";
import { setToken } from "../src/services/apiClient";
import type {
  Application,
  ApplicationDocument,
  ApplicationListItem,
  HealthResponse,
  Institution,
  IntakePolicy,
  Page,
  User,
} from "../src/types/api";

export const HEALTHY: HealthResponse = {
  app_name: "ReguLens AI",
  api_version: "v1",
  status: "ok",
  database: { status: "ok", detail: null },
};

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export function page<T>(items: T[], extra: Partial<Page<T>> = {}): Page<T> {
  return { items, total: items.length, page: 1, page_size: 20, total_pages: items.length ? 1 : 0, ...extra };
}

export const INSTITUTION: Institution = {
  institution_code: "INST-00001",
  name: "Deccan Ridge Institute of Engineering",
  institution_type: "private_self_financing",
  state: "Maharashtra",
  district: "Pune",
  status: "active",
  address: "Plot 14, Synthetic Knowledge Park, Pune",
  trust_name: "Deccan Ridge Education Society (Synthetic)",
  property_identifier: "SYN-MH-PUN-1",
  created_at: "2026-10-23T10:00:00Z",
  updated_at: "2026-10-23T10:00:00Z",
};

export const LIST_ITEM: ApplicationListItem = {
  application_code: "REG-EoA-2026-0001",
  category: "extension_of_approval",
  academic_year: "2026-27",
  application_type: "eoa_no_change",
  status: "draft",
  institution: {
    institution_code: INSTITUTION.institution_code,
    name: INSTITUTION.name,
    institution_type: INSTITUTION.institution_type,
    state: INSTITUTION.state,
    district: INSTITUTION.district,
    status: "active",
  },
  programme_count: 1,
  total_proposed_intake: 60,
  submitted_at: null,
  created_at: "2026-10-23T10:00:00Z",
  updated_at: "2026-10-23T10:00:00Z",
};

export const DRAFT: Application = {
  ...LIST_ITEM,
  programmes: [
    { programme_level: "undergraduate", course_name: "B.Tech Civil Engineering", shift: "first", existing_intake: 60, proposed_intake: 60 },
  ],
  status_changed_at: "2026-10-23T10:00:00Z",
  is_editable: true,
  document_intake_open: true,
  allowed_transitions: ["ready_for_preliminary_scrutiny"],
  institution_snapshot: null,
};

export const POLICY: IntakePolicy = {
  max_upload_bytes: 20 * 1024 * 1024,
  accepted_content_types: ["application/pdf"],
  accepted_extensions: [".pdf"],
  categories: ["fire_safety_certificate", "occupancy_certificate", "completion_certificate", "building_license", "form_d",
    "structural_stability_certificate", "building_plan", "university_noc", "trust_resolution", "other"],
  intake_open_statuses: ["draft", "awaiting_additional_evidence"],
};

export const DOC: ApplicationDocument = {
  id: "11111111-1111-4111-8111-111111111111",
  application_code: "REG-EoA-2026-0001",
  original_filename: "fire-safety.pdf",
  category: "fire_safety_certificate",
  mime_type: "application/pdf",
  size_bytes: 245760,
  sha256: "a".repeat(64),
  status: "uploaded",
  duplicate_of: null,
  other_application_match_count: 0,
  content_available: true,
  processing: null,
  description: null,
  uploaded_at: "2026-10-23T10:30:00Z",
  created_at: "2026-10-23T10:30:00Z",
  updated_at: "2026-10-23T10:30:00Z",
};

export interface RecordedCall {
  method: string;
  path: string;
  params: URLSearchParams;
  body: unknown;
}

type Handler = (call: RecordedCall) => Response | Promise<Response>;

/**
 * Routes fetch calls by "METHOD /path" (path relative to /api/v1, regex allowed).
 * /health is answered healthy unless overridden. Unmatched calls fail the request with 599.
 */
export function mockApi(routes: Record<string, Handler>) {
  const calls: RecordedCall[] = [];
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = new URL(String(input));
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const method = (init?.method ?? "GET").toUpperCase();
    const call: RecordedCall = {
      method,
      path: decodeURIComponent(path),
      params: url.searchParams,
      body: init?.body instanceof FormData ? init.body : init?.body ? JSON.parse(String(init.body)) : undefined,
    };
    calls.push(call);
    for (const [pattern, handler] of Object.entries(routes)) {
      const [m, p] = pattern.split(" ");
      if (m === method && new RegExp(`^${p}$`).test(call.path)) return handler(call);
    }
    if (method === "GET" && call.path === "/health") return jsonResponse(HEALTHY);
    // Panels on detail pages: default to the real-shaped policy and an empty document list.
    if (method === "GET" && call.path === "/documents/intake-policy") return jsonResponse(POLICY);
    if (method === "GET" && /^\/applications\/[^/]+\/documents$/.test(call.path)) return jsonResponse(page([]));
    if (method === "GET" && /^\/applications\/[^/]+\/scrutiny-runs$/.test(call.path)) return jsonResponse(page([]));
    // Session and workspace panels.
    if (method === "GET" && call.path === "/auth/me") return jsonResponse(currentUser);
    if (method === "GET" && call.path === "/alerts") return jsonResponse({ ...page([]), unread_count: 0 });
    if (method === "GET" && /^\/applications\/[^/]+\/evidence-requests$/.test(call.path)) return jsonResponse([]);
    if (method === "GET" && /^\/applications\/[^/]+\/audit-events$/.test(call.path)) return jsonResponse(page([]));
    if (method === "GET" && /\/findings\/[^/]+\/actions$/.test(call.path)) return jsonResponse([]);
    if (method === "GET" && /^\/applications\/[^/]+\/cross-case-alerts$/.test(call.path)) {
      return jsonResponse({ items: [], can_view_details: currentUser.cross_case_reviewer, latest_scan: null,
        notice: "A possible match is a prompt for human review. Document reuse is not automatically misconduct." });
    }
    return jsonResponse({ error: { code: "unmocked", message: `Unmocked ${method} ${path}`, request_id: "t" } }, 599);
  });
  return { spy, calls, callsTo: (method: string, path: string) => calls.filter((c) => c.method === method && c.path === path) };
}

export const REVIEWER: User = {
  id: "u-reviewer", username: "demo.reviewer", display_name: "Demo Reviewer", role: "reviewer", is_active: true,
  cross_case_reviewer: false, created_at: "2026-10-23T09:00:00Z",
};
export const ADMIN: User = { ...REVIEWER, id: "u-admin", username: "demo.admin", display_name: "Demo Admin", role: "admin" };
export const SENIOR: User = { ...REVIEWER, id: "u-senior", username: "senior.reviewer", display_name: "Senior Reviewer",
  cross_case_reviewer: true };
let currentUser: User = ADMIN;

/** Renders the app signed in (token present, /auth/me answered) unless `signedIn` is false. */
export function renderApp(path: string, options: { user?: User; signedIn?: boolean } = {}) {
  currentUser = options.user ?? ADMIN;
  setToken(options.signedIn === false ? null : "test-token");
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import { App } from "../src/app/App";
import type { Application, ApplicationListItem, HealthResponse, Institution, Page } from "../src/types/api";

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
  allowed_transitions: ["ready_for_preliminary_scrutiny"],
  institution_snapshot: null,
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
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    };
    calls.push(call);
    for (const [pattern, handler] of Object.entries(routes)) {
      const [m, p] = pattern.split(" ");
      if (m === method && new RegExp(`^${p}$`).test(call.path)) return handler(call);
    }
    if (method === "GET" && call.path === "/health") return jsonResponse(HEALTHY);
    return jsonResponse({ error: { code: "unmocked", message: `Unmocked ${method} ${path}`, request_id: "t" } }, 599);
  });
  return { spy, calls, callsTo: (method: string, path: string) => calls.filter((c) => c.method === method && c.path === path) };
}

export function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

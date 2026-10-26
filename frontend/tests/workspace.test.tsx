import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { getToken } from "../src/services/apiClient";
import type { AlertItem, CopilotAnswer, EvidenceRequest, QueuePage, ScrutinyRule } from "../src/types/api";
import { ADMIN, DOC, DRAFT, REVIEWER, jsonResponse, mockApi, page, renderApp } from "./helpers";

const APP = "/applications/REG-EoA-2026-0001";

describe("Authentication", () => {
  it("redirects to sign-in and signs in with the backend", async () => {
    const api = mockApi({
      "POST /auth/login": () => jsonResponse({ token: "new-token", token_type: "bearer", expires_at: "2026-10-24T08:00:00Z", user: REVIEWER }),
    });
    renderApp("/review-queue", { signedIn: false });
    expect(await screen.findByRole("heading", { name: "Sign in to ReguLens AI" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Sign-in details missing");
    await userEvent.type(screen.getByLabelText(/^Username/), "demo.reviewer");
    await userEvent.type(screen.getByLabelText(/^Password/), "a-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Review queue" })).toBeInTheDocument();
    expect(api.callsTo("POST", "/auth/login")[0]!.body).toEqual({ username: "demo.reviewer", password: "a-password" });
    expect(getToken()).toBe("new-token");
  });

  it("shows the server's error for bad credentials", async () => {
    mockApi({
      "POST /auth/login": () => jsonResponse({ error: { code: "invalid_credentials", message: "Invalid username or password.", request_id: "r" } }, 401),
    });
    renderApp("/", { signedIn: false });
    await userEvent.type(await screen.findByLabelText(/^Username/), "x");
    await userEvent.type(screen.getByLabelText(/^Password/), "y");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password.");
  });

  it("returns to sign-in when the session expires", async () => {
    mockApi({
      "GET /applications": () => jsonResponse({ error: { code: "not_authenticated", message: "Sign in to continue.", request_id: "r" } }, 401),
    });
    renderApp("/applications");
    expect(await screen.findByText("Your session has ended. Please sign in again.")).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });

  it("signs out", async () => {
    const api = mockApi({ "POST /auth/logout": () => new Response(null, { status: 204 }) });
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: /Account menu for/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in to ReguLens AI" })).toBeInTheDocument();
    expect(api.callsTo("POST", "/auth/logout")).toHaveLength(1);
  });
});

const QUEUE: QueuePage = {
  items: [{
    application_code: "REG-EoA-2026-0005", institution_name: "Hooghly Riverside Engineering College", institution_code: "INST-00005",
    application_type: "increase_in_intake", academic_year: "2026-27", status: "draft", latest_run_number: 2,
    latest_run_status: "completed", latest_run_finished_at: "2026-10-23T12:00:00Z", unresolved_by_severity: { high: 2, medium: 3 },
    unresolved_total: 5, findings_total: 6, open_evidence_requests: 1, overdue_evidence_requests: 1, review_state: "in_progress",
  }],
  total: 1, page: 1, page_size: 20, total_pages: 1,
  counts: { pending_review: 1, unresolved_high: 2, awaiting_additional_evidence: 1, completed_preliminary_reviews: 0, no_scrutiny_yet: 11 },
};

describe("Review queue", () => {
  it("shows real counts and sends filters to the server", async () => {
    const api = mockApi({ "GET /review-queue": () => jsonResponse(QUEUE) });
    renderApp("/review-queue", { user: REVIEWER });
    const summary = await screen.findByRole("list", { name: "Queue summary" }).catch(() => screen.findByLabelText("Queue summary"));
    expect(summary).toHaveTextContent("Unresolved high-severity findings2");
    const row = within(screen.getByRole("table", { name: "Review queue" })).getAllByRole("row")[1]!;
    expect(row).toHaveTextContent("REG-EoA-2026-0005");
    expect(row).toHaveTextContent("2 high");
    expect(row).toHaveTextContent("(1 overdue)");
    expect(row).toHaveTextContent("Review in progress");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Unresolved severity" }), "high");
    await waitFor(() => expect(api.calls.at(-1)?.params.get("severity")).toBe("high"));
    await userEvent.click(screen.getByRole("checkbox", { name: "Unresolved only" }));
    await waitFor(() => expect(api.calls.at(-1)?.params.get("unresolved_only")).toBe("true"));
  });
});

const REQUEST: EvidenceRequest = {
  id: "er1", application_code: "REG-EoA-2026-0001", finding_id: null, finding_title: null,
  requested_evidence: "Structural stability certificate", reason: "Not uploaded with the application.", due_date: "2026-10-30",
  status: "open", is_overdue: false, version: 1, created_by: "demo.reviewer", created_at: "2026-10-23T12:00:00Z",
  closed_by: null, closed_at: null, closing_note: null, documents: [],
};

describe("Evidence requests", () => {
  it("creates a request, links a document and marks it fulfilled", async () => {
    let request: EvidenceRequest | null = null;
    const api = mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`GET ${APP}/documents`]: () => jsonResponse(page([DOC])),
      [`GET ${APP}/evidence-requests`]: () => jsonResponse(request ? [request] : []),
      [`POST ${APP}/evidence-requests`]: () => { request = REQUEST; return jsonResponse(REQUEST, 201); },
      [`POST ${APP}/evidence-requests/er1/documents`]: () => {
        request = { ...REQUEST, version: 2, documents: [{ document_id: DOC.id, document_filename: DOC.original_filename, linked_by: "demo.reviewer", linked_at: "x" }] };
        return jsonResponse(request, 201);
      },
      [`POST ${APP}/evidence-requests/er1/fulfil`]: () => {
        request = { ...request!, status: "fulfilled", closed_by: "demo.reviewer", closed_at: "2026-10-23T13:00:00Z", version: 3 };
        return jsonResponse(request);
      },
    });
    renderApp(APP, { user: REVIEWER });
    const card = await screen.findByRole("region", { name: "Additional evidence requests" });
    await userEvent.click(within(card).getByRole("button", { name: "New request" }));
    await userEvent.click(within(card).getByRole("button", { name: "Create request" }));
    expect(within(card).getByText("Give a reason (at least 10 characters).")).toBeInTheDocument();
    await userEvent.type(within(card).getByRole("textbox", { name: "Evidence requested" }), "Structural stability certificate");
    await userEvent.type(within(card).getByRole("textbox", { name: "Reason" }), "Not uploaded with the application.");
    await userEvent.click(within(card).getByRole("button", { name: "Create request" }));
    const item = await within(card).findByRole("listitem");
    expect(within(item).getByRole("button", { name: "Mark fulfilled" })).toBeDisabled();

    await userEvent.click(within(item).getByRole("button", { name: "Link uploaded document" }));
    await userEvent.selectOptions(within(item).getByRole("combobox", { name: "Document" }), DOC.id);
    await userEvent.click(within(item).getByRole("button", { name: "Link document" }));
    await waitFor(() => expect(within(card).getByRole("listitem")).toHaveTextContent(`Linked documents: ${DOC.original_filename}`));
    const linked = within(card).getByRole("listitem");
    await userEvent.click(within(linked).getByRole("button", { name: "Mark fulfilled" }));
    await userEvent.click(within(linked).getByRole("button", { name: "Confirm fulfilled" }));
    await waitFor(() => expect(within(card).getByRole("listitem")).toHaveTextContent("fulfilled"));
    expect(api.callsTo("POST", `${APP}/evidence-requests/er1/fulfil`)[0]!.body).toEqual({ expected_version: 2, note: null });
  });

  it("offers explicit request linking when uploading", async () => {
    const api = mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`GET ${APP}/evidence-requests`]: () => jsonResponse([REQUEST]),
      [`POST ${APP}/documents`]: () => jsonResponse(DOC, 201),
    });
    renderApp(APP, { user: REVIEWER });
    await userEvent.click(await screen.findByRole("button", { name: "Upload document" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Document category" }), "structural_stability_certificate");
    await userEvent.upload(screen.getByLabelText("Document file"), new File([new Uint8Array(100)], "ssc.pdf", { type: "application/pdf" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Link to evidence request (optional)" }), "er1");
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(api.callsTo("POST", `${APP}/documents`)).toHaveLength(1));
    expect((api.callsTo("POST", `${APP}/documents`)[0]!.body as FormData).get("evidence_request_id")).toBe("er1");
  });
});

const ALERT: AlertItem = {
  id: "al1", application_code: "REG-EoA-2026-0005", event_type: "finding_escalated", severity: "high",
  title: "Finding escalated for further review", message: "demo.reviewer escalated a finding.", finding_id: "f1",
  evidence_request_id: null, document_id: null, created_at: "2026-10-23T12:00:00Z", read: false,
};

describe("Alerts", () => {
  it("shows the unread badge, lists alerts and marks them read", async () => {
    let read = false;
    const api = mockApi({
      "GET /alerts": () => jsonResponse({ ...page([{ ...ALERT, read }]), unread_count: read ? 0 : 1 }),
      "POST /alerts/read": () => { read = true; return new Response(null, { status: 204 }); },
    });
    renderApp("/alerts", { user: REVIEWER });
    expect(await screen.findByTestId("unread-alerts")).toHaveTextContent("1");
    const list = await screen.findByRole("region", { name: "Alerts" });
    expect(await within(list).findByText("Finding escalated for further review")).toBeInTheDocument();
    expect(within(list).getByRole("link", { name: "Open REG-EoA-2026-0005" })).toHaveAttribute("href", "/applications/REG-EoA-2026-0005");
    await userEvent.click(within(list).getByRole("button", { name: 'Mark "Finding escalated for further review" as read' }));
    await waitFor(() => expect(within(list).queryByText("Unread")).not.toBeInTheDocument());
    expect(api.callsTo("POST", "/alerts/read")[0]!.body).toEqual({ alert_ids: ["al1"] });
  });

  it("shows an empty state", async () => {
    mockApi({});
    renderApp("/alerts");
    expect(await screen.findByText("No alerts.")).toBeInTheDocument();
  });
});

const ANSWER: CopilotAnswer = {
  intent: "explain", grounded: true, limitations: [], disclaimer: "Reviewer aid only.", suggestions: [],
  lines: ["'Conflicting survey number across documents' was raised by rule CON-003 (version 1). [S1, S2]",
    "Quoted document text (untrusted data) from fire.pdf, page 1: “Survey No.: 312”"],
  sources: [
    { id: "S1", kind: "finding", label: "Finding: Conflicting survey number across documents", finding_id: "fd1", document_id: null, document_filename: null, page_number: null, quote: null },
    { id: "S2", kind: "evidence", label: "fire.pdf, page 1", finding_id: "fd1", document_id: "d1", document_filename: "fire.pdf", page_number: 1, quote: "Survey No.: 312" },
  ],
};

describe("Copilot", () => {
  it("answers with sources and opens the cited finding", async () => {
    const api = mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`POST ${APP}/copilot`]: () => jsonResponse(ANSWER),
      [`GET ${APP}/scrutiny-runs`]: () => jsonResponse(page([{ id: "run1", application_code: "x", run_number: 1, status: "completed",
        scrutiny_date: "2026-10-23", rule_set_version: "v", summary: {}, warnings: [], failure_reason: null,
        started_at: "2026-10-23T10:00:00Z", finished_at: null }])),
      [`GET ${APP}/scrutiny-runs/run1`]: () => jsonResponse({ id: "run1", application_code: "x", run_number: 1, status: "completed",
        scrutiny_date: "2026-10-23", rule_set_version: "v", summary: {}, warnings: [], failure_reason: null,
        started_at: "2026-10-23T10:00:00Z", finished_at: null, rule_snapshot: [], documents_considered: [], evaluations: [] }),
      [`GET ${APP}/scrutiny-runs/run1/findings`]: () => jsonResponse(page([{ id: "fd1", run_id: "run1", finding_key: "k",
        kind: "rule_finding", finding_type: "t", title: "Conflicting survey number across documents", severity: "high",
        outcome: "issue", explanation: "312 vs 318", uncertainty: null, rule_id: "CON-003", rule_version: 1, detector: null,
        document_ids: [], field_ids: [], evidence: [], compared_values: [], missing_evidence: null, human_review_recommended: true,
        review_status: "not_reviewed", review_note: null, reviewed_at: null, review_version: 1, allowed_actions: ["confirm"], created_at: "x" }])),
      [`GET ${APP}/findings/fd1`]: () => jsonResponse({ id: "fd1", run_id: "run1", finding_key: "k", kind: "rule_finding",
        finding_type: "t", title: "Conflicting survey number across documents", severity: "high", outcome: "issue",
        explanation: "312 vs 318", uncertainty: null, rule_id: "CON-003", rule_version: 1, detector: null, document_ids: [],
        field_ids: [], evidence: [], compared_values: [], missing_evidence: null, human_review_recommended: true,
        review_status: "not_reviewed", review_note: null, reviewed_at: null, review_version: 1, allowed_actions: ["confirm"],
        created_at: "x", application_code: "x", run_number: 1, rule: null }),
    });
    renderApp(APP, { user: REVIEWER });
    const panel = await screen.findByRole("region", { name: "Reviewer copilot" });
    expect(panel).toHaveTextContent("No AI model is used");
    await userEvent.type(within(panel).getByRole("textbox", { name: "Ask about this application" }), "Why was the survey conflict raised?");
    await userEvent.click(within(panel).getByRole("button", { name: "Ask" }));
    const answer = await within(panel).findByTestId("copilot-answer");
    expect(answer).toHaveTextContent("rule CON-003");
    expect(answer).toHaveTextContent("“Survey No.: 312”");
    expect(api.callsTo("POST", `${APP}/copilot`)[0]!.body).toEqual({ question: "Why was the survey conflict raised?", finding_id: null });
    await userEvent.click(within(answer).getByRole("button", { name: /Open source S1/ }));
    expect(await screen.findByRole("article", { name: "Finding: Conflicting survey number across documents" })).toBeInTheDocument();
  });

  it("shows ungrounded answers and failures honestly", async () => {
    let fail = false;
    mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`POST ${APP}/copilot`]: () => fail
        ? jsonResponse({ error: { code: "internal_error", message: "An unexpected error occurred.", request_id: "r" } }, 500)
        : jsonResponse({ ...ANSWER, intent: "decision", grounded: false, sources: [],
            lines: ["I cannot approve, reject, or determine fraud, forgery or authenticity."],
            limitations: ["Decisions and authenticity determinations are out of scope."] }),
    });
    renderApp(APP, { user: REVIEWER });
    const panel = await screen.findByRole("region", { name: "Reviewer copilot" });
    await userEvent.click(within(panel).getByRole("button", { name: "What should I inspect next?" }));
    expect(await within(panel).findByText(/No supporting records were found/)).toBeInTheDocument();
    expect(within(panel).getByText(/Limitation: Decisions/)).toBeInTheDocument();
    fail = true;
    await userEvent.click(within(panel).getByRole("button", { name: "What is still unresolved?" }));
    expect(await within(panel).findByText("An unexpected error occurred.")).toBeInTheDocument();
  });
});

describe("Reports", () => {
  it("downloads the preliminary report for the selected run", async () => {
    URL.createObjectURL = vi.fn(() => "blob:report");
    URL.revokeObjectURL = vi.fn();
    const run = { id: "run1", application_code: "x", run_number: 1, status: "completed", scrutiny_date: "2026-10-23",
      rule_set_version: "v", summary: {}, warnings: [], failure_reason: null, started_at: "2026-10-23T10:00:00Z", finished_at: null };
    const api = mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`GET ${APP}/scrutiny-runs`]: () => jsonResponse(page([run])),
      [`GET ${APP}/scrutiny-runs/run1`]: () => jsonResponse({ ...run, rule_snapshot: [], documents_considered: [], evaluations: [] }),
      [`GET ${APP}/scrutiny-runs/run1/findings`]: () => jsonResponse(page([])),
      [`GET ${APP}/scrutiny-runs/run1/report.pdf`]: () => new Response(new Blob(["%PDF"]), { status: 200,
        headers: { "Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="ReguLens-preliminary-scrutiny-REG-run1.pdf"' } }),
    });
    renderApp(APP, { user: REVIEWER });
    await userEvent.click(await screen.findByRole("button", { name: "Download preliminary report (run #1)" }));
    expect(await screen.findByText("Downloaded ReguLens-preliminary-scrutiny-REG-run1.pdf.")).toBeInTheDocument();
    expect(api.callsTo("GET", `${APP}/scrutiny-runs/run1/report.pdf`)).toHaveLength(1);
  });
});

describe("Administration and roles", () => {
  const RULE: ScrutinyRule = { rule_id: "CON-003", title: "Survey numbers consistent", description: "d", rule_type: "field_consistency",
    parameters: {}, severity: "high", enabled: true, source: "Generic check", source_reference: null,
    source_verification_status: "not_applicable", is_demo_only: false, provenance: "integrity", registry_managed: false,
    retired: false, effective_from: null, effective_to: null, version: 1, created_at: "x", updated_at: "x" };

  it("makes rules read-only for reviewers", async () => {
    mockApi({ "GET /scrutiny-rules": () => jsonResponse([RULE]) });
    renderApp("/scrutiny-rules", { user: REVIEWER });
    expect(await screen.findByText(/Read-only: only administrators/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Enable CON-003" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Severity for CON-003" })).toBeDisabled();
  });

  it("blocks admin pages for reviewers", async () => {
    mockApi({});
    renderApp("/users", { user: REVIEWER });
    expect(await screen.findByRole("heading", { name: "Administrator access required" })).toBeInTheDocument();
  });

  it("lets administrators view the audit trail with filters", async () => {
    const api = mockApi({
      "GET /audit-events": () => jsonResponse(page([{ id: "e1", created_at: "2026-10-23T12:00:00Z", actor_username: "demo.reviewer",
        action: "finding.confirm", resource_type: "finding", resource_id: "f1", application_id: "a1", outcome: "success",
        request_id: "r1", details: { from: "not_reviewed", to: "confirmed" } }])),
    });
    renderApp("/audit-trail", { user: ADMIN });
    const table = await screen.findByRole("table", { name: "Audit events" });
    expect(table).toHaveTextContent("finding.confirm");
    expect(table).toHaveTextContent("from: not_reviewed · to: confirmed");
    expect(screen.getByText(/not a cryptographically tamper-evident/)).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox", { name: "Action starts with" }), "finding.");
    await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() => expect(api.calls.at(-1)?.params.get("action")).toBe("finding."));
  });

  it("lets administrators create users with validation", async () => {
    const api = mockApi({
      "GET /users": () => jsonResponse([ADMIN, REVIEWER]),
      "POST /users": () => jsonResponse({ ...REVIEWER, id: "u3", username: "new.reviewer" }, 201),
    });
    renderApp("/users", { user: ADMIN });
    expect(await screen.findByRole("table", { name: "Users" })).toHaveTextContent("demo.reviewer");
    expect(screen.getByRole("combobox", { name: "Role for demo.admin" })).toBeDisabled(); // no self-demotion
    const form = screen.getByRole("form", { name: "Create user" });
    await userEvent.click(within(form).getByRole("button", { name: "Create user" }));
    expect(within(form).getByText("At least 10 characters.")).toBeInTheDocument();
    await userEvent.type(within(form).getByRole("textbox", { name: /^Username/ }), "new.reviewer");
    await userEvent.type(within(form).getByRole("textbox", { name: /^Display name/ }), "New Reviewer");
    await userEvent.type(within(form).getByLabelText(/^Initial password/), "long-password-1");
    await userEvent.click(within(form).getByRole("button", { name: "Create user" }));
    expect(await screen.findByText("Created: new.reviewer.")).toBeInTheDocument();
    expect(api.callsTo("POST", "/users")[0]!.body).toEqual({ username: "new.reviewer", display_name: "New Reviewer", role: "reviewer", password: "long-password-1" });
  });

  it("asks for confirmation before changing a role or deactivating a user", async () => {
    const api = mockApi({
      "GET /users": () => jsonResponse([ADMIN, REVIEWER]),
      [`PATCH /users/${REVIEWER.id}`]: () => jsonResponse({ ...REVIEWER, is_active: false }),
    });
    renderApp("/users", { user: ADMIN });
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Role for demo.reviewer" }), "admin");
    const roleDialog = screen.getByRole("dialog", { name: "Change role?" });
    await userEvent.keyboard("{Escape}");
    expect(roleDialog).not.toBeInTheDocument();
    expect(api.callsTo("PATCH", `/users/${REVIEWER.id}`)).toHaveLength(0);

    await userEvent.click(screen.getByRole("checkbox", { name: "Active: demo.reviewer" }));
    const dialog = screen.getByRole("dialog", { name: "Deactivate user?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Deactivate" }));
    expect((await screen.findAllByText("Deactivated: demo.reviewer.")).length).toBeGreaterThan(0);
    expect(api.callsTo("PATCH", `/users/${REVIEWER.id}`)[0]!.body).toEqual({ is_active: false });
  });
});

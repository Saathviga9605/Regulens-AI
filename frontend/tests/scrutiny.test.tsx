import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type {
  ApplicationDocument,
  Finding,
  FindingDetail,
  ProcessingResult,
  ScrutinyRule,
  ScrutinyRun,
  VerificationAttempt,
} from "../src/types/api";
import { DOC, DRAFT, jsonResponse, mockApi, page, renderApp } from "./helpers";

const APP = "/applications/REG-EoA-2026-0001";
const DOCS = `${APP}/documents`;
const RUNS = `${APP}/scrutiny-runs`;
const SIM = "SIMULATED — NOT VERIFIED WITH THE ISSUING AUTHORITY";

const PROCESSED: ProcessingResult = {
  document_id: DOC.id,
  application_code: "REG-EoA-2026-0001",
  status: "completed",
  failure_code: null,
  failure_reason: null,
  pipeline_version: "p1+cls-1+label_regex_v1",
  is_current: true,
  reused_from_cache: false,
  ocr_available: false,
  page_count: 1,
  pages_processed: 1,
  warnings: [],
  classification: {
    predicted_category: "fire_safety_certificate", selected_category: "fire_safety_certificate", confidence: "high",
    score: 0.93, signals: [{ signal: "phrase 'fire safety certificate'", weight: 10, in_heading: true }],
    alternatives: [], agrees_with_selected: true,
  },
  pages: [{ page_number: 1, method: "text_layer", status: "ok", char_count: 420, warnings: [] }],
  fields: [
    { id: "f1", document_id: DOC.id, field_name: "valid_until", raw_value: "13 March 2029",
      normalized_value: { date: "2029-03-13" }, page_number: 1, evidence_quote: "Valid Until: 13 March 2029",
      method: "label_regex_v1", confidence: "high", status: "extracted", warnings: [], candidates: [] },
    { id: "f2", document_id: DOC.id, field_name: "issuing_authority", raw_value: null, normalized_value: null,
      page_number: null, evidence_quote: null, method: "label_regex_v1", confidence: "low", status: "not_found",
      warnings: ["No labelled value found in the readable text."], candidates: [] },
  ],
  started_at: "2026-10-23T10:00:00Z",
  finished_at: "2026-10-23T10:00:01Z",
};

const FINDING: Finding = {
  id: "fd1", run_id: "run2", finding_key: "rule:CON-003:across_documents", kind: "rule_finding",
  finding_type: "cross_document_conflict", title: "Conflicting survey number across documents", severity: "high",
  outcome: "issue", explanation: "'312' in 'fire.pdf' (p.1) vs '318' in 'occupancy.pdf' (p.1).", uncertainty: null,
  rule_id: "CON-003", rule_version: 1, detector: null, document_ids: ["d1", "d2"], field_ids: ["a", "b"],
  evidence: [
    { document_id: "d1", document_filename: "fire.pdf", field_id: "a", field_name: "survey_number", value: "312", page_number: 1, quote: "Survey No.: 312" },
    { document_id: "d2", document_filename: "occupancy.pdf", field_id: "b", field_name: "survey_number", value: "318", page_number: 1, quote: "Survey No.: 318" },
  ],
  compared_values: [{ source: "'fire.pdf' p.1", value: "312" }], missing_evidence: null,
  human_review_recommended: true, review_status: "not_reviewed", review_note: null, reviewed_at: null,
  review_version: 1, allowed_actions: ["confirm", "dismiss", "escalate", "request_evidence", "note"],
  created_at: "2026-10-23T11:00:00Z",
};

const INDICATOR: Finding = {
  ...FINDING, id: "fd2", finding_key: "anomaly:exact_duplicate:x", kind: "anomaly_indicator", finding_type: "exact_duplicate",
  title: "Exact duplicate file: plan-copy.pdf", severity: "low", outcome: "inconclusive", rule_id: null, rule_version: null,
  detector: "exact_duplicate", uncertainty: "Identical files are usually accidental re-uploads. This is not evidence of misconduct.",
};

const EXPECTED_DOC: Finding = {
  ...FINDING, id: "fd3", finding_key: "rule:EXP-001:application", rule_id: "EXP-001", finding_type: "missing_document",
  title: "Expected document not found: fire safety certificate", severity: "medium", evidence: [],
  missing_evidence: "A document uploaded with the category 'structural stability certificate'.",
};

function run(n: number, id: string): ScrutinyRun {
  return {
    id, application_code: "REG-EoA-2026-0001", run_number: n, status: "completed", scrutiny_date: "2026-10-23",
    scrutiny_date_source: "operator_override",
    rule_set_version: "abc123", ruleset_profile: "production", ruleset_profile_version: "database",
    warnings: [], failure_reason: null, started_at: `2026-10-23T1${n}:00:00Z`,
    finished_at: `2026-10-23T1${n}:00:05Z`,
    summary: {
      evaluation_outcomes: { pass: 26, issue: 2, inconclusive: 1, not_applicable: 3 },
      finding_severities: { high: 1, medium: 1, low: 1, info: 0 }, rule_findings: 2, anomaly_indicators: 1,
      documents_considered: 4, documents_processed_ok: 4, rules_evaluated: 16,
    },
    rule_snapshot: [], documents_considered: [],
    evaluations: [
      { id: "e1", rule_id: "CON-001", rule_version: 1, subject_key: "document:d1", outcome: "pass", severity: "high",
        explanation: "Name matches the record.", document_ids: [], field_ids: [], evidence: [], compared_values: [],
        missing_evidence: null, human_review_recommended: false },
      { id: "e2", rule_id: "EXP-004", rule_version: 1, subject_key: "application", outcome: "not_applicable", severity: "low",
        explanation: "Applies only to other application types.", document_ids: [], field_ids: [], evidence: [],
        compared_values: [], missing_evidence: null, human_review_recommended: false },
    ],
  };
}

const DETAIL: FindingDetail = {
  ...EXPECTED_DOC, application_code: "REG-EoA-2026-0001", run_number: 2,
  rule: { rule_id: "EXP-001", version: 1, title: "Fire safety certificate expected (demo)", rule_type: "expected_document",
    severity: "medium", source: "ReguLens prototype demonstration configuration",
    source_reference: "Not verified against the AICTE Approval Process Handbook or any official source",
    source_verification_status: "unverified", is_demo_only: true },
};

async function openDetails(name = DOC.original_filename) {
  await userEvent.click(await screen.findByRole("button", { name: `Details for ${name}` }));
}

describe("Document processing and evidence", () => {
  it("processes a document and shows fields with evidence quotes", async () => {
    let processed = false;
    const api = mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS}`]: () => jsonResponse(page([processed ? { ...DOC, processing: {
        status: "completed", pipeline_version: "p1", is_current: true, predicted_category: "fire_safety_certificate",
        classification_confidence: "high", warning_count: 0, finished_at: "2026-10-23T10:00:01Z" } } : DOC])),
      [`GET /documents/${DOC.id}/processing`]: () =>
        jsonResponse({ error: { code: "not_processed", message: "This document has not been processed yet.", request_id: "r" } }, 404),
      [`POST /documents/${DOC.id}/processing`]: () => { processed = true; return jsonResponse(PROCESSED); },
      [`GET /documents/${DOC.id}/issuer-verifications`]: () => jsonResponse([]),
    });
    renderApp(APP);
    expect(within(await screen.findByRole("table", { name: /Documents for/ })).getByText("Not processed")).toBeInTheDocument();
    await openDetails();
    expect(await screen.findByText("This document has not been processed yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run simulated issuer check" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: `Process ${DOC.original_filename}` }));
    const fields = await screen.findByRole("table", { name: "Extracted fields with evidence" });
    const validRow = within(fields).getByRole("row", { name: /Valid until/ });
    expect(validRow).toHaveTextContent("13 March 2029");
    expect(validRow).toHaveTextContent("Normalised: 2029-03-13");
    expect(validRow).toHaveTextContent("Valid Until: 13 March 2029");
    expect(validRow).toHaveTextContent("Page 1");
    const missingRow = within(fields).getByRole("row", { name: /Issuing authority/ });
    expect(missingRow).toHaveTextContent("Not found");
    expect(missingRow).toHaveTextContent("No evidence in readable text");
    expect(screen.getByText(/Predicted/)).toHaveTextContent("Fire Safety Certificate");
    expect(api.callsTo("POST", `/documents/${DOC.id}/processing`)).toHaveLength(1);
    await waitFor(() => expect(within(screen.getByRole("table", { name: /Documents for/ })).getAllByText("Processed").length).toBeGreaterThan(0));
  });

  it("shows failure reasons and category mismatches honestly", async () => {
    mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS}`]: () => jsonResponse(page([DOC])),
      [`GET /documents/${DOC.id}/processing`]: () => jsonResponse({
        ...PROCESSED, status: "failed", failure_code: "ocr_unavailable", fields: [],
        failure_reason: "No page has a usable text layer and OCR is not available.",
        pages: [{ page_number: 1, method: "none", status: "insufficient_text", char_count: 0, warnings: [] }],
        classification: { ...PROCESSED.classification, predicted_category: null, confidence: "uncertain", signals: [], agrees_with_selected: null },
      }),
      [`GET /documents/${DOC.id}/issuer-verifications`]: () => jsonResponse([]),
    });
    renderApp(APP);
    await openDetails();
    expect(await screen.findByText("No page has a usable text layer and OCR is not available.")).toBeInTheDocument();
    expect(screen.getByText("Processing failed", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("Uncertain")).toBeInTheDocument();
    expect(screen.getByText("No fields were extracted.")).toBeInTheDocument();
  });

  it("loads page text on demand", async () => {
    mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS}`]: () => jsonResponse(page([DOC])),
      [`GET /documents/${DOC.id}/processing`]: () => jsonResponse(PROCESSED),
      [`GET /documents/${DOC.id}/issuer-verifications`]: () => jsonResponse([]),
      [`GET /documents/${DOC.id}/pages`]: () => jsonResponse(page([{
        page_number: 1, method: "text_layer", status: "ok", char_count: 30, warnings: [], text: "FIRE SAFETY CERTIFICATE\nValid Until: 13 March 2029",
      }])),
    });
    renderApp(APP);
    await openDetails();
    await userEvent.click(await screen.findByRole("button", { name: "Show extracted page text" }));
    expect(await screen.findByText(/Page 1 · text layer · Readable/)).toBeInTheDocument();
    expect(screen.getByText(/FIRE SAFETY CERTIFICATE\s+Valid Until/)).toBeInTheDocument();
  });

  it("labels simulated issuer checks unmistakably", async () => {
    const attempt: VerificationAttempt = {
      id: "v1", document_id: DOC.id, document_filename: DOC.original_filename, adapter: "mock_synthetic_registry",
      method: "simulated_reference_lookup", simulated: true, simulation_label: SIM, outcome: "simulated_match",
      explanation: "The extracted fields match a configured synthetic reference record. This does not establish authenticity.",
      fields_compared: [{ field: "certificate_number", document_value: "SYN-1", result: "match" }],
      reference_code: "SYN-REF-0001", source_status: "verified", source_status_label: "Verified", source_type: "SIMULATED",
      created_at: "2026-10-23T12:00:00Z",
    };
    const api = mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS}`]: () => jsonResponse(page([DOC])),
      [`GET /documents/${DOC.id}/processing`]: () => jsonResponse(PROCESSED),
      [`GET /documents/${DOC.id}/issuer-verifications`]: () => jsonResponse([]),
      [`POST /documents/${DOC.id}/issuer-verifications`]: () => jsonResponse(attempt, 201),
    });
    renderApp(APP);
    await openDetails();
    const section = await screen.findByRole("region", { name: "Simulated issuer verification" });
    expect(section).toHaveTextContent(SIM);
    expect(await within(section).findByTestId("source-status-pending")).toHaveTextContent("Verification pending");
    await userEvent.click(within(section).getByRole("button", { name: "Run simulated issuer check" }));
    expect(await within(section).findByTestId("source-status")).toHaveTextContent("Verified");
    expect(section).toHaveTextContent("SIMULATED"); // never presented as a live source
    expect(within(section).getByText(/Adapter result: Simulated match/)).toBeInTheDocument();
    expect((section.textContent ?? "").split(SIM).length - 1).toBeGreaterThanOrEqual(2); // banner + the attempt itself
    expect(section).toHaveTextContent("Synthetic reference: SYN-REF-0001");
    expect(api.callsTo("POST", `/documents/${DOC.id}/issuer-verifications`)).toHaveLength(1);
  });

  it("shows a not-connected source honestly as manual review required", async () => {
    const attempt: VerificationAttempt = {
      id: "v2", document_id: DOC.id, document_filename: DOC.original_filename, adapter: "mock_synthetic_registry",
      method: "simulated_reference_lookup", simulated: true, simulation_label: SIM, outcome: "unsupported",
      explanation: "The simulated registry does not cover this document type.", fields_compared: [], reference_code: null,
      source_status: "manual_review_required", source_status_label: "Manual review required", source_type: "NOT_CONNECTED",
      created_at: "2026-10-23T12:00:00Z",
    };
    mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS}`]: () => jsonResponse(page([DOC])),
      [`GET /documents/${DOC.id}/processing`]: () => jsonResponse(PROCESSED),
      [`GET /documents/${DOC.id}/issuer-verifications`]: () => jsonResponse([attempt]),
    });
    renderApp(APP);
    await openDetails();
    const section = await screen.findByRole("region", { name: "Simulated issuer verification" });
    expect(await within(section).findByTestId("source-status")).toHaveTextContent("Manual review required");
    expect(section).toHaveTextContent("NOT CONNECTED");
    expect(section).not.toHaveTextContent(/Verified/);
  });

  it("process all only processes documents without current results", async () => {
    const done: ApplicationDocument = { ...DOC, id: "done", original_filename: "done.pdf", processing: {
      status: "completed", pipeline_version: "p1", is_current: true, predicted_category: null,
      classification_confidence: "uncertain", warning_count: 0, finished_at: "2026-10-23T10:00:00Z" } };
    const api = mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS}`]: () => jsonResponse(page([DOC, done])),
      [`POST /documents/${DOC.id}/processing`]: () => jsonResponse({ ...PROCESSED, status: "failed", failure_reason: "x" }),
    });
    renderApp(APP);
    await userEvent.click(await screen.findByRole("button", { name: "Process all" }));
    expect(await screen.findByText(/Processed 1 document\(s\); 1 could not be read/)).toBeInTheDocument();
    expect(api.calls.filter((c) => c.method === "POST" && c.path.endsWith("/processing")).map((c) => c.path))
      .toEqual([`/documents/${DOC.id}/processing`]);
  });
});

describe("Preliminary scrutiny", () => {
  function scrutinyApi(extra: Record<string, Parameters<typeof mockApi>[0][string]> = {}) {
    let runs: ScrutinyRun[] = [];
    const api = mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`GET ${RUNS}`]: () => jsonResponse(page(runs)),
      [`POST ${RUNS}`]: () => {
        const created = run(runs.length + 1, `run${runs.length + 1}`);
        runs = [created, ...runs];
        return jsonResponse(created, 201);
      },
      [`GET ${RUNS}/run1`]: () => jsonResponse(run(1, "run1")),
      [`GET ${RUNS}/run2`]: () => jsonResponse(run(2, "run2")),
      [`GET ${RUNS}/run[12]/findings`]: () => jsonResponse(page([FINDING, EXPECTED_DOC, INDICATOR])),
      [`GET ${APP}/findings/fd3`]: () => jsonResponse(DETAIL),
      ...extra,
    });
    return api;
  }

  it("shows the empty state, runs scrutiny and summarises outcomes", async () => {
    const api = scrutinyApi();
    renderApp(APP);
    expect(await screen.findByText(/No scrutiny runs yet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Run preliminary scrutiny" }));

    const findings = await screen.findByRole("region", { name: "Findings" });
    expect(screen.getByText(/Run #1 · scrutiny reference date 2026-10-23 \(operator override\)/)).toBeInTheDocument();
    for (const [label, n] of [["Pass", "26"], ["Issue", "2"], ["Inconclusive", "1"], ["Not applicable", "3"]] as const) {
      expect(screen.getByText(label, { selector: "dt" }).nextSibling).toHaveTextContent(n);
    }
    expect(within(findings).getByText("Rule findings (2)")).toBeInTheDocument();
    expect(within(findings).getByText("Anomaly indicators (1)")).toBeInTheDocument();
    expect(within(findings).getByText("Prompts for attention, not conclusions.")).toBeInTheDocument();
    expect(api.callsTo("POST", RUNS)).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Rerun preliminary scrutiny" })).toBeInTheDocument();
  });

  it("explicitly selects the isolated APH demo profile for the next run", async () => {
    const api = scrutinyApi();
    renderApp(APP);
    const profile = await screen.findByLabelText("Ruleset profile for the next run");
    await userEvent.selectOptions(profile, "aph_eoa_demo");
    expect(screen.getByText("DEMO RULESET - formal approval pending. This isolated profile does not alter production activation.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Run preliminary scrutiny" }));
    await waitFor(() => expect(api.callsTo("POST", RUNS)).toHaveLength(1));
    expect(api.callsTo("POST", RUNS)[0]?.body).toEqual({ ruleset_profile: "aph_eoa_demo" });
  });

  it("opens a finding with its evidence, demo-only rule label and saves a human review", async () => {
    let detail_ = DETAIL;
    const api = scrutinyApi({
      [`GET ${APP}/findings/fd3`]: () => jsonResponse(detail_),
      [`POST ${APP}/findings/fd3/actions`]: (call) => {
        detail_ = { ...DETAIL, review_status: "escalated", review_version: 2, reviewed_at: "2026-10-23T12:00:00Z",
          allowed_actions: ["confirm", "dismiss", "request_evidence", "resolve", "note"] };
        return jsonResponse({ id: "a1", finding_id: "fd3", action_type: (call.body as { action: string }).action,
          previous_status: "not_reviewed", new_status: "escalated", actor_username: "demo.admin",
          note: (call.body as { note: string }).note, evidence_refs: [], evidence_request_id: null,
          created_at: "2026-10-23T12:00:00Z" }, 201);
      },
    });
    renderApp(APP);
    await userEvent.click(await screen.findByRole("button", { name: "Run preliminary scrutiny" }));
    await userEvent.click(await screen.findByRole("button", { name: /Expected document not found/ }));

    const detail = await screen.findByRole("article", { name: /Finding: Expected document not found/ });
    expect(detail).toHaveTextContent("Missing evidence: A document uploaded with the category");
    expect(detail).toHaveTextContent("DEMO-ONLY RULE — not a verified AICTE requirement.");
    expect(detail).toHaveTextContent("Source verification: unverified");
    expect(within(detail).getByRole("region", { name: "System-generated result" })).toBeInTheDocument();

    const review = within(detail).getByRole("region", { name: "Human review" });
    expect(review).toHaveTextContent("Current state: Not reviewed");
    expect(within(review).queryByRole("button", { name: "Mark resolved" })).not.toBeInTheDocument(); // not allowed yet
    await userEvent.click(within(review).getByRole("button", { name: "Escalate" }));
    await userEvent.click(within(review).getByRole("button", { name: "Save: Escalate" }));
    expect(within(review).getByText(/A reason of at least 10 characters is required/)).toBeInTheDocument();
    expect(api.callsTo("POST", `${APP}/findings/fd3/actions`)).toHaveLength(0);

    await userEvent.type(within(review).getByRole("textbox", { name: "Reason (required)" }), "Needs a senior reviewer's view.");
    await userEvent.click(within(review).getByRole("button", { name: "Save: Escalate" }));
    expect(await within(detail).findByText("Escalate recorded.")).toBeInTheDocument();
    expect(api.callsTo("POST", `${APP}/findings/fd3/actions`)[0]!.body).toEqual({
      action: "escalate", expected_version: 1, note: "Needs a senior reviewer's view." });
    await waitFor(() => expect(within(detail).getByRole("region", { name: "Human review" })).toHaveTextContent("Current state: Escalated"));
    // System result stays visible and unchanged.
    expect(detail).toHaveTextContent("Issue");
  });

  it("reports a stale review conflict instead of overwriting", async () => {
    scrutinyApi({
      [`POST ${APP}/findings/fd3/actions`]: () => jsonResponse({ error: { code: "stale_review",
        message: "This finding was updated by someone else. Reload and try again.", request_id: "r" } }, 409),
    });
    renderApp(APP);
    await userEvent.click(await screen.findByRole("button", { name: "Run preliminary scrutiny" }));
    await userEvent.click(await screen.findByRole("button", { name: /Expected document not found/ }));
    const detail = await screen.findByRole("article", { name: /Finding: Expected document not found/ });
    await userEvent.click(within(detail).getByRole("button", { name: "Confirm finding" }));
    await userEvent.click(within(detail).getByRole("button", { name: "Save: Confirm finding" }));
    expect(await within(detail).findByText(/Someone else updated this finding/)).toBeInTheDocument();
  });

  it("shows evidence quotes for both documents of a conflict", async () => {
    scrutinyApi({ [`GET ${APP}/findings/fd1`]: () => jsonResponse({ ...FINDING, application_code: "x", run_number: 1, rule: null }) });
    renderApp(APP);
    await userEvent.click(await screen.findByRole("button", { name: "Run preliminary scrutiny" }));
    await userEvent.click(await screen.findByRole("button", { name: /Conflicting survey number/ }));
    const detail = await screen.findByRole("article");
    expect(detail).toHaveTextContent("fire.pdf · page 1 · Survey number");
    expect(detail).toHaveTextContent("Survey No.: 312");
    expect(detail).toHaveTextContent("occupancy.pdf · page 1 · Survey number");
    expect(detail).toHaveTextContent("Survey No.: 318");
  });

  it("filters findings on the server and keeps run history selectable", async () => {
    const api = scrutinyApi();
    renderApp(APP);
    await userEvent.click(await screen.findByRole("button", { name: "Run preliminary scrutiny" }));
    await screen.findByRole("region", { name: "Findings" });
    await userEvent.click(screen.getByRole("button", { name: "Rerun preliminary scrutiny" }));
    await waitFor(() => expect(screen.getByText(/Run #2 · scrutiny reference date/)).toBeInTheDocument());

    const select = screen.getByRole("combobox", { name: "Scrutiny run" });
    expect(within(select).getAllByRole("option")).toHaveLength(2);
    await userEvent.selectOptions(select, "run1");
    expect(await screen.findByText(/Run #1 · scrutiny reference date/)).toBeInTheDocument();
    expect(api.callsTo("GET", `${RUNS}/run1`).length).toBeGreaterThan(0);

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Severity" }), "high");
    await waitFor(() => expect(api.calls.at(-1)?.params.get("severity")).toBe("high"));
    expect(api.calls.at(-1)?.path).toBe(`${RUNS}/run1/findings`);
  });

  it("lists every evaluation including passes and not-applicable results", async () => {
    scrutinyApi();
    renderApp(APP);
    await userEvent.click(await screen.findByRole("button", { name: "Run preliminary scrutiny" }));
    const table = await screen.findByRole("table", { name: "All rule evaluations for run 1" });
    expect(within(table).getByText("Pass")).toBeInTheDocument();
    expect(within(table).getByText("Not applicable")).toBeInTheDocument();
  });

  it("reports a run that cannot start", async () => {
    scrutinyApi({
      [`POST ${RUNS}`]: () => jsonResponse({ error: { code: "scrutiny_run_in_progress",
        message: "A scrutiny run is already in progress for this application.", request_id: "r" } }, 409),
    });
    renderApp(APP);
    await userEvent.click(await screen.findByRole("button", { name: "Run preliminary scrutiny" }));
    expect(await screen.findByText("A scrutiny run is already in progress for this application.")).toBeInTheDocument();
  });
});

describe("Scrutiny rules administration", () => {
  const RULES: ScrutinyRule[] = [
    { rule_id: "EXP-001", title: "Fire safety certificate expected (demo)", description: "Demo expectation.",
      rule_type: "expected_document", parameters: { category: "fire_safety_certificate" }, severity: "high", enabled: true,
      source: "ReguLens prototype demonstration configuration", source_reference: "Not verified against the AICTE Approval Process Handbook",
      source_verification_status: "unverified", is_demo_only: true, provenance: "demo", registry_managed: false,
      retired: false, effective_from: null, effective_to: null, version: 1, created_at: "2026-10-23T10:00:00Z", updated_at: "2026-10-23T10:00:00Z" },
    { rule_id: "CON-003", title: "Survey numbers consistent across documents", description: "Generic check.",
      rule_type: "field_consistency", parameters: {}, severity: "high", enabled: true,
      source: "Generic document-consistency check (not a regulatory requirement)", source_reference: null,
      source_verification_status: "not_applicable", is_demo_only: false, provenance: "integrity", registry_managed: false,
      retired: false, effective_from: null, effective_to: null, version: 1, created_at: "2026-10-23T10:00:00Z", updated_at: "2026-10-23T10:00:00Z" },
    { rule_id: "REG-101", title: "Registry rule", description: "Immutable imported rule.",
      rule_type: "expected_document", parameters: { category: "fire_safety_certificate" }, severity: "medium", enabled: true,
      source: "Test registry", source_reference: "Test clause", source_verification_status: "verified", is_demo_only: false,
      provenance: "regulatory", registry_managed: true, retired: false, effective_from: "2026-01-01", effective_to: null,
      version: 1, created_at: "2026-10-23T10:00:00Z", updated_at: "2026-10-23T10:00:00Z" },
  ];

  it("shows source labels and disables a rule", async () => {
    const api = mockApi({
      "GET /scrutiny-rules": () => jsonResponse(RULES),
      "PATCH /scrutiny-rules/EXP-001": () => jsonResponse({ ...RULES[0]!, enabled: false, version: 2 }),
    });
    renderApp("/scrutiny-rules");
    const table = await screen.findByRole("table", { name: "Scrutiny rules" });
    const demoRow = within(table).getByRole("row", { name: /EXP-001/ });
    expect(demoRow).toHaveTextContent("Demo-only");
    expect(demoRow).toHaveTextContent("Source not verified");
    expect(within(table).getByRole("row", { name: /CON-003/ })).toHaveTextContent("Integrity check (not a regulatory requirement)");

    await userEvent.click(within(demoRow).getByRole("checkbox", { name: "Enable EXP-001" }));
    const dialog = screen.getByRole("dialog", { name: "Disable rule?" });
    expect(dialog).toHaveTextContent("Future scrutiny runs will not evaluate this rule.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(api.callsTo("PATCH", "/scrutiny-rules/EXP-001")).toHaveLength(0); // nothing sent without confirmation
    await userEvent.click(within(demoRow).getByRole("checkbox", { name: "Enable EXP-001" }));
    await userEvent.click(within(screen.getByRole("dialog", { name: "Disable rule?" })).getByRole("button", { name: "Disable rule" }));
    expect(await screen.findByText(/EXP-001 saved \(now version 2\)/)).toBeInTheDocument();
    expect(api.callsTo("PATCH", "/scrutiny-rules/EXP-001")).toHaveLength(1);
    expect(api.callsTo("PATCH", "/scrutiny-rules/EXP-001")[0]!.body).toEqual({ enabled: false });
  });

  it("shows an update error", async () => {
    mockApi({
      "GET /scrutiny-rules": () => jsonResponse(RULES),
      "PATCH /scrutiny-rules/CON-003": () => jsonResponse({ error: { code: "validation_error", message: "Rule parameters are invalid for this rule type.", request_id: "r" } }, 422),
    });
    renderApp("/scrutiny-rules");
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Severity for CON-003" }), "low");
    const dialog = screen.getByRole("dialog", { name: "Change severity?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Change severity" }));
    // The dialog stays open with the server's reason so the admin can retry or cancel.
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Rule parameters are invalid");
  });

  it("restricts registry-managed rules to audited enable toggles", async () => {
    mockApi({
      "GET /scrutiny-rules": () => jsonResponse(RULES),
      "PATCH /scrutiny-rules/REG-101": () => jsonResponse({ ...RULES[2]!, enabled: false }),
    });
    renderApp("/scrutiny-rules");
    const table = await screen.findByRole("table", { name: "Scrutiny rules" });
    const row = within(table).getByRole("row", { name: /REG-101/ });
    expect(row).toHaveTextContent("Registry-managed · content immutable");
    expect(within(row).queryByRole("combobox", { name: "Severity for REG-101" })).not.toBeInTheDocument();
    await userEvent.click(within(row).getByRole("checkbox", { name: "Enable REG-101" }));
    const dialog = screen.getByRole("dialog", { name: "Disable rule?" });
    expect(dialog).toHaveTextContent("Registry rule content and version stay unchanged.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Disable rule" }));
    expect(await screen.findByText(/REG-101 enabled state saved; content remains version 1/)).toBeInTheDocument();
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CaseAlertList, PairDetail } from "../src/types/api";
import { ADMIN, DRAFT, REVIEWER, SENIOR, jsonResponse, mockApi, renderApp } from "./helpers";

const APP = `/applications/${DRAFT.application_code}`;
const PAIR_ID = "11111111-2222-3333-4444-555555555555";

const RESTRICTED: CaseAlertList = {
  items: [{ pair_id: PAIR_ID, outcome: "MATCH_CONFIRMED_FOR_REVIEW", review_status: "not_reviewed",
    detected_at: "2026-10-25T08:00:00Z", local_document: { document_id: "d-a", filename: "structural-stability-certificate.pdf" },
    restricted: true, linked: null }],
  can_view_details: false, latest_scan: null,
  notice: "A possible match is a prompt for human review. Document reuse is not automatically misconduct.",
};

const AUTHORISED: CaseAlertList = {
  ...RESTRICTED, can_view_details: true,
  items: [{ ...RESTRICTED.items[0]!, restricted: false,
    linked: { application_code: "REG-EoA-2026-0010", institution_name: "Malvan Bay Institute of Technology",
      filename: "stability-cert-scaled.pdf" } }],
};

const side = (code: string, inst: string, file: string) => ({
  document_id: `doc-${code}`, document_available: true, filename: file, category: "structural_stability_certificate",
  application_code: code, institution_name: inst, page_count: 1, sha256: "a".repeat(64),
});

const DETAIL: PairDetail = {
  id: PAIR_ID, outcome: "CANDIDATE", outcome_meaning: "Some evidence of shared content or layout, but not enough to confirm.",
  review_status: "not_reviewed", review_version: 1, candidate_methods: ["text_shingles", "visual_phash"], candidate_score: 0.97,
  pipeline_version: "reuse_cascade_v1+txtnorm_v1", config_version: "reuse_thr_v1",
  created_at: "2026-10-25T08:00:00Z", updated_at: "2026-10-25T08:00:00Z",
  a: side("REG-EoA-2026-0009", "Konkan Coast Institute of Engineering", "structural-stability-certificate.pdf"),
  b: side("REG-EoA-2026-0012", "Sahyadri Heights College of Technology", "structural-stability-2025.pdf"),
  evidence: {
    exact: { method: "sha256", equal: false, note: "Byte identity only." },
    text: { method: "char5_shingle_jaccard+containment", status: "computed", jaccard: 0.9766, containment: 0.9882,
      normalization: "txtnorm_v1" },
    visual: { method: "phash_dct_v1", status: "computed", distance: 0, similarity: 1, page_a: 1, page_b: 1, rotation_b_degrees: 0 },
    geometric: { method: "orb_ransac_v1", status: "verified", detector: "ORB", inliers: 2903, tentative_matches: 2905,
      inlier_ratio: 0.9993, coverage: 0.6842,
      differences: { cells_judged: 82, cells_different: 1, cells_outside_overlap: 0, regions: [{ box: [0.37, 0.22, 0.4, 0.24], differing_px: 134 }] } },
    fields: {
      comparisons: [
        { field: "certificate_number", kind: "identifier", outcome: "conflict", explanation: "Different values with grounded evidence on both sides.",
          a: { raw_value: "SYN-KSC/2025/0907", page_number: 1, evidence_quote: "Certificate No.: SYN-KSC/2025/0907", status: "extracted" },
          b: { raw_value: "SYN-KSC/2025/1120", page_number: 1, evidence_quote: "Certificate No.: SYN-KSC/2025/1120", status: "extracted" } },
        { field: "issue_date", kind: "date", outcome: "inconclusive", explanation: "Value on side B is not found; a missing or unreadable value is not a conflict.",
          a: { raw_value: "27 August 2025", page_number: 1, evidence_quote: "Date of Issue: 27 August 2025", status: "extracted" },
          b: { raw_value: null, page_number: null, evidence_quote: null, status: "not_found" } },
      ],
      agree: 0, conflict: 1, inconclusive: 1, note: "Only grounded values are compared." },
    matched_pages: [{ page_a: 1, page_b: 1, basis: "best pHash page pair", rotation_b_degrees: 0 }],
    reasons: ["Text similarity: Jaccard 0.9766, containment 0.9882.", "1 critical field(s) conflict."],
    uncertainties: ["1 critical field comparison(s) inconclusive (missing or unreadable values)."],
    stage_status: { exact: "computed", text: "computed", visual: "computed", geometric: "verified", fields: "computed" },
    config: {}, latency_ms: 480, created_at: "2026-10-25T08:00:00Z",
  },
  actions: [], notice: "Document reuse is not automatically misconduct. Review the evidence and record your reasoning.",
  limitations: ["Outcomes are matching outcomes for human review — not findings of fraud, forgery, authenticity or misconduct."],
};

beforeEach(() => {
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:page"), revokeObjectURL: vi.fn() }));
});
afterEach(() => vi.unstubAllGlobals());

const png = () => new Response(new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" }), { status: 200 });

describe("Cross-case panel in the application workspace", () => {
  it("shows ordinary reviewers only a restricted alert", async () => {
    mockApi({ [`GET ${APP}`]: () => jsonResponse(DRAFT), [`GET ${APP}/cross-case-alerts`]: () => jsonResponse(RESTRICTED) });
    renderApp(APP, { user: REVIEWER });
    const list = await screen.findByRole("list", { name: "Cross-case alerts" });
    expect(list).toHaveTextContent("structural-stability-certificate.pdf");
    expect(list).toHaveTextContent("Linked-case details are restricted");
    expect(within(list).queryByRole("link", { name: "Open comparison" })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Malvan|stability-cert-scaled/);
    expect(screen.getByText(/Document reuse is not automatically misconduct/)).toBeInTheDocument();
  });

  it("links authorised reviewers to the comparison and runs a scan once", async () => {
    let scans = 0;
    const api = mockApi({
      [`GET ${APP}`]: () => jsonResponse(DRAFT),
      [`GET ${APP}/cross-case-alerts`]: () => jsonResponse(AUTHORISED),
      [`POST ${APP}/cross-case-scans`]: async () => {
        scans += 1;
        await new Promise((r) => setTimeout(r, 30));
        return jsonResponse({ id: "run", status: "completed", pipeline_version: "p", config_version: "reuse_thr_v1",
          triggered_by: "senior.reviewer", started_at: "2026-10-25T08:00:00Z", finished_at: "2026-10-25T08:00:05Z",
          documents_scanned: 1, comparisons: 15, candidates: 4, pairs_created: 4, pairs_reused: 0,
          outcome_counts: { MATCH_CONFIRMED_FOR_REVIEW: 1 }, failure_reason: null }, 201);
      },
    });
    renderApp(APP, { user: SENIOR });
    const link = await screen.findByRole("link", { name: "Open comparison" });
    expect(link).toHaveAttribute("href", `/case-pairs/${PAIR_ID}`);
    expect(screen.getByText(/Malvan Bay Institute of Technology/)).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Run cross-case scan" });
    await userEvent.dblClick(button);
    expect(await screen.findByText(/Cross-case scan completed: 15 comparisons, 4 candidate pair/)).toBeInTheDocument();
    expect(scans).toBe(1);
    expect(api.callsTo("POST", `${APP}/cross-case-scans`)).toHaveLength(1);
  });
});

describe("Case pair comparison page", () => {
  it("shows evidence, field comparison, uncertainty and side-by-side pages", async () => {
    mockApi({
      [`GET /case-pairs/${PAIR_ID}`]: () => jsonResponse(DETAIL),
      [`GET /case-pairs/${PAIR_ID}/pages/(a|b)/1`]: () => png(),
    });
    renderApp(`/case-pairs/${PAIR_ID}`, { user: SENIOR });
    expect(await screen.findByRole("heading", { level: 1, name: "Document pair" })).toBeInTheDocument();
    expect(screen.getByText("Candidate — needs review")).toBeInTheDocument();
    expect(screen.getByText(/not automatically misconduct/)).toBeInTheDocument();
    const metrics = screen.getByLabelText("Matching metrics");
    expect(metrics).toHaveTextContent("Jaccard 0.9766");
    expect(metrics).toHaveTextContent("pHash distance 0/64");
    expect(metrics).toHaveTextContent("2903 inliers / 2905 matches");
    expect(metrics).toHaveTextContent("1 localized difference region");
    const table = screen.getByRole("table", { name: "Critical-field comparison" });
    expect(within(table).getByText("conflict")).toBeInTheDocument();
    expect(table).toHaveTextContent("Certificate No.: SYN-KSC/2025/0907");
    expect(table).toHaveTextContent("a missing or unreadable value is not a conflict");
    expect(screen.getByLabelText("Uncertainties")).toHaveTextContent("inconclusive");
    expect(await screen.findByRole("img", { name: "Case A, page 1" })).toHaveAttribute("src", "blob:page");
    expect(await screen.findByRole("img", { name: "Case B, page 1" })).toBeInTheDocument();
    expect(screen.getByText(/1 localized difference region\(s\) outlined/)).toBeInTheDocument();
    expect(screen.getByText("Sahyadri Heights College of Technology")).toBeInTheDocument();
  });

  it("shows a restricted view when the server refuses (403)", async () => {
    mockApi({
      [`GET /case-pairs/${PAIR_ID}`]: () => jsonResponse({ error: { code: "cross_case_permission_required",
        message: "Cross-case match details require the cross-case reviewer permission.", request_id: "r" } }, 403),
    });
    renderApp(`/case-pairs/${PAIR_ID}`, { user: REVIEWER });
    expect(await screen.findByText("Cross-case reviewer permission required")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("records a disposition with a reason and keeps input on failure", { timeout: 20000 }, async () => {
    let fail = true;
    const api = mockApi({
      [`GET /case-pairs/${PAIR_ID}`]: () => jsonResponse(DETAIL),
      [`GET /case-pairs/${PAIR_ID}/pages/(a|b)/1`]: () => png(),
      [`POST /case-pairs/${PAIR_ID}/review-actions`]: () => {
        if (fail) {
          fail = false;
          return jsonResponse({ error: { code: "stale_review", message: "Someone else updated this pair. Reload and try again.", request_id: "r" } }, 409);
        }
        return jsonResponse({ ...DETAIL, review_status: "dismissed", review_version: 2, actions: [{
          id: "act", action_type: "dismiss", previous_status: "not_reviewed", new_status: "dismissed",
          actor_username: "senior.reviewer", note: "Different certificate on the same issuer template.", created_at: "2026-10-25T09:00:00Z" }] }, 201);
      },
    });
    renderApp(`/case-pairs/${PAIR_ID}`, { user: SENIOR });
    await userEvent.click(within(await screen.findByRole("group", { name: "Pair review actions" })).getByRole("button", { name: "Dismiss" }));
    const dialog = screen.getByRole("dialog", { name: "Dismiss" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Save: Dismiss" }));
    expect(within(dialog).getByText(/at least 10 characters is required/)).toBeInTheDocument();
    expect(api.callsTo("POST", `/case-pairs/${PAIR_ID}/review-actions`)).toHaveLength(0);
    const reason = within(dialog).getByRole("textbox", { name: /Reason/ });
    await userEvent.type(reason, "Different certificate on the same issuer template.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save: Dismiss" }));
    expect(await within(dialog).findByText(/Someone else updated this pair/)).toBeInTheDocument();
    expect(reason).toHaveValue("Different certificate on the same issuer template.");  // kept for retry
    await userEvent.click(within(dialog).getByRole("button", { name: "Save: Dismiss" }));
    expect(await screen.findByRole("list", { name: "Pair review history" })).toHaveTextContent("Dismiss by senior.reviewer");
    expect(api.callsTo("POST", `/case-pairs/${PAIR_ID}/review-actions`).at(-1)!.body).toEqual({
      action: "dismiss", note: "Different certificate on the same issuer template.", expected_version: 1 });
  });
});

describe("Cross-case administration", () => {
  it("asks for confirmation before granting the cross-case permission", async () => {
    const api = mockApi({
      "GET /users": () => jsonResponse([ADMIN, REVIEWER]),
      [`PATCH /users/${REVIEWER.id}`]: () => jsonResponse({ ...REVIEWER, cross_case_reviewer: true }),
    });
    renderApp("/users", { user: ADMIN });
    expect(await screen.findByRole("checkbox", { name: "Cross-case reviewer: demo.admin" })).toBeDisabled(); // no self-grant
    await userEvent.click(screen.getByRole("checkbox", { name: "Cross-case reviewer: demo.reviewer" }));
    const dialog = screen.getByRole("dialog", { name: "Grant cross-case permission?" });
    expect(api.callsTo("PATCH", `/users/${REVIEWER.id}`)).toHaveLength(0);
    await userEvent.click(within(dialog).getByRole("button", { name: "Grant permission" }));
    await waitFor(() => expect(api.callsTo("PATCH", `/users/${REVIEWER.id}`)[0]!.body).toEqual({ cross_case_reviewer: true }));
  });

  it("shows ordinary reviewers an explanation instead of the pair list", async () => {
    const api = mockApi({});
    renderApp("/cross-case", { user: REVIEWER });
    expect(await screen.findByRole("heading", { level: 1, name: "Cross-case document reuse" })).toBeInTheDocument();
    expect(screen.getByText(/require the cross-case reviewer permission/)).toBeInTheDocument();
    expect(api.calls.some((c) => c.path === "/case-pairs")).toBe(false);
    expect(screen.queryByText(/A0 \/ A1 \/ A4 evaluation/)).not.toBeInTheDocument();
  });

  it("lets administrators run the evaluation and shows counts with denominators", async () => {
    mockApi({
      "GET /reuse-evaluations": () => jsonResponse([]),
      "POST /reuse-evaluations": () => jsonResponse({
        id: "e1", created_at: "2026-10-25T10:00:00Z", created_by: "demo.admin", eval_version: "reuse_eval_v1",
        dataset_version: "reuse_ds_v1", dataset_digest: "c579ee4e0209f12c", config_version: "reuse_thr_v1", pipeline_version: "p",
        duration_ms: 1,
        results: {
          metrics: { heldout: {
            A0: { tp: 1, fp: 0, tn: 8, fn: 6, pairs: 15, precision: { value: 1, numerator: 1, denominator: 1 },
              recall: { value: 0.1429, numerator: 1, denominator: 7 }, hard_negative_fp: 0,
              hard_negative_fp_rate: { value: 0, numerator: 0, denominator: 7 }, latency_ms_total: 0 },
            A1: { tp: 0, fp: 0, tn: 8, fn: 7, pairs: 15, precision: { value: null, numerator: 0, denominator: 0, note: "undefined" },
              recall: { value: 0, numerator: 0, denominator: 7 }, hard_negative_fp: 0,
              hard_negative_fp_rate: { value: 0, numerator: 0, denominator: 7 }, latency_ms_total: 1 },
            A4: { tp: 4, fp: 0, tn: 8, fn: 3, pairs: 15, precision: { value: 1, numerator: 4, denominator: 4 },
              recall: { value: 0.5714, numerator: 4, denominator: 7 }, hard_negative_fp: 0,
              hard_negative_fp_rate: { value: 0, numerator: 0, denominator: 7 }, latency_ms_total: 9 } } },
          a4_outcomes: {}, field_exact_match: { issue_date: { value: 0.78, numerator: 18, denominator: 23 } },
          evidence_traceability: { value: 1, numerator: 90, denominator: 90 },
          composition: { documents: 28, cases: 28, pairs: {} },
          environment: { ocr_available: false, opencv_version: "5.0.0", unavailable_stages: ["OCR (Tesseract not configured)"] },
          a1_threshold: 0,
        },
      }, 201),
    });
    renderApp("/cross-case", { user: ADMIN });
    await userEvent.click(await screen.findByRole("button", { name: "Run evaluation" }));
    const result = await screen.findByTestId("evaluation-result");
    expect(result).toHaveTextContent("1.00 (4/4)");
    expect(result).toHaveTextContent("0.57 (4/7)");
    expect(result).toHaveTextContent("n/a (0/0)");  // undefined precision is never shown as 0 or 1
    expect(result).toHaveTextContent("90/90");
    expect(result).toHaveTextContent("OCR (Tesseract not configured)");
  });
});

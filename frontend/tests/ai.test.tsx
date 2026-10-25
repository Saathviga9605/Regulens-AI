import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AiCapabilities, PairDetail, SystemInfoResponse } from "../src/types/api";
import { DRAFT, REVIEWER, SENIOR, jsonResponse, mockApi, renderApp } from "./helpers";

const PAIR_ID = "22222222-3333-4444-5555-666666666666";
const prov = (ocr: boolean) => ({ text_layer_pages: ocr ? 0 : 1, ocr_pages: ocr ? 1 : 0, ocr_mean_confidence: ocr ? 0.91 : null, unreadable_pages: 0 });
const side = (code: string, file: string) => ({ document_id: `d-${code}`, document_available: true, filename: file,
  category: "fire_safety_certificate", application_code: code, institution_name: "Fictional Institute", page_count: 1, sha256: "b".repeat(64) });

const ALTERED: PairDetail = {
  id: PAIR_ID, outcome: "CANDIDATE", outcome_meaning: "Some evidence of shared content.", review_status: "not_reviewed",
  review_version: 1, candidate_methods: ["text_shingles", "visual_phash"], candidate_score: 0.97,
  pipeline_version: "reuse_cascade_v3+txtnorm_v2+phash_dct_v2+orb_ransac_v1+fieldcmp_v2+fusion_v1", config_version: "reuse_thr_v3",
  created_at: "2026-10-25T10:00:00Z", updated_at: "2026-10-25T10:00:00Z",
  a: side("REG-EoA-2026-0001", "source.pdf"), b: side("REG-EoA-2026-0005", "scan.pdf"),
  evidence: {
    exact: { method: "sha256", equal: false, note: "Byte identity only." },
    text: { method: "char5", status: "computed", jaccard: 0.9741, containment: 0.9882, normalization: "txtnorm_v2",
      low_quality: false, provenance: { a: prov(false), b: prov(true) } },
    visual: { method: "phash_dct_v2", status: "computed", distance: 0, page_a: 1, page_b: 1, rotation_b_degrees: 0 },
    geometric: { method: "orb_ransac_v1", status: "verified", inliers: 2903, tentative_matches: 2905, inlier_ratio: 0.99, coverage: 0.68,
      differences: { cells_judged: 82, cells_different: 1, cells_outside_overlap: 0, regions: [{ box: [0.37, 0.22, 0.4, 0.24], differing_px: 134 }] } },
    fields: { comparisons: [
      { field: "certificate_number", kind: "identifier", outcome: "conflict", explanation: "Different values with grounded evidence on both sides.",
        visual_difference: true,
        a: { raw_value: "SYN-VFS/2026/0418", page_number: 1, evidence_quote: "Certificate No.: SYN-VFS/2026/0418", status: "extracted",
          evidence_source: "text_layer", evidence_box: [0.1, 0.22, 0.6, 0.24], ocr_confidence: null },
        b: { raw_value: "SYN-VFS/2026/0481", page_number: 1, evidence_quote: "CertificateNo.:SYN-VFS/2026/0481", status: "extracted",
          evidence_source: "ocr", evidence_box: [0.1, 0.22, 0.6, 0.24], ocr_confidence: 0.93 } },
    ], agree: 3, conflict: 1, inconclusive: 0, note: "" },
    matched_pages: [{ page_a: 1, page_b: 1, basis: "best pHash page pair", rotation_b_degrees: 0 }],
    reasons: ["Rule: shared content or layout with a conflicting critical field."], uncertainties: [],
    stage_status: { exact: "computed", text: "computed", visual: "computed", geometric: "verified", fields: "computed", fusion: "fusion_v1" },
    config: {}, latency_ms: 450, created_at: "2026-10-25T10:00:00Z",
    fusion: { version: "fusion_v1", outcome: "CANDIDATE", rule: "shared content or layout with a conflicting critical field",
      supporting: [{ signal: "geometry", detail: "2903 inliers / 2905 matches, coverage 0.68", ref: "geometric.inliers" }],
      contradicting: [{ signal: "field:certificate_number", detail: "Conflicts in grounded evidence", ref: "fields.comparisons[certificate_number]" },
        { signal: "field_regions", detail: "Differences overlap the evidence of: certificate number", ref: "fields.comparisons[].visual_difference" }],
      unavailable: [], neutral: [], fields: { agree: 3, conflict: 1, inconclusive: 0 },
      regions: { regions_total: 1, regions_on_critical_fields: 1, regions_elsewhere: 0, alignment_verified: true, fields_with_visual_difference: ["certificate_number"] },
      quality: { a: prov(false), b: prov(true) }, note: "Rule-based." },
    explanation: { version: "explain_v1", generator: "deterministic", rule: "shared content or layout with a conflicting critical field",
      disclaimer: "Generated from the stored evidence record, which remains authoritative. Not a finding of misconduct.",
      statements: [
        { kind: "supports", text: "After geometric alignment (2903 inliers, coverage 0.68), 1 localized difference region(s) remain.",
          refs: { "geometric.inliers": 2903, "geometric.coverage": 0.68 } },
        { kind: "contradicts", text: "The certificate number differs: “SYN-VFS/2026/0418” (A, page 1) vs “SYN-VFS/2026/0481” (B, page 1). The aligned images also differ at that line.",
          refs: { "fields[certificate_number].a.raw_value": "SYN-VFS/2026/0418" } },
      ] },
  },
  actions: [], notice: "Document reuse is not automatically misconduct.", limitations: [],
};

beforeEach(() => {
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:p"), revokeObjectURL: vi.fn() }));
});
afterEach(() => vi.unstubAllGlobals());
const png = () => new Response(new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" }), { status: 200 });

describe("Evidence-grounded explanation on the comparison page", () => {
  it("shows statements, the rule, fusion signals, OCR provenance and region-aware field evidence", async () => {
    mockApi({ [`GET /case-pairs/${PAIR_ID}`]: () => jsonResponse(ALTERED), [`GET /case-pairs/${PAIR_ID}/pages/(a|b)/1`]: () => png() });
    renderApp(`/case-pairs/${PAIR_ID}`, { user: SENIOR });
    const statements = await screen.findByRole("list", { name: "Explanation statements" });
    expect(statements.querySelectorAll(":scope > li")).toHaveLength(2);
    expect(statements).toHaveTextContent("Supports");
    expect(statements).toHaveTextContent("“SYN-VFS/2026/0418” (A, page 1) vs “SYN-VFS/2026/0481” (B, page 1)");
    expect(statements).toHaveTextContent("geometric.inliers = 2903");
    expect(screen.getByText(/Outcome rule:/).parentElement).toHaveTextContent("conflicting critical field");
    expect(screen.getByText(/Generated deterministically/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Contradicting" })).toHaveTextContent("Differences overlap the evidence of: certificate number");
    expect(screen.getByText(/1 on critical-field evidence/)).toBeInTheDocument();
    expect(screen.getAllByText(/1 OCR page\(s\) \(score 0.91\)/).length).toBeGreaterThan(0);
    const table = screen.getByRole("table", { name: "Critical-field comparison" });
    expect(table).toHaveTextContent("pixels differ here");
    expect(table).toHaveTextContent("OCR score 0.93");
    expect(await screen.findAllByText(/1 field evidence box/)).toHaveLength(2); // one caption per side
  });

  it("is honest when a pair predates explanations", async () => {
    const legacy = { ...ALTERED, evidence: { ...ALTERED.evidence, fusion: null, explanation: null } };
    mockApi({ [`GET /case-pairs/${PAIR_ID}`]: () => jsonResponse(legacy), [`GET /case-pairs/${PAIR_ID}/pages/(a|b)/1`]: () => png() });
    renderApp(`/case-pairs/${PAIR_ID}`, { user: SENIOR });
    expect(await screen.findByText("No explanation for this evaluation")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Explanation statements" })).not.toBeInTheDocument();
    expect(screen.queryByText("Evidence fusion")).not.toBeInTheDocument();
  });
});

const caps = (ocr: boolean): AiCapabilities => ({
  ocr: { engine: ocr ? "rapidocr" : "none", available: ocr, version: ocr ? "rapidocr-onnxruntime 1.2.3" : "unavailable", local_only: true },
  computer_vision: { engine: "opencv", available: true, version: "5.0.0", used_for: "alignment" },
  extraction: { method: "deterministic", model: null },
  local_vision_model: { configured: false, note: "" }, local_text_model: { configured: false, note: "" }, remote_services: "none",
});
const info = (ocr: boolean): SystemInfoResponse => ({ app_name: "ReguLens AI", app_version: "0.8", api_version: "v1", environment: "development",
  demo_mode: true, database_backend: "sqlite", implemented_capabilities: [], planned_capabilities: [], ai_capabilities: caps(ocr) });
const APP = `/applications/${DRAFT.application_code}`;

describe("Analysis capabilities in the workspace", () => {
  it("states clearly when OCR is unavailable", async () => {
    mockApi({ [`GET ${APP}`]: () => jsonResponse(DRAFT), "GET /system/info": () => jsonResponse(info(false)) });
    renderApp(APP, { user: REVIEWER });
    const box = await screen.findByTestId("analysis-capabilities");
    expect(box).toHaveTextContent("OCR: not available — scanned or photographed pages have no text");
    expect(within(box).getByRole("list", { name: "Scan stages" })).toHaveTextContent("Text layer & OCR — unavailable");
    expect(box).toHaveTextContent("none configured (explanations are generated deterministically");
  });

  it("names the local OCR engine when available", async () => {
    mockApi({ [`GET ${APP}`]: () => jsonResponse(DRAFT), "GET /system/info": () => jsonResponse(info(true)) });
    renderApp(APP, { user: REVIEWER });
    const box = await screen.findByTestId("analysis-capabilities");
    expect(box).toHaveTextContent("OCR: rapidocr (rapidocr-onnxruntime 1.2.3) — local");
    expect(within(box).getByRole("list", { name: "Scan stages" })).not.toHaveTextContent("unavailable");
  });
});

describe("Deliverable 9 status separation and evaluation sections", () => {
  it("explains the status dimensions on the comparison page", async () => {
    mockApi({ [`GET /case-pairs/${PAIR_ID}`]: () => jsonResponse(ALTERED), [`GET /case-pairs/${PAIR_ID}/pages/(a|b)/1`]: () => png() });
    renderApp(`/case-pairs/${PAIR_ID}`, { user: SENIOR });
    const legend = await screen.findByText("What the statuses on this page mean");
    const box = legend.closest("[role=alert], [role=status], div")!.parentElement!;
    expect(box).toHaveTextContent("Reuse outcome");
    expect(box).toHaveTextContent("Reviewer disposition");
    expect(box).toHaveTextContent("Verification pending");
    expect(box).toHaveTextContent("not a finding of fraud");
  });

  it("shows alteration-suite, campus and physical-capture results with counts", async () => {
    const arm = { tp: 1, fp: 0, tn: 1, fn: 1, pairs: 3, precision: { value: 1, numerator: 1, denominator: 1 },
      recall: { value: 0.5, numerator: 1, denominator: 2 }, hard_negative_fp: 0,
      hard_negative_fp_rate: { value: 0, numerator: 0, denominator: 1 }, hard_negative_candidates: 0, inconclusive: 1, latency_ms_total: 1 };
    mockApi({
      "GET /reuse-evaluations": () => jsonResponse([]),
      "POST /reuse-evaluations": () => jsonResponse({ id: "e9", created_at: "2026-10-25T14:00:00Z", created_by: "demo.admin",
        eval_version: "reuse_eval_v3", dataset_version: "reuse_ds_v3", dataset_digest: "x", config_version: "reuse_thr_v4",
        pipeline_version: "p", duration_ms: 1, results: {
          metrics: { heldout_alt: { A0: arm, A1: arm, A4: arm } }, a4_outcomes: {}, field_exact_match: {},
          evidence_traceability: { value: 1, numerator: 10, denominator: 10 }, composition: { documents: 1, cases: 1, pairs: {} },
          environment: { ocr_available: true, opencv_version: "5.0.0", unavailable_stages: [] }, a1_threshold: 0,
          alteration_suite: { heldout_alt: { pairs: 4, candidate: 4, not_matched: 0, inconclusive: 0, confirmed: 0 } },
          campus_experiment: { synthetic: true, note: "Synthetic procedurally drawn facades.",
            metrics: { campus_heldout: { tp: 2, fp: 0, tn: 3, fn: 1, pairs: 6, inconclusive: 0 } } },
          physical_capture: { status: "BLOCKED", reason: "No camera or printer was available.", entries: 0 } } }, 201),
    });
    renderApp("/cross-case", { user: { ...SENIOR, role: "admin" } });
    const { default: userEvent } = await import("@testing-library/user-event");
    await userEvent.click(await screen.findByRole("button", { name: "Run evaluation" }));
    const result = await screen.findByTestId("evaluation-result");
    expect(within(result).getByRole("table", { name: /Altered critical fields/ })).toHaveTextContent("heldout_alt4400");
    expect(within(result).getByRole("region", { name: "Campus-photo experiment" })).toHaveTextContent("TP 2, FP 0, TN 3, FN 1");
    expect(result).toHaveTextContent("Real printed-and-photographed captures: BLOCKED");
    expect(result).toHaveTextContent("heldout_alt 1 inconclusive / 0 hard-negative candidates");
  });
});

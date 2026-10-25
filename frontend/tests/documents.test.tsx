import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ApplicationDocument } from "../src/types/api";
import { DOC, DRAFT, POLICY, jsonResponse, mockApi, page, renderApp } from "./helpers";

const APP_PATH = "/applications/REG-EoA-2026-0001";
const DOCS_PATH = "/applications/REG-EoA-2026-0001/documents";

const DUPLICATE: ApplicationDocument = {
  ...DOC,
  id: "22222222-2222-4222-8222-222222222222",
  original_filename: "fire-safety-copy.pdf",
  status: "duplicate_detected",
  duplicate_of: { id: DOC.id, original_filename: DOC.original_filename, category: DOC.category, uploaded_at: DOC.uploaded_at },
  uploaded_at: "2026-10-23T11:00:00Z",
};

function pdf(name = "occupancy.pdf", size = 1000): File {
  return new File([new Uint8Array(size)], name, { type: "application/pdf" });
}

async function docsTable() {
  return screen.findByRole("table", { name: "Documents for REG-EoA-2026-0001" });
}

describe("Documents panel", () => {
  it("loads the inventory for this application", async () => {
    const api = mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS_PATH}`]: () => jsonResponse(page([DOC, DUPLICATE])),
    });
    renderApp(APP_PATH);

    const table = await docsTable();
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveTextContent("fire-safety.pdf");
    expect(rows[1]).toHaveTextContent("Fire Safety Certificate");
    expect(rows[1]).toHaveTextContent("240.0 KB");
    expect(rows[1]).toHaveTextContent("Uploaded");
    expect(api.callsTo("GET", DOCS_PATH).length).toBeGreaterThan(0);
  });

  it("shows loading, then the empty state", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS_PATH}`]: async () => (await gate, jsonResponse(page([]))),
    });
    renderApp(APP_PATH);
    expect(await screen.findByText("Loading documents…")).toBeInTheDocument();
    release();
    expect(await screen.findByText("No documents have been uploaded for this application.")).toBeInTheDocument();
  });

  it("shows an error state with retry", async () => {
    let fail = true;
    mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS_PATH}`]: () =>
        fail ? jsonResponse({ error: { code: "internal_error", message: "An unexpected error occurred.", request_id: "r" } }, 500)
          : jsonResponse(page([DOC])),
    });
    renderApp(APP_PATH);
    expect(await screen.findByText("An unexpected error occurred.")).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await docsTable()).toHaveTextContent("fire-safety.pdf");
  });

  it("shows duplicate status with a reference to the original", async () => {
    mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS_PATH}`]: () => jsonResponse(page([DOC, { ...DUPLICATE, other_application_match_count: 1 }])),
    });
    renderApp(APP_PATH);
    const row = within(await docsTable()).getAllByRole("row")[2]!;
    expect(row).toHaveTextContent("Duplicate detected");
    expect(row).toHaveTextContent("Same content as “fire-safety.pdf”");
    expect(row).toHaveTextContent("Also present in another application");
  });

  it("shows metadata details with the authenticity disclaimer", async () => {
    mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS_PATH}`]: () => jsonResponse(page([DOC])),
    });
    renderApp(APP_PATH);
    const toggle = await screen.findByRole("button", { name: "Details for fire-safety.pdf" });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(DOC.sha256)).toBeInTheDocument();
    expect(screen.getByText(/does not establish that the document is authentic/i)).toBeInTheDocument();
  });

  it("opens and downloads content through the authenticated backend endpoint", async () => {
    const created: string[] = [];
    URL.createObjectURL = vi.fn(() => { created.push("blob:x"); return "blob:x"; });
    URL.revokeObjectURL = vi.fn();
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null);
    const api = mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS_PATH}`]: () => jsonResponse(page([DOC, { ...DUPLICATE, id: "x", content_available: false }])),
      [`GET /documents/${DOC.id}/content`]: () => new Response(new Blob(["%PDF-1.4"], { type: "application/pdf" }), {
        status: 200, headers: { "Content-Type": "application/pdf" } }),
    });
    renderApp(APP_PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Open fire-safety.pdf" }));
    await waitFor(() => expect(openSpy).toHaveBeenCalledWith("blob:x", "_blank", "noopener"));
    await userEvent.click(screen.getByRole("button", { name: "Download fire-safety.pdf" }));
    await waitFor(() => expect(api.callsTo("GET", `/documents/${DOC.id}/content`)).toHaveLength(2));
    expect(api.callsTo("GET", `/documents/${DOC.id}/content`)[1]!.params.get("disposition")).toBe("attachment");
    const headers = (api.spy.mock.calls.find((c) => String(c[0]).includes("/content"))![1]!.headers) as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer test-token");
    expect(screen.queryByRole("button", { name: "Open fire-safety-copy.pdf" })).not.toBeInTheDocument();
  });

  it("validates on the client before uploading", async () => {
    const api = mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse(DRAFT),
      "GET /documents/intake-policy": () => jsonResponse({ ...POLICY, max_upload_bytes: 2048 }),
    });
    const user = userEvent.setup({ applyAccept: false });
    renderApp(APP_PATH);
    await user.click(await screen.findByRole("button", { name: "Upload PDF" }));
    expect(screen.getByText(/PDF only, up to 2.0 KB/)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Building License" })).toHaveValue("building_license");
    expect(screen.getByRole("option", { name: "Form D" })).toHaveValue("form_d");

    await user.click(screen.getByRole("button", { name: "Upload" }));
    expect(screen.getByText("Select a document category.")).toBeInTheDocument();
    expect(screen.getByText("Choose a PDF file.")).toBeInTheDocument();

    await user.upload(screen.getByLabelText("PDF file"), new File(["hello"], "notes.txt", { type: "text/plain" }));
    await user.click(screen.getByRole("button", { name: "Upload" }));
    expect(screen.getByText("Only .pdf files are accepted.")).toBeInTheDocument();

    await user.upload(screen.getByLabelText("PDF file"), pdf("big.pdf", 5000));
    await user.click(screen.getByRole("button", { name: "Upload" }));
    expect(screen.getByText("File is 4.9 KB; the limit is 2.0 KB.")).toBeInTheDocument();
    expect(api.callsTo("POST", DOCS_PATH)).toHaveLength(0);
  });

  it("uploads to this application and refreshes the inventory", async () => {
    const created: ApplicationDocument = { ...DOC, original_filename: "occupancy.pdf", category: "occupancy_certificate" };
    let listed: ApplicationDocument[] = [];
    const api = mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS_PATH}`]: () => jsonResponse(page(listed)),
      [`POST ${DOCS_PATH}`]: () => {
        listed = [created];
        return jsonResponse(created, 201);
      },
    });
    renderApp(APP_PATH);
    await screen.findByText("No documents have been uploaded for this application.");
    await userEvent.click(screen.getByRole("button", { name: "Upload PDF" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Document category" }), "occupancy_certificate");
    await userEvent.upload(screen.getByLabelText("PDF file"), pdf());
    await userEvent.type(screen.getByRole("textbox", { name: "Description (optional)" }), "Block A");
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));

    expect(await screen.findByText("Uploaded “occupancy.pdf”.")).toBeInTheDocument();
    expect(await docsTable()).toHaveTextContent("occupancy.pdf");
    const body = api.callsTo("POST", DOCS_PATH)[0]!.body as FormData;
    expect(body.get("category")).toBe("occupancy_certificate");
    expect(body.get("description")).toBe("Block A");
    expect((body.get("file") as File).name).toBe("occupancy.pdf");
    expect(screen.queryByRole("form", { name: "Upload document" })).not.toBeInTheDocument();
  });

  it("reports a duplicate upload without implying the original changed", async () => {
    mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse(DRAFT),
      [`POST ${DOCS_PATH}`]: () => jsonResponse(DUPLICATE, 201),
    });
    renderApp(APP_PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Upload PDF" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Document category" }), "other");
    await userEvent.upload(screen.getByLabelText("PDF file"), pdf("fire-safety-copy.pdf"));
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByText(/identical to “fire-safety.pdf”, so it is marked as a duplicate. The original was not changed./))
      .toBeInTheDocument();
  });

  it("shows server rejection of an upload", async () => {
    mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse(DRAFT),
      [`POST ${DOCS_PATH}`]: () =>
        jsonResponse({ error: { code: "invalid_pdf_signature", message: "File content is not a PDF (missing %PDF- signature).",
          request_id: "r", details: [{ loc: ["body", "file"], msg: "File content is not a PDF (missing %PDF- signature)." }] } }, 415),
    });
    renderApp(APP_PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Upload PDF" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Document category" }), "building_plan");
    await userEvent.upload(screen.getByLabelText("PDF file"), pdf("fake.pdf"));
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("File content is not a PDF");
    expect(screen.getByLabelText("PDF file")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("form", { name: "Upload document" })).toBeInTheDocument();
  });

  it("deletes only after explicit confirmation", async () => {
    let listed = [DOC, DUPLICATE];
    const api = mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS_PATH}`]: () => jsonResponse(page(listed)),
      [`DELETE /documents/${DUPLICATE.id}`]: () => {
        listed = [DOC];
        return new Response(null, { status: 204 });
      },
    });
    renderApp(APP_PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Delete fire-safety-copy.pdf" }));
    const dialog = screen.getByRole("dialog", { name: "Delete document?" });
    expect(dialog).toHaveTextContent("Delete “fire-safety-copy.pdf”?");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog", { name: "Delete document?" })).not.toBeInTheDocument();
    expect(api.callsTo("DELETE", `/documents/${DUPLICATE.id}`)).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "Delete fire-safety-copy.pdf" }));
    await userEvent.click(within(screen.getByRole("dialog", { name: "Delete document?" })).getByRole("button", { name: "Confirm delete" }));
    expect((await screen.findAllByText("Deleted “fire-safety-copy.pdf”.")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("dialog", { name: "Delete document?" })).not.toBeInTheDocument();
    await waitFor(() => expect(within(screen.getByRole("table", { name: /Documents for/ })).getAllByRole("row")).toHaveLength(2));
    expect(screen.getByRole("table", { name: /Documents for/ })).toHaveTextContent("fire-safety.pdf");
    expect(api.callsTo("DELETE", `/documents/${DUPLICATE.id}`)).toHaveLength(1);
  });

  it("shows a deletion failure and keeps the document", async () => {
    mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse(DRAFT),
      [`GET ${DOCS_PATH}`]: () => jsonResponse(page([DOC])),
      [`DELETE /documents/${DOC.id}`]: () =>
        jsonResponse({ error: { code: "document_intake_closed", message: "Documents can only be removed while the application is a draft or awaiting additional evidence.", request_id: "r" } }, 409),
    });
    renderApp(APP_PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Delete fire-safety.pdf" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Documents can only be removed");
    expect(await docsTable()).toHaveTextContent("fire-safety.pdf");
  });

  it("hides upload and delete when intake is closed", async () => {
    mockApi({
      [`GET ${APP_PATH}`]: () => jsonResponse({ ...DRAFT, status: "under_preliminary_scrutiny", is_editable: false,
        document_intake_open: false, allowed_transitions: [] }),
      [`GET ${DOCS_PATH}`]: () => jsonResponse(page([DOC])),
    });
    renderApp(APP_PATH);
    expect(await docsTable()).toHaveTextContent("fire-safety.pdf");
    expect(screen.getByText(/documents can be added or removed only while/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload PDF" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Delete / })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open fire-safety.pdf" })).toBeInTheDocument();
  });
});

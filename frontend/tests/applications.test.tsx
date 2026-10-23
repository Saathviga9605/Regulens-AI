import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Application } from "../src/types/api";
import { DRAFT, INSTITUTION, LIST_ITEM, jsonResponse, mockApi, page, renderApp } from "./helpers";

describe("Applications list", () => {
  it("shows a loading state, then rows from the API", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    mockApi({ "GET /applications": async () => (await gate, jsonResponse(page([LIST_ITEM]))) });
    renderApp("/applications");

    expect(screen.getByText("Loading applications…")).toBeInTheDocument();
    release();

    const table = await screen.findByRole("table", { name: "Applications" });
    const row = within(table).getAllByRole("row")[1]!;
    expect(within(row).getByRole("link", { name: "REG-EoA-2026-0001" })).toHaveAttribute("href", "/applications/REG-EoA-2026-0001");
    expect(row).toHaveTextContent("Deccan Ridge Institute of Engineering");
    expect(row).toHaveTextContent("INST-00001");
    expect(row).toHaveTextContent("2026-27");
    expect(row).toHaveTextContent("EoA — no change");
    expect(row).toHaveTextContent("Draft");
    expect(screen.getByRole("link", { name: /new application/i })).toHaveAttribute("href", "/applications/new");
  });

  it("shows an empty state", async () => {
    mockApi({ "GET /applications": () => jsonResponse(page([])) });
    renderApp("/applications");
    expect(await screen.findByText(/no applications have been created yet/i)).toBeInTheDocument();
  });

  it("shows an error state with retry", async () => {
    let fail = true;
    const api = mockApi({
      "GET /applications": () =>
        fail
          ? jsonResponse({ error: { code: "internal_error", message: "An unexpected error occurred.", request_id: "x" } }, 500)
          : jsonResponse(page([LIST_ITEM])),
    });
    renderApp("/applications");

    expect(await screen.findByText("An unexpected error occurred.")).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByRole("link", { name: "REG-EoA-2026-0001" })).toBeInTheDocument();
    expect(api.callsTo("GET", "/applications")).toHaveLength(2);
  });

  it("sends search and filters to the server", async () => {
    const api = mockApi({ "GET /applications": () => jsonResponse(page([LIST_ITEM])) });
    renderApp("/applications");
    await screen.findByRole("link", { name: "REG-EoA-2026-0001" });

    await userEvent.type(screen.getByRole("searchbox", { name: "Search" }), "deccan");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(api.calls.at(-1)?.params.get("q")).toBe("deccan"));

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Status" }), "under_preliminary_scrutiny");
    await waitFor(() => expect(api.calls.at(-1)?.params.get("status")).toBe("under_preliminary_scrutiny"));
    expect(api.calls.at(-1)?.params.get("q")).toBe("deccan");

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Academic year" }), "2026-27");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Application type" }), "increase_in_intake");
    await waitFor(() => {
      const last = api.calls.at(-1)!.params;
      expect(last.get("academic_year")).toBe("2026-27");
      expect(last.get("application_type")).toBe("increase_in_intake");
    });
  });

  it("shows a filtered empty state", async () => {
    mockApi({ "GET /applications": () => jsonResponse(page([])) });
    renderApp("/applications?status=draft");
    expect(await screen.findByText(/no applications match/i)).toBeInTheDocument();
  });

  it("requests the next page", async () => {
    const api = mockApi({
      "GET /applications": () => jsonResponse(page([LIST_ITEM], { total: 25, total_pages: 2 })),
    });
    renderApp("/applications");
    await userEvent.click(await screen.findByRole("button", { name: /next/i }));
    await waitFor(() => expect(api.calls.at(-1)?.params.get("page")).toBe("2"));
  });
});

async function fillValidForm() {
  await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Institution" }), "INST-00001");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Academic year" }), "2026-27");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Application type" }), "eoa_no_change");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Level" }), "undergraduate");
  await userEvent.type(screen.getByRole("textbox", { name: "Course name" }), "B.Tech Civil Engineering");
  await userEvent.type(screen.getByRole("textbox", { name: "Existing intake" }), "60");
  await userEvent.type(screen.getByRole("textbox", { name: "Proposed intake" }), "60");
}

describe("Application creation", () => {
  it("validates required fields without calling the API", async () => {
    const api = mockApi({ "GET /institutions": () => jsonResponse(page([INSTITUTION])) });
    renderApp("/applications/new");
    await screen.findByRole("option", { name: /Deccan Ridge/ });

    await userEvent.type(screen.getByRole("textbox", { name: "Existing intake" }), "abc");
    await userEvent.click(screen.getByRole("button", { name: "Create draft application" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Please correct the highlighted fields.");
    expect(screen.getByText("Select an institution.")).toBeInTheDocument();
    expect(screen.getByText("Select an academic year.")).toBeInTheDocument();
    expect(screen.getByText("Select an application type.")).toBeInTheDocument();
    expect(screen.getByText("Enter the course name.")).toBeInTheDocument();
    expect(screen.getAllByText("Whole number from 0 to 600.")).toHaveLength(2);
    expect(screen.getByRole("combobox", { name: "Institution" })).toHaveAttribute("aria-invalid", "true");
    expect(api.callsTo("POST", "/applications")).toHaveLength(0);
  });

  it("creates through the API, shows the returned ID and navigates to the detail page", async () => {
    const created: Application = { ...DRAFT, application_code: "REG-EoA-2026-0042" };
    const api = mockApi({
      "GET /institutions": () => jsonResponse(page([INSTITUTION])),
      "POST /applications": () => jsonResponse(created, 201),
      "GET /applications/REG-EoA-2026-0042": () => jsonResponse(created),
    });
    renderApp("/applications/new");
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: "Create draft application" }));

    expect(await screen.findByRole("heading", { level: 1, name: "REG-EoA-2026-0042" })).toBeInTheDocument();
    expect(screen.getByText("Draft application REG-EoA-2026-0042 created.")).toBeInTheDocument();
    expect(api.callsTo("POST", "/applications")[0]!.body).toEqual({
      institution_code: "INST-00001",
      academic_year: "2026-27",
      application_type: "eoa_no_change",
      programmes: [
        { programme_level: "undergraduate", course_name: "B.Tech Civil Engineering", shift: "first", existing_intake: 60, proposed_intake: 60 },
      ],
    });
  });

  it("maps server field errors onto the form", async () => {
    mockApi({
      "GET /institutions": () => jsonResponse(page([INSTITUTION])),
      "POST /applications": () =>
        jsonResponse(
          {
            error: {
              code: "validation_error",
              message: "Proposed intake must equal existing intake for this application type.",
              request_id: "r",
              details: [{ loc: ["body", "programmes", "0", "proposed_intake"], msg: "Must equal existing intake." }],
            },
          },
          422,
        ),
    });
    renderApp("/applications/new");
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: "Create draft application" }));

    expect(await screen.findByText("Must equal existing intake.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/proposed intake must equal existing intake/i);
    expect(screen.getByRole("textbox", { name: "Proposed intake" })).toHaveAttribute("aria-invalid", "true");
  });

  it("preselects the institution from the query string", async () => {
    mockApi({ "GET /institutions": () => jsonResponse(page([INSTITUTION])) });
    renderApp("/applications/new?institution=INST-00001");
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Institution" })).toHaveValue("INST-00001"));
  });
});

describe("Application detail", () => {
  it("renders application, institution and status explanation with only backend-allowed actions", async () => {
    mockApi({ "GET /applications/REG-EoA-2026-0001": () => jsonResponse(DRAFT) });
    renderApp("/applications/REG-EoA-2026-0001");

    expect(await screen.findByRole("heading", { level: 1, name: "REG-EoA-2026-0001" })).toBeInTheDocument();
    expect(screen.getByText(/being prepared in regulens/i)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Declared programmes" })).toHaveTextContent("B.Tech Civil Engineering");
    expect(screen.getByRole("link", { name: "View institution" })).toHaveAttribute("href", "/institutions/INST-00001");
    expect(screen.getByRole("button", { name: "Mark ready for preliminary scrutiny" })).toBeInTheDocument();
    for (const name of [/start preliminary scrutiny/i, /complete preliminary scrutiny/i, /approve/i, /reject/i]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it("shows a not-found error", async () => {
    mockApi({
      "GET /applications/REG-EoA-2026-9999": () =>
        jsonResponse({ error: { code: "not_found", message: "Application 'REG-EoA-2026-9999' was not found.", request_id: "r" } }, 404),
    });
    renderApp("/applications/REG-EoA-2026-9999");
    expect(await screen.findByText("Application 'REG-EoA-2026-9999' was not found.")).toBeInTheDocument();
  });

  it("edits a draft through PATCH", async () => {
    const updated: Application = { ...DRAFT, academic_year: "2027-28", updated_at: "2026-10-23T11:00:00Z" };
    const api = mockApi({
      "GET /applications/REG-EoA-2026-0001": () => jsonResponse(DRAFT),
      "GET /institutions": () => jsonResponse(page([INSTITUTION])),
      "PATCH /applications/REG-EoA-2026-0001": () => jsonResponse(updated),
    });
    renderApp("/applications/REG-EoA-2026-0001");
    await userEvent.click(await screen.findByRole("button", { name: "Edit draft" }));

    const year = await screen.findByRole("combobox", { name: "Academic year" });
    expect(year).toHaveValue("2026-27");
    await userEvent.selectOptions(year, "2027-28");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Draft saved.")).toBeInTheDocument();
    expect(screen.getByText(/Academic year 2027-28/)).toBeInTheDocument();
    expect((api.callsTo("PATCH", "/applications/REG-EoA-2026-0001")[0]!.body as { academic_year: string }).academic_year).toBe("2027-28");
  });

  it("does not offer editing for a frozen application", async () => {
    mockApi({
      "GET /applications/REG-EoA-2026-0001": () =>
        jsonResponse({ ...DRAFT, status: "under_preliminary_scrutiny", is_editable: false,
          allowed_transitions: ["awaiting_additional_evidence", "preliminary_scrutiny_completed"] }),
    });
    renderApp("/applications/REG-EoA-2026-0001");
    expect(await screen.findByRole("button", { name: "Complete preliminary scrutiny" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit draft" })).not.toBeInTheDocument();
    expect(screen.getByText(/reviewer is carrying out internal preliminary scrutiny/i)).toBeInTheDocument();
  });

  it("changes status and shows a server rejection", async () => {
    const ready: Application = {
      ...DRAFT, status: "ready_for_preliminary_scrutiny", is_editable: false,
      allowed_transitions: ["draft", "under_preliminary_scrutiny"], submitted_at: "2026-10-23T12:00:00Z",
    };
    let reject = false;
    const api = mockApi({
      "GET /applications/REG-EoA-2026-0001": () => jsonResponse(DRAFT),
      "POST /applications/REG-EoA-2026-0001/status": () =>
        reject
          ? jsonResponse({ error: { code: "invalid_status_transition", message: "Cannot change status from 'ready_for_preliminary_scrutiny' to 'preliminary_scrutiny_completed'.", request_id: "r" } }, 409)
          : jsonResponse(ready),
    });
    renderApp("/applications/REG-EoA-2026-0001");
    await userEvent.click(await screen.findByRole("button", { name: "Mark ready for preliminary scrutiny" }));

    expect(await screen.findByText(/status changed to “ready for preliminary scrutiny”/i)).toBeInTheDocument();
    expect(api.callsTo("POST", "/applications/REG-EoA-2026-0001/status")[0]!.body).toEqual({ target_status: "ready_for_preliminary_scrutiny" });
    expect(screen.queryByRole("button", { name: "Edit draft" })).not.toBeInTheDocument();

    reject = true;
    await userEvent.click(screen.getByRole("button", { name: "Start preliminary scrutiny" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/cannot change status/i);
  });
});

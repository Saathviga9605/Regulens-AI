import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Institution } from "../src/types/api";
import { INSTITUTION, LIST_ITEM, jsonResponse, mockApi, page, renderApp } from "./helpers";

describe("Institutions", () => {
  it("lists institutions and searches server-side", async () => {
    const api = mockApi({ "GET /institutions": () => jsonResponse(page([INSTITUTION])) });
    renderApp("/institutions");

    const table = await screen.findByRole("table", { name: "Institutions" });
    expect(within(table).getByRole("link", { name: INSTITUTION.name })).toHaveAttribute("href", "/institutions/INST-00001");
    expect(table).toHaveTextContent("Pune, Maharashtra");

    await userEvent.type(screen.getByRole("searchbox", { name: "Search institutions" }), "INST-00001");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(api.calls.at(-1)?.params.get("q")).toBe("INST-00001"));
  });

  it("shows detail with linked applications", async () => {
    const api = mockApi({
      "GET /institutions/INST-00001": () => jsonResponse(INSTITUTION),
      "GET /applications": () => jsonResponse(page([LIST_ITEM])),
    });
    renderApp("/institutions/INST-00001");

    expect(await screen.findByRole("heading", { level: 1, name: INSTITUTION.name })).toBeInTheDocument();
    expect(screen.getByText(INSTITUTION.trust_name)).toBeInTheDocument();
    const apps = await screen.findByRole("table", { name: `Applications for ${INSTITUTION.name}` });
    expect(within(apps).getByRole("link", { name: "REG-EoA-2026-0001" })).toBeInTheDocument();
    expect(api.callsTo("GET", "/applications")[0]!.params.get("institution_code")).toBe("INST-00001");
    expect(screen.getByRole("link", { name: /new application/i })).toHaveAttribute("href", "/applications/new?institution=INST-00001");
  });

  it("validates and creates an institution, then opens it", async () => {
    const created: Institution = { ...INSTITUTION, institution_code: "INST-00009", name: "Test Synthetic College" };
    const api = mockApi({
      "POST /institutions": () => jsonResponse(created, 201),
      "GET /institutions/INST-00009": () => jsonResponse(created),
      "GET /applications": () => jsonResponse(page([])),
    });
    renderApp("/institutions/new");

    await userEvent.click(await screen.findByRole("button", { name: "Create institution" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Please correct the highlighted fields.");
    expect(screen.getByText("Official name must be 3–200 characters.")).toBeInTheDocument();
    expect(screen.getByText("Select an institution type.")).toBeInTheDocument();
    expect(api.callsTo("POST", "/institutions")).toHaveLength(0);

    await userEvent.type(screen.getByRole("textbox", { name: "Official name" }), "Test Synthetic College");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Institution type" }), "government");
    await userEvent.type(screen.getByRole("textbox", { name: "State" }), "Kerala");
    await userEvent.type(screen.getByRole("textbox", { name: "District" }), "Ernakulam");
    await userEvent.type(screen.getByRole("textbox", { name: "Address" }), "1 Synthetic Road, Kochi");
    await userEvent.type(screen.getByRole("textbox", { name: "Trust or sponsoring body" }), "Synthetic Trust");
    await userEvent.type(screen.getByRole("textbox", { name: "Property / survey identifier" }), "SYN-KL-1");
    await userEvent.click(screen.getByRole("button", { name: "Create institution" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Test Synthetic College" })).toBeInTheDocument();
    expect(screen.getByText("Institution INST-00009 created.")).toBeInTheDocument();
    expect(api.callsTo("POST", "/institutions")[0]!.body).toEqual({
      name: "Test Synthetic College",
      institution_type: "government",
      state: "Kerala",
      district: "Ernakulam",
      address: "1 Synthetic Road, Kochi",
      trust_name: "Synthetic Trust",
      property_identifier: "SYN-KL-1",
    });
  });

  it("edits an institution and surfaces API errors", async () => {
    let fail = true;
    const api = mockApi({
      "GET /institutions/INST-00001": () => jsonResponse(INSTITUTION),
      "GET /applications": () => jsonResponse(page([])),
      "PATCH /institutions/INST-00001": () =>
        fail
          ? jsonResponse({ error: { code: "validation_error", message: "Request validation failed.", request_id: "r",
              details: [{ loc: ["body", "district"], msg: "String should have at least 2 characters" }] } }, 422)
          : jsonResponse({ ...INSTITUTION, district: "Satara" }),
    });
    renderApp("/institutions/INST-00001");
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const district = screen.getByRole("textbox", { name: "District" });
    await userEvent.clear(district);
    await userEvent.type(district, "Satara");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("String should have at least 2 characters")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Request validation failed.");

    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Institution saved.")).toBeInTheDocument();
    expect(screen.getByText("Satara")).toBeInTheDocument();
    expect((api.callsTo("PATCH", "/institutions/INST-00001").at(-1)!.body as { district: string }).district).toBe("Satara");
  });
});

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { HealthResponse } from "../src/types/api";
import { HEALTHY, REVIEWER, jsonResponse, mockApi, renderApp } from "./helpers";

const DEGRADED: HealthResponse = {
  ...HEALTHY,
  status: "degraded",
  database: { status: "unavailable", detail: "Database connectivity check failed." },
};

function indicator() {
  return screen.getByTestId("connection-indicator");
}

/** Backend diagnostics live under Help → System status (not on the dashboard). */
async function openStatus() {
  renderApp("/help");
  await userEvent.click(await screen.findByRole("tab", { name: "System status" }));
}

describe("Dashboard", () => {
  it("renders the shell and navigation without repeated prototype notices", async () => {
    mockApi({});
    renderApp("/");

    expect(await screen.findByRole("heading", { level: 1, name: /Welcome,/ })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    for (const label of ["Review Queue", "Applications", "Institutions", "Alerts", "Scrutiny Rules", "Audit Trail", "Users"]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(within(nav).getByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Help & About" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Regulatory source" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Highest-priority applications" })).toBeInTheDocument();
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.queryByText(/decision support, not decision making/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Backend connected")).not.toBeInTheDocument();
    expect(screen.getAllByText(/independent decision-support software/)).toHaveLength(1);
    // a healthy connection shows no permanent indicator
    await expect.poll(() => screen.queryByTestId("connection-indicator")).toBeNull();
  });

  it("hides administrator navigation from reviewers", async () => {
    mockApi({});
    renderApp("/", { user: REVIEWER });
    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect(within(nav).queryByRole("link", { name: "Users" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Audit Trail" })).not.toBeInTheDocument();
    expect(screen.getByText(/demo\.reviewer · Reviewer/)).toBeInTheDocument();
  });

  it("shows a loading state while health is being fetched", async () => {
    let resolve!: (r: Response) => void;
    const gate = new Promise<Response>((r) => (resolve = r));
    mockApi({ "GET /health": () => gate });
    await openStatus();

    expect(await screen.findByText("Checking backend status…")).toBeInTheDocument();
    expect(indicator()).toHaveTextContent("Checking…");
    resolve(jsonResponse(HEALTHY));
    await screen.findByText("Backend connected");
  });

  it("shows Connected for a healthy backend response", async () => {
    const api = mockApi({});
    await openStatus();
    await screen.findByText("Backend connected");
    expect(screen.queryByTestId("connection-indicator")).not.toBeInTheDocument();
    expect(api.callsTo("GET", "/health").length).toBeGreaterThan(0);
  });

  it("shows Degraded when the API reports an unhealthy database", async () => {
    mockApi({ "GET /health": () => jsonResponse(DEGRADED) });
    await openStatus();
    await screen.findByText("Backend degraded");
    expect(indicator()).toHaveTextContent("Degraded");
    expect(screen.getByRole("alert")).toHaveTextContent("Database connectivity check failed.");
  });

  it("shows Disconnected with an error message when the backend is unreachable", async () => {
    mockApi({ "GET /health": () => Promise.reject(new TypeError("Failed to fetch")) });
    await openStatus();
    await screen.findByText("Backend unavailable");
    expect(indicator()).toHaveTextContent("Disconnected");
    expect(screen.getByRole("alert")).toHaveTextContent(/unable to reach the regulens api/i);
  });

  it("treats an HTTP error response as disconnected without crashing", async () => {
    mockApi({ "GET /health": () => jsonResponse({ error: { code: "internal_error", message: "An unexpected error occurred.", request_id: "x" } }, 500) });
    await openStatus();
    await screen.findByText("Backend unavailable");
    expect(screen.getByRole("alert")).toHaveTextContent("An unexpected error occurred.");
  });

  it("retry triggers a new health request and updates the status", async () => {
    let fail = true;
    const api = mockApi({ "GET /health": () => (fail ? Promise.reject(new TypeError("Failed to fetch")) : jsonResponse(HEALTHY)) });
    await openStatus();
    await screen.findByText("Backend unavailable");
    const before = api.callsTo("GET", "/health").length;
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    await screen.findByText("Backend connected");
    expect(api.callsTo("GET", "/health").length).toBe(before + 1);
  });
});

describe("Routing", () => {
  it("shows not found for unknown pages without fabricated data", async () => {
    mockApi({});
    renderApp("/does-not-exist");
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { App } from "../src/app/App";
import type { HealthResponse } from "../src/types/api";

const HEALTHY: HealthResponse = {
  app_name: "ReguLens AI",
  api_version: "v1",
  status: "ok",
  database: { status: "ok", detail: null },
};

const DEGRADED: HealthResponse = {
  ...HEALTHY,
  status: "degraded",
  database: { status: "unavailable", detail: "Database connectivity check failed." },
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

function indicator() {
  return screen.getByTestId("connection-indicator");
}

describe("Dashboard", () => {
  it("renders the shell, purpose statement and navigation", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(HEALTHY));
    renderApp();

    expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /decision support, not decision making/i })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    for (const label of ["Applications", "Review Queue", "Verification", "Reports", "Audit Trail"]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole("heading", { name: "Available in this release" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Planned modules" })).toBeInTheDocument();
    await screen.findByText("Backend connected");
  });

  it("shows a loading state while health is being fetched", async () => {
    let resolve!: (r: Response) => void;
    vi.spyOn(globalThis, "fetch").mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    renderApp();

    expect(screen.getByText("Checking backend status…")).toBeInTheDocument();
    expect(indicator()).toHaveTextContent("Checking…");

    resolve(jsonResponse(HEALTHY));
    await screen.findByText("Backend connected");
  });

  it("shows Connected for a healthy backend response", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(HEALTHY));
    renderApp();

    await screen.findByText("Backend connected");
    expect(indicator()).toHaveTextContent("Connected");
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/health$/);
  });

  it("shows Degraded when the API reports an unhealthy database", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(DEGRADED));
    renderApp();

    await screen.findByText("Backend degraded");
    expect(indicator()).toHaveTextContent("Degraded");
    expect(screen.getByRole("alert")).toHaveTextContent("Database connectivity check failed.");
  });

  it("shows Disconnected with an error message when the backend is unreachable", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    renderApp();

    await screen.findByText("Backend unavailable");
    expect(indicator()).toHaveTextContent("Disconnected");
    expect(screen.getByRole("alert")).toHaveTextContent(/unable to reach the regulens api/i);
  });

  it("treats an HTTP error response as disconnected without crashing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ error: { code: "internal_error", message: "An unexpected error occurred.", request_id: "x" } }, 500),
    );
    renderApp();

    await screen.findByText("Backend unavailable");
    expect(screen.getByRole("alert")).toHaveTextContent("An unexpected error occurred.");
  });

  it("retry triggers a new health request and updates the status", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse(HEALTHY));
    renderApp();

    await screen.findByText("Backend unavailable");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: /retry/i }));

    await screen.findByText("Backend connected");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("Module placeholders", () => {
  it("renders a clearly labelled placeholder with no fabricated data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(HEALTHY));
    renderApp("/verification");

    expect(screen.getByRole("heading", { level: 1, name: "Verification" })).toBeInTheDocument();
    expect(screen.getByText("Planned")).toBeInTheDocument();
    expect(screen.getByText(/this module is not implemented yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    await waitFor(() => expect(indicator()).toHaveTextContent("Connected"));
  });
});

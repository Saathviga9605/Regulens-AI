import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "../src/components/Toast";
import { ConfirmDialog, Dialog } from "../src/components/ui";
import type { SystemInfoResponse } from "../src/types/api";
import { REVIEWER, jsonResponse, mockApi, renderApp } from "./helpers";

const INFO: SystemInfoResponse = {
  app_name: "ReguLens AI", app_version: "0.6.0", api_version: "v1", environment: "development", demo_mode: true,
  database_backend: "sqlite", implemented_capabilities: [], planned_capabilities: [],
};

describe("Application shell", () => {
  it("shows the trust notice, environment badge and unread alert count", async () => {
    mockApi({
      "GET /system/info": () => jsonResponse(INFO),
      "GET /alerts": () => jsonResponse({ items: [], total: 0, page: 1, page_size: 5, total_pages: 1, unread_count: 3 }),
    });
    renderApp("/");
    expect(await screen.findByRole("note")).toHaveTextContent("Not an official AICTE decision.");
    expect(await screen.findByTestId("environment-badge")).toHaveTextContent("Local demo");
    expect(await screen.findByRole("link", { name: "Alerts, 3 unread" })).toBeInTheDocument();
  });

  it("opens and closes the mobile navigation drawer", async () => {
    mockApi({});
    renderApp("/", { user: REVIEWER });
    await userEvent.click(await screen.findByRole("button", { name: "Open navigation" }));
    const drawer = screen.getByRole("dialog", { name: "Navigation" });
    expect(within(drawer).getByRole("link", { name: "Review Queue" })).toBeInTheDocument();
    expect(within(drawer).queryByRole("link", { name: "Users" })).not.toBeInTheDocument(); // admin-only stays hidden
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    await userEvent.click(within(screen.getByRole("dialog", { name: "Navigation" })).getByRole("link", { name: "Alerts" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Alerts" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument(); // closes on navigation
  });

  it("renders the Help & About page with non-affiliation wording and keyboard tabs", async () => {
    mockApi({});
    renderApp("/help");
    expect(await screen.findByRole("heading", { level: 1, name: "Help & About" })).toBeInTheDocument();
    expect(screen.getByText(/not affiliated with or endorsed by any government body/)).toBeInTheDocument();
    const workflow = screen.getByRole("tab", { name: "Scrutiny workflow" });
    workflow.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Evidence & uncertainty" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("not evidence of wrongdoing");
  });
});

describe("Sign-in page", () => {
  it("marks the demo environment without revealing credentials and toggles password visibility", async () => {
    mockApi({ "GET /system/info": () => jsonResponse(INFO) });
    const { container } = renderApp("/", { signedIn: false });
    expect(await screen.findByTestId("demo-indicator")).toHaveTextContent("Local demo environment");
    expect(container.textContent).not.toMatch(/Reviewer@Demo|Admin@Demo/);
    const password = screen.getByLabelText(/^Password/);
    expect(password).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    await userEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
  });

  it("explains a temporary lockout", async () => {
    mockApi({
      "POST /auth/login": () => jsonResponse({ error: { code: "too_many_attempts", message: "Too many failed sign-in attempts. Try again later.", request_id: "r" } }, 429),
    });
    renderApp("/", { signedIn: false });
    await userEvent.type(await screen.findByLabelText(/^Username/), "demo.reviewer");
    await userEvent.type(screen.getByLabelText(/^Password/), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Temporarily locked");
    expect(alert).toHaveTextContent("Too many failed sign-in attempts");
  });
});

function DialogHarness({ onConfirm }: { onConfirm: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open</button>
      <ConfirmDialog open={open} title="Delete item?" confirmLabel="Delete" destructive busy={busy}
        onCancel={() => setOpen(false)}
        onConfirm={async () => { setBusy(true); await onConfirm(); setBusy(false); setOpen(false); }}>
        <p>This cannot be undone.</p>
      </ConfirmDialog>
    </>
  );
}

describe("Dialogs and toasts", () => {
  it("keeps focus in a text field while typing (inline onClose does not re-run the focus effect)", async () => {
    function Typing() {
      const [value, setValue] = useState("");
      return (
        <Dialog open title="Reason" onClose={() => undefined}>
          <label>Reason <textarea value={value} onChange={(e) => setValue(e.target.value)} /></label>
        </Dialog>
      );
    }
    render(<Typing />);
    const box = screen.getByRole("textbox", { name: "Reason" });
    await userEvent.click(box);
    await userEvent.type(box, "several words");
    expect(box).toHaveValue("several words");
    expect(box).toHaveFocus();
  });

  it("traps focus, closes on Escape and restores focus to the trigger", async () => {
    render(<DialogHarness onConfirm={async () => {}} />);
    const trigger = screen.getByRole("button", { name: "Open" });
    await userEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Delete item?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog.contains(document.activeElement)).toBe(true);
    for (let i = 0; i < 4; i++) {
      await userEvent.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("prevents a double submission while confirming", async () => {
    let release!: () => void;
    const onConfirm = vi.fn(() => new Promise<void>((r) => (release = r)));
    render(<DialogHarness onConfirm={onConfirm} />);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    const working = screen.getByRole("button", { name: "Working…" });
    expect(working).toBeDisabled();
    await userEvent.click(working);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    await act(async () => release());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("announces toasts politely", async () => {
    function Pusher() {
      const toast = useToast();
      return <button type="button" onClick={() => toast("Saved.")}>Save</button>;
    }
    render(<ToastProvider><Pusher /></ToastProvider>);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const region = screen.getByLabelText("Notifications");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveTextContent("Saved.");
  });
});

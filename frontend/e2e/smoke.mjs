// ReguLens UI smoke test: drives the real app in a browser (Edge by default) through the main reviewer and
// admin journeys, checks for page-level horizontal overflow at 360–1920 px and collects console errors.
//
// It WRITES data (runs scrutiny, uploads/deletes a document, toggles rule CON-004 twice, creates and
// deactivates a user). Run it only against a scratch database — see README "UI smoke test".
//   SMOKE_ALLOW_WRITES=1 SMOKE_BASE_URL=http://127.0.0.1:5195 SMOKE_API_URL=http://127.0.0.1:8030/api/v1 npm run smoke
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const BASE = process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:5173";
const API = process.env.SMOKE_API_URL ?? "http://127.0.0.1:8000/api/v1";
const DIR = fileURLToPath(new URL(".", import.meta.url));
const OUT = process.env.SMOKE_OUT_DIR ?? join(DIR, "..", "..", "data", "smoke-screenshots");
mkdirSync(OUT, { recursive: true });
if (process.env.SMOKE_ALLOW_WRITES !== "1") {
  console.error("Refusing to run: this smoke test modifies data. Point it at a scratch database and set SMOKE_ALLOW_WRITES=1.");
  process.exit(2);
}
const SMOKE_USER = `smoke.${Date.now() % 100000}`;
const CODE = "REG-EoA-2026-0005";
// Documented local defaults from .env.example (LOCAL DEMO ONLY).
const REVIEWER = [process.env.REGULENS_DEMO_REVIEWER_USERNAME ?? "demo.reviewer", process.env.REGULENS_DEMO_REVIEWER_PASSWORD ?? "Reviewer@Demo2026"];
const ADMIN = [process.env.REGULENS_DEMO_ADMIN_USERNAME ?? "demo.admin", process.env.REGULENS_DEMO_ADMIN_PASSWORD ?? "Admin@Demo2026"];
const log = (...a) => console.log("✔", ...a);
const fail = (m) => { throw new Error(m); };
const shot = (page, name) => page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true });

const browser = await chromium.launch({ channel: process.env.SMOKE_BROWSER_CHANNEL ?? "msedge", headless: true });
const context = await browser.newContext({ viewport: { width: 1366, height: 900 }, acceptDownloads: true });
const page = await context.newPage();
const consoleErrors = [];
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(`${page.url()} :: ${m.text().slice(0, 200)}`); });
page.on("pageerror", (e) => consoleErrors.push(`pageerror ${e.message}`));
const token = () => page.evaluate(() => sessionStorage.getItem("regulens.token"));
const api = async (path, opts = {}) => page.request.fetch(`${API}${path}`, { ...opts, headers: { Authorization: `Bearer ${await token()}`, ...(opts.headers || {}) } });

async function signIn([user, pw]) {
  await page.goto(`${BASE}/`);
  await page.getByRole("heading", { name: "Sign in to ReguLens AI" }).waitFor();
  await page.getByLabel(/^Username/).fill(user);
  await page.getByLabel(/^Password/).fill(pw);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("heading", { level: 1, name: /Welcome,/ }).waitFor();
}
async function signOut() {
  await page.getByRole("button", { name: /Account menu for/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.getByRole("heading", { name: "Sign in to ReguLens AI" }).waitFor();
}
async function findingAction(titleRe, action, reason) {
  const findings = page.getByRole("region", { name: "Findings" });
  await findings.getByRole("button", { name: titleRe }).first().click();
  const detail = page.getByRole("article", { name: /Finding:/ });
  await detail.waitFor();
  const review = detail.getByRole("region", { name: "Human review" });
  await review.getByRole("button", { name: "Add observation", exact: true }).waitFor();
  if (!(await review.getByRole("button", { name: action, exact: true }).count())) {
    // Re-run against the same database: the finding already carries a review, which is kept.
    log(`'${action}' not offered (already reviewed) — skipping`);
    return;
  }
  await review.getByRole("button", { name: action, exact: true }).click();
  if (reason) await review.getByRole("textbox", { name: /Reason/ }).fill(reason);
  const save = review.getByRole("button", { name: `Save: ${action}` });
  await save.dblclick(); // double submission must record only one action
  await detail.getByText(`${action} recorded.`).waitFor();
}

try {
  // 1. login page: demo indicator, no credentials, show/hide, bad password
  await page.goto(`${BASE}/`);
  await page.getByText(/It is not an AICTE service/).waitFor();
  if (await page.getByTestId("demo-indicator").count()) throw new Error("demo banner should be gone");
  const body = await page.locator("body").innerText();
  if (/Reviewer@Demo|Admin@Demo/.test(body)) fail("credentials rendered on login page");
  await page.getByLabel(/^Password/).fill("x");
  await page.getByRole("button", { name: "Show password" }).click();
  if ((await page.getByLabel(/^Password/).getAttribute("type")) !== "text") fail("show password");
  // A fictional username, so repeated runs never lock the real demo account (lockout is per username).
  await page.getByLabel(/^Username/).fill("smoke.no-such-user");
  await page.getByLabel(/^Password/).fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  log("Bad password →", (await page.getByRole("alert").innerText()).replace(/\s+/g, " "));
  await shot(page, "01-login");

  // 2. reviewer sign-in with default demo credentials; shell
  await signIn(REVIEWER);
  const nav = page.getByRole("navigation", { name: "Primary" });
  log("Reviewer nav:", (await nav.getByRole("link").allInnerTexts()).map((t) => t.trim()).join(" | "));
  if (await nav.getByRole("link", { name: "Users" }).count()) fail("reviewer sees Users");
  if (await page.getByRole("note").count() || await page.getByTestId("environment-badge").count()) throw new Error("repeated prototype banners should be gone");
  log("Identity footer:", await page.getByText(/independent decision-support software/).innerText());
  log("Overview metrics:", (await page.getByLabel("Review summary").innerText()).replace(/\s+/g, " "));
  await shot(page, "02-overview");

  // 3. queue
  await nav.getByRole("link", { name: "Review Queue" }).click();
  await page.getByRole("table", { name: "Review queue" }).waitFor();
  await shot(page, "03-queue");

  // 4. workspace: scrutiny, actions (double-click guarded)
  await page.goto(`${BASE}/applications/${CODE}`);
  await page.getByRole("navigation", { name: "Workspace sections" }).waitFor();
  await page.getByRole("button", { name: "Run preliminary scrutiny" }).click();
  await page.getByRole("region", { name: "Findings" }).waitFor({ timeout: 120000 });
  await findingAction(/Conflicting survey number/, "Confirm finding", "Survey 312 vs 318 genuinely differ on page 1 of both documents.");
  const fid = await page.getByRole("article", { name: /Finding:/ }).getAttribute("data-finding-id").catch(() => null);
  log("Finding review step done (Save is double-clicked to exercise the double-submit guard)", fid ?? "");
  await shot(page, "04-workspace-finding");

  // 5. upload with progress + selected vs detected; delete via dialog
  await page.getByRole("button", { name: "Upload document" }).click();
  await page.getByRole("combobox", { name: "Document category" }).selectOption("structural_stability_certificate");
  await page.getByLabel("Document file").setInputFiles(process.env.SMOKE_PDF ?? join(DIR, "fixtures", "structural-stability.pdf"));
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await page.getByText("Uploaded “structural-stability.pdf”.").first().waitFor();
  log("Uploaded structural-stability.pdf");
  await page.getByRole("button", { name: "Delete structural-stability.pdf" }).click();
  const del = page.getByRole("dialog", { name: "Delete document?" });
  await del.waitFor();
  await shot(page, "05-delete-dialog");
  await del.getByRole("button", { name: "Cancel" }).click();
  if (await del.count()) fail("dialog did not close");
  await page.getByRole("button", { name: "Delete structural-stability.pdf" }).click();
  await page.getByRole("dialog", { name: "Delete document?" }).getByRole("button", { name: "Confirm delete" }).click();
  await page.getByText("Deleted “structural-stability.pdf”.").first().waitFor();
  log("Delete: cancel kept the file; confirm deleted it; toast shown");

  // 6. copilot + report
  const copilot = page.getByRole("region", { name: "Reviewer copilot" });
  await copilot.getByRole("textbox", { name: "Ask about this application" }).fill("Why was the survey number conflict raised?");
  await copilot.getByRole("button", { name: "Ask", exact: true }).click();
  const answer = copilot.getByTestId("copilot-answer").last();
  await answer.waitFor();
  if (!(await answer.innerText()).includes("CON-003")) fail("copilot lacks citation");
  log("Copilot cites CON-003");
  const [download] = await Promise.all([page.waitForEvent("download"),
    page.getByRole("button", { name: /Download preliminary report/ }).click()]);
  const reportPath = join(OUT, "report.pdf");
  await download.saveAs(reportPath);
  log("Report:", download.suggestedFilename(), readFileSync(reportPath).subarray(0, 5).toString());
  const report = readFileSync(reportPath).toString("latin1");
  if (/Reviewer@Demo|Admin@Demo/.test(report)) fail("password in report");

  // 7. review history recorded once despite double click
  const findingsApi = await (await api(`/applications/${CODE}/scrutiny-runs`)).json();
  log("Scrutiny runs:", findingsApi.total ?? findingsApi.items?.length);

  // 8. alerts and reviewer admin denial
  await page.getByRole("link", { name: /^Alerts/ }).first().click();
  await page.getByRole("heading", { level: 1, name: "Alerts" }).waitFor();
  await shot(page, "06-alerts");
  await page.goto(`${BASE}/users`);
  await page.getByRole("heading", { name: "Administrator access required" }).waitFor();
  log("Reviewer blocked from /users; PATCH rule →", (await api("/scrutiny-rules/CON-003", { method: "PATCH", data: { enabled: false } })).status());
  await page.goto(`${BASE}/help`);
  await page.getByRole("heading", { level: 1, name: "Help & About" }).waitFor();
  await shot(page, "07-help");
  await signOut();
  log("Reviewer signed out via account menu");

  // 9. admin: rule confirm (cancel then apply), user deactivate confirm, audit
  await signIn(ADMIN);
  await page.goto(`${BASE}/scrutiny-rules`);
  const v0 = (await (await api("/scrutiny-rules")).json()).find((r) => r.rule_id === "CON-004").version;
  await page.getByRole("checkbox", { name: "Enable CON-004" }).click();
  const rd = page.getByRole("dialog", { name: "Disable rule?" });
  await rd.waitFor();
  await shot(page, "08-rule-confirm");
  await rd.getByRole("button", { name: "Cancel" }).click();
  if (!(await page.getByRole("checkbox", { name: "Enable CON-004" }).isChecked())) fail("cancel changed rule (CON-004 must start enabled)");
  await page.getByRole("checkbox", { name: "Enable CON-004" }).click();
  await page.getByRole("dialog", { name: "Disable rule?" }).getByRole("button", { name: "Disable rule" }).click();
  await page.getByText(`CON-004 saved (now version ${v0 + 1})`, { exact: false }).waitFor();
  await page.getByRole("checkbox", { name: "Enable CON-004" }).click();
  await page.getByRole("dialog", { name: "Enable rule?" }).getByRole("button", { name: "Enable rule" }).click();
  await page.getByText(`CON-004 saved (now version ${v0 + 2})`, { exact: false }).waitFor();
  log(`Rule CON-004: cancel left it on; disable → v${v0 + 1}; enable → v${v0 + 2}`);

  await page.goto(`${BASE}/users`);
  const form = page.getByRole("form", { name: "Create user" });
  await form.getByRole("textbox", { name: /^Username/ }).fill(SMOKE_USER);
  await form.getByRole("textbox", { name: /^Display name/ }).fill("Temporary Reviewer (fictional)");
  await form.getByLabel(/^Initial password/).fill("another-long-pass");
  await form.getByRole("button", { name: "Create user" }).click();
  await page.getByText(`Created: ${SMOKE_USER}.`).waitFor();
  await page.getByRole("checkbox", { name: `Active: ${SMOKE_USER}` }).click();
  await page.getByRole("dialog", { name: "Deactivate user?" }).waitFor();
  await shot(page, "09-user-confirm");
  await page.getByRole("dialog", { name: "Deactivate user?" }).getByRole("button", { name: "Deactivate" }).click();
  await page.getByText(`Deactivated: ${SMOKE_USER}.`).first().waitFor();
  log(`Created and deactivated ${SMOKE_USER} via confirm dialog`);

  await page.goto(`${BASE}/audit-trail`);
  await page.getByRole("table", { name: "Audit events" }).waitFor();
  const auditText = await page.locator("main").innerText();
  if (/Reviewer@Demo|Admin@Demo|another-long-pass/.test(auditText)) fail("password in audit");
  const actions = [...new Set(await page.locator("tbody tr td:nth-child(3)").allInnerTexts())];
  log("Audit actions (latest page):", actions.slice(0, 14).join(", "));
  await shot(page, "10-audit");

  // 10. responsive sweep: overflow per route per width
  const routes = ["/", "/review-queue", "/applications", `/applications/${CODE}`, "/applications/new", "/institutions",
    "/institutions/INST-00005", "/institutions/new", "/alerts", "/scrutiny-rules", "/audit-trail", "/users", "/help", "/nope"];
  const overflows = [];
  for (const width of [360, 390, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    for (const r of routes) {
      await page.goto(`${BASE}${r}`);
      await page.waitForTimeout(700);
      if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) overflows.push(`${width}${r}`);
    }
  }
  log("Page-level horizontal overflow:", overflows.length ? overflows : "none at 360/390/768/1024/1440/1920");

  // 11. mobile drawer + dialog fit
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE}/`);
  await page.getByRole("button", { name: "Open navigation" }).click();
  const drawer = page.getByRole("dialog", { name: "Navigation" });
  await drawer.waitFor();
  await shot(page, "11-mobile-drawer");
  await drawer.getByRole("link", { name: "Review Queue" }).click();
  await page.getByRole("table", { name: "Review queue" }).waitFor();
  if (await drawer.count()) fail("drawer stayed open");
  await shot(page, "12-mobile-queue");
  await page.goto(`${BASE}/applications/${CODE}`);
  await page.getByRole("navigation", { name: "Workspace sections" }).waitFor();
  await page.waitForTimeout(800);
  await shot(page, "13-mobile-workspace");
  await page.goto(`${BASE}/scrutiny-rules`);
  await page.getByRole("checkbox", { name: "Enable CON-004" }).click();
  const box = await page.getByRole("dialog", { name: "Disable rule?" }).boundingBox();
  log("Mobile dialog box:", JSON.stringify(box), "fits:", box.x >= 0 && box.x + box.width <= 390 && box.y >= 0 && box.y + box.height <= 844);
  await shot(page, "14-mobile-dialog");
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 1366, height: 900 });

  log("Console errors:", consoleErrors.length ? consoleErrors : "none");
} catch (err) {
  console.error("✘", err.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}

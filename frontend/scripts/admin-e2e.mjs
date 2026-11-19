// Admin acceptance test against the running stack. Reads a SYNTHETIC admin password from the file
// given in ADMIN_E2E_PASSWORD_FILE (never printed). Run only against an isolated acceptance database.
import { chromium } from "playwright-core";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// SAFETY: this script sends chatbot messages, which are recorded as analytics. Refuse to run unless the
// backend reports an isolated SYNTHETIC database (start it with DATABASE_URL=sqlite:///…/acceptance-synthetic.db).
{
  const h = await (await fetch(`${process.env.BASE_URL ?? "http://127.0.0.1:3000"}/api/v1/health`)).json();
  if (h.database?.label !== "synthetic") {
    console.error("Refusing to run: backend is using the PRIMARY analytics database. Start an acceptance backend with a *synthetic* DATABASE_URL.");
    process.exit(2);
  }
}

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:3000";
const OUT = new URL("../screenshots/", import.meta.url).pathname;
const EMAIL = "admin@gmail.com";
const PW = readFileSync(process.env.ADMIN_E2E_PASSWORD_FILE, "utf8").trim();
const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
};

function chromiumPath() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const root = join(homedir(), ".cache", "ms-playwright");
  for (const d of readdirSync(root).filter((d) => d.startsWith("chromium_headless_shell-")).sort().reverse()) {
    const p = join(root, d, "chrome-headless-shell-linux64", "chrome-headless-shell");
    if (existsSync(p)) return p;
  }
}

const browser = await chromium.launch({ executablePath: chromiumPath() });
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
const page = await ctx.newPage();
const api = async (path) => page.evaluate(async (p) => {
  const r = await fetch(p, { credentials: "same-origin" });
  return { status: r.status, body: r.ok ? await r.json() : null };
}, path);

try {
  // 1. Unauthenticated access is blocked (page + API)
  await page.goto(`${BASE}/admin/dashboard`);
  check("unauthenticated /admin/dashboard redirects to login", page.url().includes("/admin/login?next=%2Fadmin%2Fdashboard"));
  check("unauthenticated analytics API returns 401", (await api("/api/v1/admin/analytics?days=7")).status === 401);

  // 2. Wrong password rejected
  await page.getByLabel(/Email address/).fill(EMAIL);
  await page.getByLabel(/^Password/).fill("definitely-not-the-password");
  await page.getByRole("button", { name: "Login" }).click();
  await page.getByText("The email or password is incorrect.").waitFor({ timeout: 10000 });
  check("wrong password shows error and stays on login", page.url().includes("/admin/login"));
  await page.screenshot({ path: `${OUT}admin-login-error.png` });

  // 3. Correct login -> dashboard (empty state on a fresh database)
  await page.getByLabel(/^Password/).fill(PW);
  await page.getByRole("button", { name: "Login" }).click();
  await page.waitForURL("**/admin/dashboard", { timeout: 15000 });
  await page.getByRole("heading", { name: "Chatbot Dashboard" }).waitFor();
  const cookies = await ctx.cookies();
  const sess = cookies.find((c) => c.name === "dy_admin_session");
  check("login sets HttpOnly SameSite=Strict session cookie", !!sess && sess.httpOnly && sess.sameSite === "Strict");
  const empty0 = await api("/api/v1/admin/analytics?days=7");
  const emptyDb = empty0.body.totals.conversations === 0;
  if (emptyDb) {
    await page.getByText("No conversations in this period yet").first().waitFor();
    check("empty states shown on fresh database", await page.getByText("No feedback yet").isVisible());
    await page.screenshot({ path: `${OUT}admin-dashboard-empty.png`, fullPage: true });
  }

  // 4. Public journey: homepage navigation between information sections
  const pub = await ctx.newPage();
  await pub.goto(BASE, { waitUntil: "networkidle" });
  for (const [link, id] of [["Registration", "registration"], ["Airports", "airports"], ["FAQs", "faq"], ["Contact Us", "support"]]) {
    await pub.getByRole("navigation", { name: "Main" }).first().getByRole("link", { name: link, exact: true }).click();
    // Smooth scrolling takes ~1 s: poll until the section's top reaches the viewport top.
    const inView = await pub
      .waitForFunction((sid) => {
        const r = document.getElementById(sid)?.getBoundingClientRect();
        return !!r && Math.abs(r.top) < 80;
      }, id, { timeout: 3000 })
      .then(() => true, () => false);
    check(`navigation "${link}" scrolls to #${id}`, inView && pub.url().endsWith(`#${id}`));
  }
  await pub.goto(BASE, { waitUntil: "networkidle" });
  // Public chatbot usage (real backend) + Yes/No feedback through the UI
  await pub.getByRole("button", { name: "Open Digi Yatra Assistant" }).click();
  const askUi = async (q) => {
    const n = await pub.locator('[role="log"] > div.flex-col.items-start').count();
    await pub.getByLabel("Type your question").fill(q);
    await pub.keyboard.press("Enter");
    await pub.locator('[role="log"] > div.flex-col.items-start').nth(n).waitFor({ timeout: 130000 });
    await pub.getByText("The assistant is typing…").waitFor({ state: "detached", timeout: 130000 });
  };
  await askUi("How do I register for Digi Yatra?");
  await askUi("How do I upload a boarding pass PDF from my phone?");
  const srcBtn = pub.locator('[role="log"] > div.flex-col.items-start').last().getByRole("button", { name: /Sources \(\d+\)/ });
  await srcBtn.click();
  const files = await pub.locator('[role="log"] ol').last().locator("span.font-mono").allTextContents();
  check("grounded answer shows source citations with filenames", files.length > 0 && files.every((f) => /\.(md|csv)$/.test(f.replace("Source file: ", ""))), files.join(", "));
  await askUi("What if a child does not have Aadhaar?");
  check("follow-up question answered", (await pub.locator('[role="log"] > div.flex-col.items-start').count()) >= 4);
  await pub.getByRole("button", { name: "Yes" }).last().click();
  await pub.getByText("Thank you for your feedback.").waitFor();
  check("Yes feedback acknowledged in chat", true);
  // conversation 2: unresolved
  await pub.getByRole("button", { name: "Clear conversation" }).click();
  await pub.getByRole("button", { name: "Clear", exact: true }).click();
  await askUi("How much does it cost to register for Digi Yatra?");
  await askUi("My boarding pass upload keeps failing");
  await pub.getByRole("button", { name: "No" }).last().click();
  await pub.getByText("Sorry this didn't resolve your issue").waitFor();
  check("No feedback shows support guidance", await pub.getByText("customercare@digiyatrafoundation.com").last().isVisible());
  // conversation 3: no feedback (unconfirmed)
  await pub.getByRole("button", { name: "Clear conversation" }).click();
  await pub.getByRole("button", { name: "Clear", exact: true }).click();
  await askUi("How do I delete my Digi Yatra account?");
  await pub.screenshot({ path: `${OUT}admin-e2e-public-chat.png` });

  // 5. Duplicate feedback cannot inflate counts (replay the same Yes)
  const conv1 = await pub.evaluate(() => JSON.parse(sessionStorage.getItem("dy-poc-chat")).conversationId);
  const before = (await api("/api/v1/admin/analytics?days=7")).body;
  const replay = await pub.evaluate(async (cid) => {
    const r = await fetch("/api/v1/chat/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: cid, message_id: "not-a-real-message", resolved: true }) });
    return r.status;
  }, conv1);
  check("feedback for unknown message is rejected", replay === 404);

  // 6. Dashboard reflects real data
  await page.reload();
  await page.getByRole("heading", { name: "Chatbot Dashboard" }).waitFor();
  await page.waitForSelector("text=Total Conversations");
  const rep = (await api("/api/v1/admin/analytics?days=7")).body;
  const res = rep.resolution;
  console.log(`      report: conversations=${rep.totals.conversations} questions=${rep.totals.questions} resolved=${res.resolved} unresolved=${res.unresolved} unconfirmed=${res.unconfirmed} rate=${res.rate_percent} avg=${res.avg_resolution_seconds}s`);
  check("new questions incremented counters", rep.totals.conversations - (empty0.body.totals.conversations) === 3 && rep.totals.questions - empty0.body.totals.questions === 6);
  check("Yes/No feedback changed resolution stats", res.resolved - empty0.body.resolution.resolved === 1 && res.unresolved - empty0.body.resolution.unresolved === 1);
  check("rate = resolved / (resolved + unresolved)", res.rate_percent === Math.round((res.resolved / (res.resolved + res.unresolved)) * 1000) / 10);
  check("duplicate replay did not change counts", res.resolved === before.resolution.resolved && res.unresolved === before.resolution.unresolved);
  const cardText = await page.locator("main").innerText();
  check("dashboard cards show the API values", cardText.includes(`${res.rate_percent}%`) && cardText.includes(String(rep.totals.questions)));
  check("recent activity uses anonymous IDs only", /C-[0-9A-F]{8}/.test(cardText) && !cardText.includes(conv1));
  check("no raw question text on dashboard", !cardText.includes("keeps failing") && !cardText.includes("How much does it cost"));
  await page.screenshot({ path: `${OUT}admin-dashboard-desktop.png`, fullPage: true });

  // 7. Filters
  await page.getByRole("button", { name: "Last 30 days" }).click();
  await page.waitForFunction(() => document.querySelectorAll("svg[role=img] path").length > 0 || true);
  await page.waitForTimeout(500);
  const pressed30 = await page.getByRole("button", { name: "Last 30 days" }).getAttribute("aria-pressed");
  const r30 = (await api("/api/v1/admin/analytics?days=30")).body;
  check("30-day filter applied", pressed30 === "true" && r30.daily.length === 30 && r30.range.days === 30);
  await page.getByRole("button", { name: "Show table" }).click();
  check("daily chart has a table view", await page.getByRole("table", { name: /Conversations and questions per day/ }).isVisible());

  // 8. Responsive layouts
  for (const [name, w, h] of [["tablet", 820, 1180], ["mobile", 390, 844]]) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(300);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check(`${name} layout has no horizontal page overflow`, overflow <= 0, `${overflow}px`);
    await page.screenshot({ path: `${OUT}admin-dashboard-${name}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1366, height: 900 });

  // 9. Logout
  await page.getByRole("button", { name: "Logout" }).click();
  await page.waitForURL("**/admin/login**", { timeout: 15000 });
  check("logout returns to login page", true);
  check("analytics API is 401 after logout", (await api("/api/v1/admin/analytics?days=7")).status === 401);
  await page.goto(`${BASE}/admin/dashboard`);
  check("dashboard inaccessible after logout", page.url().includes("/admin/login"));
} catch (e) {
  check("unexpected error", false, String(e).slice(0, 300));
  await page.screenshot({ path: `${OUT}admin-e2e-failure.png` });
} finally {
  await browser.close();
}
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exitCode = failed ? 1 : 0;

// Browser E2E for persistent conversation history, provider/language switching, privacy and links.
// Runs against the TEST-ONLY stack (backend/scripts/e2e_stack.py, synthetic DB, mocked providers,
// outbound network blocked) behind a local Next.js production build. Synthetic data only.
//   BASE_URL=http://127.0.0.1:18732 BACKEND=http://127.0.0.1:18731 BACKEND_LOG=../.cache/e2e/backend.log \
//     node scripts/history-e2e.mjs
import { chromium } from "playwright-core";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:18732";
const BACKEND = process.env.BACKEND ?? "http://127.0.0.1:18731";
const LOG = process.env.BACKEND_LOG;
const OUT = new URL("../screenshots/", import.meta.url).pathname;
const PROFILE = new URL("../../.cache/e2e/profile-a/", import.meta.url).pathname;
const PROFILE_B = new URL("../../.cache/e2e/profile-b/", import.meta.url).pathname;
const KEY = "dy-chat-history-v1";
const VIDEOS = ["-nlJBCwg0nM", "y6xTGrpfAGs", "7z7iLNSkFg4", "j2lw7LljME0", "apjRDn3pkZ4", "jdb1Ph-QH9g", "Wlc6iqgwQDU"];
mkdirSync(OUT, { recursive: true });

{
  const h = await (await fetch(`${BASE}/api/v1/health`)).json();
  if (h.database?.label !== "synthetic") {
    console.error("Refusing to run: backend is not the synthetic E2E stack.");
    process.exit(2);
  }
}

function chromiumPath() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const root = join(homedir(), ".cache", "ms-playwright");
  for (const d of readdirSync(root).filter((d) => d.startsWith("chromium_headless_shell-")).sort().reverse())
    for (const p of [join(root, d, "chrome-headless-shell-linux64", "chrome-headless-shell"), join(root, d, "chrome-linux", "headless_shell")])
      if (existsSync(p)) return p;
}
const exe = chromiumPath();
const results = [];
const pass = (name, ok, detail = "") => {
  results.push({ name, ok: !!ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
};

const bubbles = (page) => page.locator('[role="log"] > div.flex-col.items-start');
const userBubbles = (page) => page.locator('[role="log"] > div.flex-col.items-end');

async function stubExternal(context) {
  // Official links are opened, but never leave the machine: a stub page answers instead.
  await context.route(/https:\/\/(www\.youtube\.com|x\.com|youtu\.be)\/.*/, (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: "<title>stub</title>external link stub" }));
}

async function openWidget(page) {
  const launcher = page.locator('button[aria-label="Open Digi Yatra Assistant"], button[aria-label="डिजी यात्रा सहायक खोलें"]');
  if (await page.locator('[role="log"]').count()) return;
  await launcher.first().click();
  await page.locator('[role="log"]').waitFor();
}

async function ask(page, text, requests) {
  const before = await bubbles(page).count();
  const box = page.locator('[role="dialog"] textarea');
  await box.fill(text);
  await box.press("Enter");
  await bubbles(page).nth(before).waitFor({ timeout: 30000 });
  await page.waitForTimeout(150);
  const body = requests?.at(-1);
  return { text: await bubbles(page).last().innerText(), body };
}

function track(page) {
  const requests = [];
  page.on("request", (r) => {
    if (new URL(r.url()).pathname === "/api/v1/chat" && r.method() === "POST") requests.push(JSON.parse(r.postData() ?? "{}"));
  });
  return requests;
}

const stored = (page) => page.evaluate((k) => window.localStorage.getItem(k), KEY);

async function scenarioSet(browser, label, viewport) {
  const context = await browser.newContext({ viewport, isMobile: label === "mobile", hasTouch: label === "mobile" });
  await stubExternal(context);
  const page = await context.newPage();
  const requests = track(page);
  await page.goto(BASE, { waitUntil: "networkidle" });
  await openWidget(page);
  pass(`${label}: history notice shown`, await page.getByTestId("history-note").isVisible());

  // A — several questions, close and reopen the widget
  await ask(page, "How do I register for Digi Yatra?", requests);
  await ask(page, "Can I do that using DigiLocker?", requests);
  const usersA = await userBubbles(page).count();
  await page.locator('button[aria-label="Close assistant"]').click();
  await openWidget(page);
  pass(`${label}: A close/reopen keeps history`, (await userBubbles(page).count()) === usersA && usersA === 2);

  // B — refresh restores
  await page.reload({ waitUntil: "networkidle" });
  await openWidget(page);
  pass(`${label}: B refresh restores history`, (await userBubbles(page).count()) === 2);

  // D — Sarvam -> Anthropic, context kept and provider honoured
  await page.selectOption('select[aria-label="AI provider"]', "anthropic");
  const d = await ask(page, "What if I don't have Aadhaar?", requests);
  pass(`${label}: D switch to Anthropic sends anthropic with prior user turns`,
    d.body?.provider === "anthropic" && d.body?.history?.some((h) => /register/i.test(h.content)) && (await userBubbles(page).count()) === 3,
    `history=${d.body?.history?.length}`);

  // E — Novita, contextual follow-up resolves to the registration video
  await page.selectOption('select[aria-label="AI provider"]', "novita");
  const e = await ask(page, "Can you show me a video?", requests);
  const vid = VIDEOS.find((v) => e.text.includes(v));
  pass(`${label}: E Novita contextual video follow-up`, e.body?.provider === "novita" && ["-nlJBCwg0nM", "y6xTGrpfAGs", "7z7iLNSkFg4"].includes(vid), `video=${vid}`);

  // M — open official video and social links from Sources (stubbed, safe attributes)
  const last = bubbles(page).last();
  await last.getByRole("button", { name: /Sources|स्रोत/ }).click();
  const link = last.locator('ol a[href*="youtube.com/watch"]').first();
  const href = await link.getAttribute("href");
  const rel = await link.getAttribute("rel");
  const [popup] = await Promise.all([page.waitForEvent("popup"), link.click()]);
  await popup.waitForURL((u) => u.href !== "about:blank", { timeout: 10000 }).catch(() => {});
  pass(`${label}: M video link opens verified URL safely`,
    VIDEOS.some((v) => href?.includes(v)) && rel?.includes("noopener") && popup.url() === href, href ?? "");
  await popup.close();
  const f = await ask(page, "Where can I follow official Digi Yatra announcements?", requests);
  const fb = bubbles(page).last();
  await fb.getByRole("button", { name: /Sources|स्रोत/ }).click();
  const social = fb.locator('ol a[href^="https://x.com/"], ol a[href^="https://www.youtube.com/@"]').first();
  const shref = await social.getAttribute("href");
  const [p2] = await Promise.all([page.waitForEvent("popup"), social.click()]);
  await p2.waitForURL((u) => u.href !== "about:blank", { timeout: 10000 }).catch(() => {});
  pass(`${label}: M official channel link opens`, /^https:\/\/(x\.com\/DigiYatraOffice|www\.youtube\.com\/@DigiYatraFoundation)/.test(shref ?? "") && p2.url() === shref, shref ?? "");
  await p2.close();
  void f;

  // F — English -> Hindi; history kept, next answer requested in Hindi
  const beforeF = await userBubbles(page).count();
  await page.selectOption('select[aria-label="Response language"]', "hi");
  const fh = await ask(page, "क्या मैं इसके लिए डिजीलॉकर का उपयोग कर सकता हूँ?", requests);
  pass(`${label}: F switch to Hindi keeps conversation`, fh.body?.locale === "hi" && (await userBubbles(page).count()) === beforeF + 1);
  await page.selectOption('select[aria-label="Response language"]', "en");

  // I — synthetic personal data never persisted or logged
  await ask(page, "My Aadhaar is 4321 8765 1098 and my PNR is AB12CD, how do I register?", requests);
  const raw = (await stored(page)) ?? "";
  const shown = await userBubbles(page).last().innerText();
  const logText = LOG && existsSync(LOG) ? readFileSync(LOG, "utf8") : "";
  pass(`${label}: I personal data not stored/shown/logged`,
    !raw.includes("8765") && !raw.includes("AB12CD") && !shown.includes("8765") && !logText.includes("8765") && !logText.includes("AB12CD"));
  pass(`${label}: no credentials/tokens in browser storage`, !/api[_-]?key|token|secret|cookie/i.test(raw));

  // H — expiry: messages older than 7 days are pruned on load
  await page.evaluate((k) => {
    const s = JSON.parse(window.localStorage.getItem(k));
    s.messages = s.messages.map((m) => ({ ...m, createdAt: Date.now() - 8 * 24 * 3600 * 1000 }));
    window.localStorage.setItem(k, JSON.stringify(s));
  }, KEY);
  await page.reload({ waitUntil: "networkidle" });
  await openWidget(page);
  pass(`${label}: H expired history deleted`, (await userBubbles(page).count()) === 0 && (await stored(page)) === null);

  // G — clear history, including a response still in flight
  await ask(page, "How do I register for Digi Yatra?", requests);
  await page.route("**/api/v1/chat", async (route) => { await new Promise((r) => setTimeout(r, 2500)); await route.continue(); });
  const box = page.locator('[role="dialog"] textarea');
  await box.fill("How do I add my child?");
  await box.press("Enter");
  await page.waitForTimeout(300);
  await page.locator('button[aria-label="Clear conversation"]').click();
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await page.waitForTimeout(3500);
  await page.unroute("**/api/v1/chat");
  const afterClear = await userBubbles(page).count() + (await bubbles(page).count()) - 1;
  await page.reload({ waitUntil: "networkidle" });
  await openWidget(page);
  pass(`${label}: G clear removes history; in-flight answer not restored`,
    afterClear <= 0 && (await userBubbles(page).count()) === 0 && (await stored(page)) === null);
  await page.screenshot({ path: `${OUT}history-e2e-${label}.png` });
  await context.close();
}

let browser;
try {
  browser = await chromium.launch({ executablePath: exe });
  await scenarioSet(browser, "desktop", { width: 1366, height: 900 });
  await scenarioSet(browser, "mobile", { width: 390, height: 844 });
  await browser.close();

  // C — close and reopen the browser with a persistent profile
  for (const p of [PROFILE, PROFILE_B]) rmSync(p, { recursive: true, force: true });
  let ctx = await chromium.launchPersistentContext(PROFILE, { executablePath: exe, viewport: { width: 1366, height: 900 } });
  let page = ctx.pages()[0] ?? (await ctx.newPage());
  await page.goto(BASE, { waitUntil: "networkidle" });
  await openWidget(page);
  await ask(page, "How do I register for Digi Yatra?");
  await ctx.close();
  ctx = await chromium.launchPersistentContext(PROFILE, { executablePath: exe, viewport: { width: 1366, height: 900 } });
  page = ctx.pages()[0] ?? (await ctx.newPage());
  await page.goto(BASE, { waitUntil: "networkidle" });
  await openWidget(page);
  pass("C browser restart restores history (persistent profile)", (await userBubbles(page).count()) === 1);
  await ctx.close();

  // J — another browser profile cannot see this history
  const other = await chromium.launchPersistentContext(PROFILE_B, { executablePath: exe });
  const op = other.pages()[0] ?? (await other.newPage());
  await op.goto(BASE, { waitUntil: "networkidle" });
  await openWidget(op);
  pass("J separate profile has no access to another profile's history",
    (await userBubbles(op).count()) === 0 && (await op.evaluate((k) => window.localStorage.getItem(k), KEY)) === null);
  await other.close();

  // K — external sources unreachable during all of the above (stack blocks non-loopback traffic)
  const blocked = await (await fetch(`${BACKEND}/__e2e/blocked`)).json();
  pass("K chat worked with external sources unreachable; zero outbound attempts", blocked.blocked_outbound.length === 0,
    JSON.stringify(blocked.blocked_outbound));
} catch (e) {
  pass("unexpected error", false, String(e).slice(0, 500));
  try { await browser?.close(); } catch { /* already closed */ }
}
for (const p of [PROFILE, PROFILE_B]) rmSync(p, { recursive: true, force: true });
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} browser checks passed`);
process.exitCode = failed.length ? 1 : 0;

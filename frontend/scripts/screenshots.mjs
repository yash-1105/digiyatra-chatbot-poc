// Captures the rendered site at desktop / tablet / mobile widths and exercises
// key interactions (chat, tabs, contrast). Uses an already-installed Chromium;
// set CHROMIUM_PATH to override. Output: frontend/screenshots/
import { chromium } from "playwright-core";
import { existsSync, mkdirSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:3000";
const OUT = new URL("../screenshots/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

function findChromium() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const root = join(homedir(), ".cache", "ms-playwright");
  if (!existsSync(root)) return undefined;
  const dirs = readdirSync(root).filter((d) => d.startsWith("chromium_headless_shell-")).sort().reverse();
  for (const d of dirs) {
    const p = join(root, d, "chrome-linux", "headless_shell");
    if (existsSync(p)) return p;
    const p2 = join(root, d, "chrome-headless-shell-linux64", "chrome-headless-shell");
    if (existsSync(p2)) return p2;
  }
  return undefined;
}

const viewports = [
  { name: "desktop", width: 1920, height: 957 },
  { name: "laptop", width: 1366, height: 768 },
  { name: "tablet", width: 820, height: 1180 },
  { name: "mobile", width: 390, height: 844 },
];

const browser = await chromium.launch({ executablePath: findChromium() });
const errors = [];
try {
  for (const vp of viewports) {
    const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
    page.on("pageerror", (e) => errors.push(`[${vp.name}] ${e.message}`));
    page.on("console", (m) => m.type() === "error" && errors.push(`[${vp.name}] console: ${m.text()}`));
    await page.goto(BASE, { waitUntil: "networkidle" });
    await page.screenshot({ path: `${OUT}${vp.name}-fold.png` });
    await page.screenshot({ path: `${OUT}${vp.name}-full.png`, fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (overflow > 0) errors.push(`[${vp.name}] horizontal overflow ${overflow}px`);

    // Chat panel layout only — no message is sent (sending would record analytics; see chat-e2e.mjs).
    await page.getByRole("button", { name: "Open Digi Yatra Assistant" }).click();
    await page.getByText("Suggested questions").waitFor({ timeout: 5000 });
    await page.screenshot({ path: `${OUT}${vp.name}-chat.png` });
    await page.keyboard.press("Escape");
    await page.close();
  }

  // Interactions on desktop: high contrast + Hindi + error state + admin login.
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "High contrast" }).click();
  await page.getByRole("button", { name: /View in Hindi/ }).click();
  await page.screenshot({ path: `${OUT}contrast-hindi.png` });
  await page.getByRole("button", { name: /View in English/ }).click();
  await page.getByRole("button", { name: "Standard contrast" }).click();


  await page.goto(`${BASE}/admin/dashboard`, { waitUntil: "networkidle" });
  if (!page.url().includes("/admin/login")) errors.push("admin dashboard was NOT protected");
  await page.getByRole("button", { name: "Login" }).click();
  await page.screenshot({ path: `${OUT}admin-validation.png` });
  // Login error flow is covered by admin-e2e.mjs (needs a synthetic DB); no credentials are submitted here.
  await page.close();
} finally {
  await browser.close();
}

if (errors.length) {
  console.error("Issues found:\n" + errors.join("\n"));
  process.exitCode = 1;
} else {
  console.log(`Screenshots written to ${OUT}`);
}

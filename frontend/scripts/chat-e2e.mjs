// Browser E2E for the chat widget against the running stack (Next.js :3000 -> FastAPI :8000).
// Usage: node scripts/chat-e2e.mjs [label]   — screenshots go to screenshots/chat-e2e-<label>-*.png
// Works with the real Sarvam backend or the offline stub (backend/scripts/fake_sarvam_server.py).
import { chromium } from "playwright-core";
import { existsSync, mkdirSync, readdirSync } from "node:fs";
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
const LABEL = process.argv[2] ?? "run";
const QUESTIONS = (process.env.E2E_QUESTIONS ?? "How do I register for Digi Yatra?|What if I don't have Aadhaar?").split("|");
const OUT = new URL("../screenshots/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

function chromiumPath() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const root = join(homedir(), ".cache", "ms-playwright");
  for (const d of readdirSync(root).filter((d) => d.startsWith("chromium_headless_shell-")).sort().reverse()) {
    for (const p of [join(root, d, "chrome-headless-shell-linux64", "chrome-headless-shell"), join(root, d, "chrome-linux", "headless_shell")])
      if (existsSync(p)) return p;
  }
}

const browser = await chromium.launch({ executablePath: chromiumPath() });
const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
const failures = [];
const apiCalls = [];
page.on("request", (r) => r.url().includes("/api/v1/") && apiCalls.push(new URL(r.url()).origin + new URL(r.url()).pathname));
page.on("pageerror", (e) => failures.push(`pageerror: ${e.message}`));

async function lastAssistantText() {
  return page.locator('[role="log"] > div.flex-col.items-start').last().innerText();
}

try {
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Open Digi Yatra Assistant" }).click();
  if (await page.getByText("Development mock").count()) failures.push("mock banner visible in normal flow");

  for (const [i, q] of QUESTIONS.entries()) {
    await page.getByLabel("Type your question").fill(q);
    await page.keyboard.press("Enter");
    await page.locator('[role="log"] > div.flex-col.items-start').nth(i + 1).waitFor({ timeout: 130000 });
    await page.getByText("The assistant is typing…").waitFor({ state: "detached", timeout: 130000 });
    const text = await lastAssistantText();
    console.log(`\nQ${i + 1}: ${q}\nA${i + 1}: ${text.replace(/\n+/g, " | ").slice(0, 700)}`);
    const bubble = page.locator('[role="log"] > div.flex-col.items-start').last();
    const src = bubble.getByRole("button", { name: /Sources \(\d+\)/ });
    if (await bubble.getByRole("button", { name: /Sources \(\d+\)/ }).count()) {
      await src.click();
      const files = await page.locator('[role="log"] ol').last().locator("span.font-mono").allTextContents();
      console.log(`   sources: ${files.map((f) => f.replace("Source file: ", "")).join(", ")}`);
    } else console.log("   sources: (none)");
  }
  await page.screenshot({ path: `${OUT}chat-e2e-${LABEL}-answers.png` });

  if (process.env.E2E_ERROR === "1") {
    await page.getByLabel("Type your question").fill("How do I register? #fail");
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Retry" }).waitFor({ timeout: 30000 });
    console.log("\nerror state: Retry button shown with:", (await page.locator('[role="log"] [role="alert"]').last().innerText()).trim());
    await page.screenshot({ path: `${OUT}chat-e2e-${LABEL}-error.png` });
  }

  await page.getByRole("button", { name: "Clear conversation" }).click();
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await page.getByText("Suggested questions").waitFor({ timeout: 5000 });
  console.log("\nconversation restart: OK (suggested questions visible again)");
} catch (e) {
  failures.push(String(e));
  await page.screenshot({ path: `${OUT}chat-e2e-${LABEL}-failure.png` });
} finally {
  await browser.close();
}
const origins = [...new Set(apiCalls.map((u) => new URL(u).origin))];
console.log(`\nAPI calls went to: ${origins.join(", ")} (${apiCalls.length} calls)`);
if (origins.some((o) => o !== new URL(BASE).origin)) failures.push("browser called a non-same-origin API");
if (failures.length) {
  console.error("FAILURES:\n" + failures.join("\n"));
  process.exitCode = 1;
}

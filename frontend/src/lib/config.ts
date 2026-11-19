/**
 * Public runtime configuration. Only NEXT_PUBLIC_* values are readable in the
 * browser; never place secrets here.
 */
export type ChatMode = "mock" | "api";

/** Real FastAPI backend by default. "mock" is an explicit opt-in for UI work without a backend. */
function readChatMode(): ChatMode {
  if (process.env.NODE_ENV === "production") return "api"; // mocks can never ship
  return process.env.NEXT_PUBLIC_CHAT_MODE === "mock" ? "mock" : "api";
}

function readTimeout(): number {
  const parsed = Number(process.env.NEXT_PUBLIC_CHAT_TIMEOUT_MS);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 120_000;
}

export const publicConfig = {
  chatMode: readChatMode(),
  // Empty = same origin: the browser calls /api/v1/* on the Next.js server, which proxies to
  // FastAPI (see rewrites in next.config.ts). Only one port needs to be reachable.
  apiBaseUrl: (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/+$/, ""),
  chatTimeoutMs: readTimeout(),
} as const;

/** Official external resources referenced throughout the site. */
export const officialLinks = {
  website: "https://www.digiyatrafoundation.com/",
  news: "https://digiyatrafoundation.com/news/",
  contact: "https://digiyatrafoundation.com/contact-us/",
  privacyPolicy: "https://digiyatrafoundation.com/privacy-policy/",
  currentAirports: "https://digiyatrafoundation.com/digi-yatra-implementation-current/",
  upcomingAirports: "https://digiyatrafoundation.com/digi-yatra-implementation-upcoming/",
  playStore: "https://play.google.com/store/apps/details?id=org.digiyatra.org&hl=en_IN",
  appStore: "https://apps.apple.com/in/app/digi-yatra/id6479873321",
} as const;

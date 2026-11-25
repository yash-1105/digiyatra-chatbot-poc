/**
 * Browser-local conversation history (anonymous users; no accounts, no server archive).
 *
 * - Stored in localStorage on THIS browser/device only, for RETENTION_DAYS, bounded by
 *   MAX_MESSAGES / MAX_BYTES; expired messages are pruned on every load and save.
 * - Personal data is never persisted: user turns use the server's redaction when it detected
 *   personal data, plus a second, independent client-side redactor; any message that still looks
 *   like it carries an identifier after redaction is replaced by a placeholder instead of stored.
 * - No API keys, tokens or cookies are ever written here.
 */

export const STORAGE_KEY = "dy-chat-history-v1";
export const LEGACY_SESSION_KEY = "dy-poc-chat";
export const RETENTION_DAYS = 7;
export const RETENTION_MS = RETENTION_DAYS * 24 * 60 * 60 * 1000;
export const MAX_MESSAGES = 60;
export const MAX_BYTES = 150_000;
export const NOT_SAVED = "[Message not saved: it may contain personal information]";

const PATTERNS: [RegExp, string][] = [
  [/\b[\w.+-]+@[\w-]+\.[\w.-]+\b/g, "[email]"],
  [/\b(?:otp|one[- ]time (?:password|code)|verification code|ओटीपी)\D{0,12}\d{4,8}\b/gi, "[otp]"],
  [/\b(?:pnr|booking|reservation|ref(?:erence)?|बुकिंग)\W{0,6}(?:no\.?|number|code|id)?\W{0,4}[A-Z0-9]{5,8}\b/gi, "[booking reference]"],
  [/\b[A-PR-WYa-pr-wy][1-9]\d\s?\d{4}[1-9]\b/g, "[passport number]"],
  [/\b\d{4}[\s-]?\d{4}[\s-]?\d{4}(?:[\s-]?\d{4})?\b/g, "[id number]"], // Aadhaar (12) / VID (16)
  [/(?:\+?91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b/g, "[phone]"],
  [/\b(?:\d[ -]?){13,19}\b/g, "[card number]"],
  [/\b(?:password|passcode|pin|api[_ -]?key|token|secret)\b\s*[:=]?\s*\S{4,}/gi, "[credential]"],
];

export function redactSensitive(text: string): { text: string; redacted: boolean } {
  let out = text;
  for (const [re, label] of PATTERNS) out = out.replace(re, label);
  return { text: out, redacted: out !== text };
}

/** Residual identifiers after redaction: long digit runs or ID-like tokens => do not persist. */
export function stillSensitive(text: string): boolean {
  return /\d{6,}/.test(text.replace(/\s/g, "").replace(/\[[a-z ]+\]/g, "")) || /\b[A-Z]{5}\d{4}[A-Z]\b/.test(text);
}

export function persistable(content: string, serverRedacted?: string): string {
  const base = serverRedacted ?? content;
  const { text } = redactSensitive(base);
  return stillSensitive(text) ? NOT_SAVED : text;
}

export interface StoredMessageLike {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
}

export function prune<T extends StoredMessageLike>(messages: T[], now = Date.now()): T[] {
  return messages.filter((m) => now - m.createdAt <= RETENTION_MS && m.createdAt <= now + 60_000).slice(-MAX_MESSAGES);
}

export function validMessage(m: unknown): m is StoredMessageLike {
  if (typeof m !== "object" || m === null) return false;
  const r = m as Record<string, unknown>;
  return typeof r.id === "string" && r.id.length <= 80 && (r.role === "user" || r.role === "assistant") &&
    typeof r.content === "string" && r.content.length <= 8000 && typeof r.createdAt === "number" && Number.isFinite(r.createdAt);
}

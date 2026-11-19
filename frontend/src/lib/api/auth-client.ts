/**
 * Admin authentication client. Talks to FastAPI through the same-origin /api/v1 proxy.
 * Credentials are sent once over the login request; the session lives in an HttpOnly
 * cookie the page cannot read. Nothing secret is stored in the frontend.
 */
import { publicConfig } from "@/lib/config";
import { ADMIN_CSRF_COOKIE } from "@/lib/admin-session";

export interface LoginRequest {
  email: string;
  password: string;
}

export type LoginResult =
  | { ok: true }
  | { ok: false; reason: "invalid_credentials" | "locked" | "unavailable" | "network"; message: string };

const base = () => publicConfig.apiBaseUrl;

export async function loginAdmin(request: LoginRequest): Promise<LoginResult> {
  try {
    const res = await fetch(`${base()}/api/v1/admin/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(request),
    });
    if (res.ok) return { ok: true };
    if (res.status === 401) return { ok: false, reason: "invalid_credentials", message: "The email or password is incorrect." };
    if (res.status === 429)
      return { ok: false, reason: "locked", message: "Too many sign-in attempts. Please wait 15 minutes and try again." };
    return { ok: false, reason: "unavailable", message: "The login service is temporarily unavailable. Please try again later." };
  } catch {
    return { ok: false, reason: "network", message: "Unable to reach the login service. Check your connection." };
  }
}

/** Reads the (non-HttpOnly) CSRF cookie so it can be echoed in the X-CSRF-Token header. */
export function csrfToken(): string {
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${ADMIN_CSRF_COOKIE}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

export async function logoutAdmin(): Promise<void> {
  try {
    await fetch(`${base()}/api/v1/admin/auth/logout`, {
      method: "POST",
      headers: { "X-CSRF-Token": csrfToken() },
      credentials: "same-origin",
    });
  } catch {
    /* even if the request fails we leave the admin area; the session will expire server-side */
  }
}

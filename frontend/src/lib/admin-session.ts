/**
 * Server-side admin session validation (used by middleware and the protected layout).
 *
 * The browser only holds an opaque HttpOnly cookie; validity, expiry and revocation are
 * decided by FastAPI (`GET /api/v1/admin/session`). Any failure — missing cookie, expired
 * session, backend unreachable — is treated as "not signed in" (fail closed).
 */
export const ADMIN_SESSION_COOKIE = "dy_admin_session";
export const ADMIN_CSRF_COOKIE = "dy_admin_csrf";

const BACKEND_URL = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

export interface AdminIdentity {
  email: string;
  expiresAt: string;
}

export async function validateAdminSession(token: string | undefined): Promise<AdminIdentity | null> {
  if (!token || token.length > 200) return null;
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/admin/session`, {
      headers: {
        cookie: `${ADMIN_SESSION_COOKIE}=${encodeURIComponent(token)}`, accept: "application/json",
      },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { email?: unknown; expires_at?: unknown };
    if (typeof body.email !== "string") return null;
    return { email: body.email, expiresAt: typeof body.expires_at === "string" ? body.expires_at : "" };
  } catch {
    return null;
  }
}

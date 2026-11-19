import { NextResponse, type NextRequest } from "next/server";
import { createHash, timingSafeEqual } from "node:crypto";
import { ADMIN_SESSION_COOKIE, validateAdminSession } from "@/lib/admin-session";

/**
 * Protects every /admin route except the login page by validating the session with
 * the backend. Signed-in admins visiting /admin/login are sent to the dashboard.
 */
/**
 * Redirect on the SAME host the browser used (host-only cookies). Note: Next.js itself normalises 127.0.0.1
 * to "localhost" at ingress, so local unauthenticated bounces land on localhost (harmless; tunnels use localhost).
 */
function redirectTo(request: NextRequest, path: string): NextResponse {
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? request.nextUrl.host;
  const proto = (request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol).replace(/:$/, "").split(",")[0];
  // Only allow plain host[:port] values to avoid open redirects via a forged header.
  const safeHost = /^[a-z0-9.-]+(:\d+)?$/i.test(host) ? host : request.nextUrl.host;
  // Plain Response: NextResponse.redirect() would normalise 127.0.0.1 to "localhost" via NextURL.
  const location = `${proto === "https" ? "https" : "http"}://${safeHost}${path}`;
  return new NextResponse(null, { status: 307, headers: { Location: location } });
}

export async function middleware(request: NextRequest) {
  const stagingCredential = process.env.STAGING_BASIC_AUTH;
  if (process.env.NODE_ENV === "production" || stagingCredential) {
    if (!stagingCredential) {
      return new NextResponse("Staging access is not configured.", { status: 503 });
    }
    const digest = (value: string) => createHash("sha256").update(value).digest();
    if (!timingSafeEqual(digest(request.headers.get("authorization") ?? ""), digest(`Basic ${stagingCredential}`))) {
      return new NextResponse("Authorized staging access required.", {
        status: 401,
        headers: { "WWW-Authenticate": 'Basic realm="Digi Yatra staging", charset="UTF-8"', "Cache-Control": "no-store" },
      });
    }
  }
  const { pathname, search } = request.nextUrl;
  if (pathname !== "/admin" && !pathname.startsWith("/admin/")) return NextResponse.next();
  const token = request.cookies.get(ADMIN_SESSION_COOKIE)?.value;
  const isLogin = pathname === "/admin/login" || pathname.startsWith("/admin/login/");

  if (isLogin) {
    if (token && (await validateAdminSession(token))) {
      return redirectTo(request, "/admin/dashboard");
    }
    return NextResponse.next();
  }

  if (!(await validateAdminSession(token))) {
    return redirectTo(request, `/admin/login?next=${encodeURIComponent(`${pathname}${search}`)}`);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/:path*"],
  runtime: "nodejs",
};

import { NextResponse, type NextRequest } from "next/server";
import { createHmac } from "node:crypto";
import { isIP } from "node:net";
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
  const forwardRequest = () => {
    const headers = new Headers(request.headers);
    headers.delete("x-dy-client-ip");
    headers.delete("x-dy-client-signature");
    const ip = request.headers.get("x-vercel-forwarded-for") ?? "";
    const secret = process.env.PROXY_SHARED_SECRET;
    if (process.env.VERCEL === "1" && secret && isIP(ip)) {
      headers.set("x-dy-client-ip", ip);
      headers.set("x-dy-client-signature", createHmac("sha256", secret).update(ip).digest("hex"));
    }
    return NextResponse.next({ request: { headers } });
  };
  const { pathname, search } = request.nextUrl;
  if (pathname !== "/admin" && !pathname.startsWith("/admin/")) return forwardRequest();
  const token = request.cookies.get(ADMIN_SESSION_COOKIE)?.value;
  const isLogin = pathname === "/admin/login" || pathname.startsWith("/admin/login/");

  if (isLogin) {
    if (token && (await validateAdminSession(token))) {
      return redirectTo(request, "/admin/dashboard");
    }
    return forwardRequest();
  }

  if (!(await validateAdminSession(token))) {
    return redirectTo(request, `/admin/login?next=${encodeURIComponent(`${pathname}${search}`)}`);
  }
  return forwardRequest();
}

export const config = {
  matcher: ["/:path*"],
  runtime: "nodejs",
};

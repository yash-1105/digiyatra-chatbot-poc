import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { AdminHeader } from "@/components/admin/AdminHeader";
import { ADMIN_SESSION_COOKIE, validateAdminSession } from "@/lib/admin-session";

export const dynamic = "force-dynamic";

/** Server-side guard (defence in depth on top of middleware): validates the session with FastAPI. */
export default async function ProtectedAdminLayout({ children }: { children: React.ReactNode }) {
  const store = await cookies();
  const admin = await validateAdminSession(store.get(ADMIN_SESSION_COOKIE)?.value);
  if (!admin) redirect("/admin/login");

  return (
    <div className="min-h-screen bg-band">
      <a
        href="#main-content"
        className="sr-only z-[100] rounded bg-surface px-4 py-2 font-medium text-brand shadow-float focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Skip to main content
      </a>
      <AdminHeader email={admin.email} />
      <main id="main-content" tabIndex={-1} className="mx-auto max-w-[1440px] px-4 py-6 focus:outline-none sm:px-6 sm:py-8 lg:px-8">
        {children}
      </main>
    </div>
  );
}

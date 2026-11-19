import type { Metadata } from "next";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { LogoMark } from "@/components/brand/LogoMark";
import { AdminLoginForm } from "@/components/admin/AdminLoginForm";
import { PublicShell } from "@/components/layout/PublicShell";
import { Container } from "@/components/ui/Container";

export const metadata: Metadata = { title: "Admin Login" };

export default async function AdminLoginPage({ searchParams }: { searchParams: Promise<{ next?: string | string[] }> }) {
  const params = await searchParams;
  const next = typeof params.next === "string" ? params.next : undefined;

  return (
    <PublicShell withChat={false}>
      <div className="border-b border-line bg-band">
        <Container className="py-3 text-sm text-ink-muted">
          <Link href="/" className="text-brand hover:underline">Home</Link> <span aria-hidden="true">›</span> Admin Login
        </Container>
      </div>
      <div className="admin-login-surface bg-band py-16 sm:py-24">
        <Container>
          <div className="mx-auto grid max-w-4xl overflow-hidden rounded-3xl bg-surface shadow-card md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
            <div className="hidden flex-col justify-between bg-panel p-8 text-panel-ink md:flex">
              <div>
                <LogoMark wordmark title="" className="login-wordmark" />
                <ShieldCheck aria-hidden="true" className="mt-12 h-10 w-10 text-accent" />
                <h2 className="mt-4 text-xl font-semibold">Administration</h2>
                <p lang="hi" className="font-devanagari text-panel-ink/80">प्रशासन</p>
                <span aria-hidden="true" className="my-4 block h-0.5 w-10 bg-accent" />
                <p className="text-sm leading-relaxed text-panel-ink/90">
                  Manage the assistant&apos;s knowledge base, approved announcements and user feedback for the Digi Yatra
                  portal.
                </p>
              </div>
              <p className="text-xs leading-relaxed text-panel-ink/70">
                Access is restricted to authorised personnel. Activity may be logged for security purposes.
              </p>
            </div>
            <div className="p-6 sm:p-10">
              <h1 className="text-[1.75rem] font-semibold text-heading">Administrator Login</h1>
              <p lang="hi" className="font-devanagari text-sm text-ink-soft">व्यवस्थापक लॉगिन</p>
              <span aria-hidden="true" className="mb-6 mt-3 block h-[3px] w-14 rounded bg-accent" />
              <AdminLoginForm next={next} redirected={Boolean(next)} />
              <p className="mt-6 text-center text-sm">
                <Link href="/" className="text-brand hover:underline">← Back to homepage</Link>
              </p>
            </div>
          </div>
        </Container>
      </div>
    </PublicShell>
  );
}

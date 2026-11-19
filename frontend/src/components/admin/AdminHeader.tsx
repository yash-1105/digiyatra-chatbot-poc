import Link from "next/link";
import { ExternalLink, LayoutDashboard, UserRound } from "lucide-react";
import { LogoMark } from "@/components/brand/LogoMark";
import { LogoutButton } from "./LogoutButton";

/** Admin top navigation in the portal style: navy utility bar + white branding bar. */
export function AdminHeader({ email }: { email: string }) {
  return (
    <header className="admin-header">
      <div className="bg-navy text-white">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-3 px-4 py-1.5 text-xs sm:px-6 lg:px-8">
          <span className="font-semibold uppercase">
            <span lang="hi" className="font-devanagari normal-case">डिजी यात्रा प्रशासन</span> · Digi Yatra Administration
          </span>
          <span className="hidden items-center gap-1 text-white/80 sm:flex">
            <UserRound aria-hidden="true" className="h-3.5 w-3.5" />
            <span className="sr-only">Signed in as </span>
            {email}
          </span>
        </div>
      </div>
      <div className="border-b border-line bg-surface shadow-[0_2px_4px_rgb(0_0_0/0.06)]">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6 lg:px-8">
          <Link href="/admin/dashboard" className="flex items-center gap-3">
            <LogoMark wordmark className="admin-wordmark" title="" />
            <span className="leading-tight">
              <span className="block font-semibold text-white"><span className="hidden sm:inline">Digi Yatra </span>Administration</span>
              <span className="block text-xs font-medium text-white/65">
                Chatbot analytics
              </span>
            </span>
          </Link>
          <nav aria-label="Administration" className="ml-auto">
            <ul className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[0.95rem] text-white">
              <li>
                <Link href="/admin/dashboard" aria-current="page" className="flex items-center gap-1.5 font-medium text-brand">
                  <LayoutDashboard aria-hidden="true" className="h-4 w-4" /> Dashboard
                </Link>
              </li>
              <li>
                <Link href="/" className="flex items-center gap-1.5 text-brand hover:underline">
                  <ExternalLink aria-hidden="true" className="h-4 w-4" /> Return to Website
                </Link>
              </li>
              <li>
                <LogoutButton />
              </li>
            </ul>
          </nav>
        </div>
      </div>
    </header>
  );
}

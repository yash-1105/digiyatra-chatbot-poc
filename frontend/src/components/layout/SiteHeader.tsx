"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Home, LockKeyhole, Menu, X } from "lucide-react";
import { LogoMark } from "@/components/brand/LogoMark";
import { usePreferences } from "@/lib/accessibility/preferences";
import { mainNav, topLinks } from "@/lib/navigation";

/**
 * White organisation-branding header: logo + bilingual name on the left;
 * on the right a small pipe-separated link row, a red notice line and the
 * blue main navigation (home icon first), exactly like the DGCA layout.
 */
export function SiteHeader() {
  const { t } = usePreferences();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <header className="border-b border-line bg-surface shadow-[0_2px_4px_rgb(0_0_0/0.06)]">
      <div className="mx-auto flex max-w-[1440px] items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
        {/* Branding */}
        <Link href="/" className="flex shrink-0 items-center gap-3" aria-label="Digi Yatra Information Portal (POC) — Home">
          <LogoMark className="h-12 w-12 sm:h-14 sm:w-14" title="" />
          <span className="leading-tight">
            <span className="block font-devanagari text-[1.05rem] font-bold text-ink">डिजी यात्रा सूचना पोर्टल</span>
            <span className="block text-[0.95rem] font-bold uppercase text-ink">Digi Yatra</span>
            <span className="block text-[0.78rem] font-semibold uppercase text-ink-muted">
              Information Portal · <span className="text-accent">POC</span>
            </span>
          </span>
        </Link>

        <div className="ml-auto hidden min-w-0 flex-col items-end gap-1 xl:flex">
          {/* Top link row */}
          <ul className="pipe-list flex items-center text-[0.9rem] text-ink-muted">
            {topLinks.map((l) => (
              <li key={l.key}>
                <Link href={l.href} className="hover:text-brand">
                  {t(l.key)}
                </Link>
              </li>
            ))}
            <li>
              <Link href="/admin/login" className="inline-flex items-center gap-1 hover:text-brand">
                <LockKeyhole aria-hidden="true" className="h-3.5 w-3.5" />
                {t("adminLogin")}
              </Link>
            </li>
          </ul>
          {/* Red notice line (POC disclaimer), like DGCA's red ticker */}
          <p className="max-w-[52rem] truncate text-[0.78rem] font-semibold text-alert" title={t("tickerText")}>
            {t("tickerText")}
          </p>
          {/* Main navigation */}
          <nav aria-label="Main" className="mt-1">
            <ul className="flex flex-nowrap items-center justify-end gap-x-6 text-[1.02rem]">
              <li>
                <Link href="/" className="text-brand hover:text-brand-strong" aria-label={t("home")}>
                  <Home aria-hidden="true" className="h-6 w-6" />
                </Link>
              </li>
              {mainNav.map((item) => (
                <li key={item.key}>
                  <Link href={item.href} className="whitespace-nowrap text-brand hover:text-brand-strong hover:underline">
                    {t(item.short ?? item.key)}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>

        {/* Mobile / tablet menu button */}
        <button
          ref={menuButtonRef}
          type="button"
          className="ml-auto flex items-center gap-2 rounded border border-line px-3 py-2 text-brand xl:hidden"
          aria-expanded={menuOpen}
          aria-controls="mobile-nav"
          onClick={() => setMenuOpen((o) => !o)}
        >
          {menuOpen ? <X aria-hidden="true" className="h-5 w-5" /> : <Menu aria-hidden="true" className="h-5 w-5" />}
          <span className="text-sm font-medium">{menuOpen ? t("closeMenu") : t("menu")}</span>
        </button>
      </div>

      {/* Mobile notice line */}
      <p className="border-t border-line-soft px-4 py-1.5 text-center text-[0.75rem] font-semibold text-alert xl:hidden">
        {t("tickerShort")}
      </p>

      {/* Mobile navigation drawer */}
      <nav
        id="mobile-nav"
        aria-label="Main"
        hidden={!menuOpen}
        className="border-t border-line bg-surface xl:hidden"
      >
        <ul className="mx-auto grid max-w-[1440px] divide-y divide-line-soft px-4 sm:grid-cols-2 sm:gap-x-8 sm:divide-y-0 sm:px-6 sm:py-2">
          <li>
            <Link href="/" onClick={() => setMenuOpen(false)} className="flex items-center gap-2 py-3 text-brand">
              <Home aria-hidden="true" className="h-5 w-5" /> {t("home")}
            </Link>
          </li>
          {mainNav.map((item) => (
            <li key={item.key}>
              <Link href={item.href} onClick={() => setMenuOpen(false)} className="block py-3 text-brand">
                {t(item.key)}
              </Link>
            </li>
          ))}
          <li>
            <Link href="/accessibility" onClick={() => setMenuOpen(false)} className="block py-3 text-ink-muted">
              {t("accessibility")}
            </Link>
          </li>
          <li>
            <Link href="/admin/login" onClick={() => setMenuOpen(false)} className="flex items-center gap-2 py-3 text-ink-muted">
              <LockKeyhole aria-hidden="true" className="h-4 w-4" /> {t("adminLogin")}
            </Link>
          </li>
        </ul>
      </nav>
    </header>
  );
}

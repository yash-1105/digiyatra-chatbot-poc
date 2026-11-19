"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, LockKeyhole, Menu, X } from "lucide-react";
import { LogoMark } from "@/components/brand/LogoMark";
import { usePreferences } from "@/lib/accessibility/preferences";
import { mainNav, topLinks } from "@/lib/navigation";

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
    <header className="site-header">
      <div className="header-inner">
        <Link href="/" className="header-identity" aria-label="Digi Yatra Information Portal — Home">
          <LogoMark wordmark className="header-wordmark" title="" />
          <span className="brand-caption">Independent information portal</span>
        </Link>
        <nav aria-label="Main" className="hidden min-w-0 flex-1 xl:block">
          <ul className="header-links">
            {mainNav.map((item) => (
              <li key={item.key}><Link href={item.href}>{t(item.short ?? item.key)}</Link></li>
            ))}
          </ul>
        </nav>
        <Link href="/#registration" className="header-download hidden sm:inline-flex">Download The App <ArrowUpRight aria-hidden="true" className="h-4 w-4" /></Link>
        <button ref={menuButtonRef} type="button" className="header-menu flex xl:hidden" aria-expanded={menuOpen} aria-controls="mobile-nav" onClick={() => setMenuOpen((o) => !o)}>
          {menuOpen ? <X aria-hidden="true" className="h-5 w-5" /> : <Menu aria-hidden="true" className="h-5 w-5" />}
          <span className="sr-only sm:not-sr-only">{menuOpen ? t("closeMenu") : t("menu")}</span>
        </button>
      </div>
      <nav id="mobile-nav" aria-label="Main" hidden={!menuOpen} className="mobile-navigation xl:hidden">
        <ul className="mx-auto grid max-w-[1440px] px-5 py-4 sm:grid-cols-2 sm:gap-x-8 sm:px-8">
          <li><Link href="/" onClick={() => setMenuOpen(false)}>{t("home")}</Link></li>
          {mainNav.map((item) => <li key={item.key}><Link href={item.href} onClick={() => setMenuOpen(false)}>{t(item.key)}</Link></li>)}
          {topLinks.filter(item => item.key === "accessibility").map(item => <li key={item.key}><Link href={item.href} onClick={() => setMenuOpen(false)}>{t(item.key)}</Link></li>)}
          <li><Link href="/admin/login" onClick={() => setMenuOpen(false)}><LockKeyhole aria-hidden="true" className="h-4 w-4" />{t("adminLogin")}</Link></li>
        </ul>
      </nav>
    </header>
  );
}

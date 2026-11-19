"use client";

import Link from "next/link";
import { Moon, Sun } from "lucide-react";
import { usePreferences } from "@/lib/accessibility/preferences";
import { cn } from "@/lib/cn";

/**
 * Slim dark-navy bar across the top (DGCA style): organisation lines on the
 * left, accessibility controls and language switch on the right.
 */
export function UtilityBar() {
  const { t, contrast, setContrast, increaseText, decreaseText, resetText, textSize, toggleLocale, locale } =
    usePreferences();

  const ctrl =
    "flex h-7 min-w-7 items-center justify-center rounded px-1 text-[0.8rem] text-white/90 hover:bg-white/10 hover:text-white";

  return (
    <div className="utility-bar bg-navy text-white">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-1.5 sm:px-6 lg:px-8">
        {/* Left: bilingual organisation name */}
        <div className="flex items-center gap-3 text-[0.68rem] font-semibold uppercase leading-tight">
          <div>
            <span className="block font-devanagari normal-case">डिजी यात्रा सूचना पोर्टल</span>
            <span className="block">Digi Yatra Information Portal</span>
          </div>
          <Link href="/admin/login" className="ml-3 border-l border-white/25 pl-4 text-[0.68rem] font-normal normal-case text-white/80 hover:underline">{t("adminLogin")}</Link>
        </div>

        {/* Right: skip link, screen-reader page, contrast, text size, language */}
        <nav aria-label="Accessibility tools" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.82rem]">
          <a href="#main-content" className="hidden font-medium hover:underline md:inline">
            {t("skipToMain")}
          </a>
          <span aria-hidden="true" className="hidden text-white/60 md:inline">/</span>
          <Link href="/accessibility" className="hidden font-medium hover:underline md:inline">
            {t("screenReader")}
          </Link>
          <span aria-hidden="true" className="hidden h-4 w-px bg-white/50 md:inline-block" />

          <div role="group" aria-label={t("contrast")} className="flex items-center gap-1">
            <span className="hidden text-white/75 sm:inline">{t("contrast")}</span>
            <button
              type="button"
              className={cn(ctrl, contrast === "normal" && "bg-white/15")}
              aria-pressed={contrast === "normal"}
              aria-label={t("contrastNormal")}
              title={t("contrastNormal")}
              onClick={() => setContrast("normal")}
            >
              <Sun aria-hidden="true" className="h-4 w-4" />
            </button>
            <button
              type="button"
              className={cn(ctrl, contrast === "high" && "bg-white/15")}
              aria-pressed={contrast === "high"}
              aria-label={t("contrastHigh")}
              title={t("contrastHigh")}
              onClick={() => setContrast("high")}
            >
              <Moon aria-hidden="true" className="h-4 w-4" />
            </button>
          </div>

          <span aria-hidden="true" className="h-4 w-px bg-white/50" />

          <div role="group" aria-label={t("text")} className="flex items-center gap-1">
            <span className="hidden text-white/75 sm:inline">{t("text")}</span>
            <button type="button" className={ctrl} onClick={increaseText} disabled={textSize === "xl"} aria-label={t("textIncrease")} title={t("textIncrease")}>
              +A
            </button>
            <button type="button" className={cn(ctrl, textSize === "md" && "bg-white/15")} onClick={resetText} aria-label={t("textReset")} title={t("textReset")}>
              A
            </button>
            <button type="button" className={ctrl} onClick={decreaseText} disabled={textSize === "sm"} aria-label={t("textDecrease")} title={t("textDecrease")}>
              -A
            </button>
          </div>

          <button
            type="button"
            onClick={toggleLocale}
            aria-label={t("switchLanguageLabel")}
            lang={locale === "en" ? "hi" : "en"}
            className="ml-1 rounded-full border border-white bg-white px-3 py-0.5 text-[0.85rem] font-medium text-navy hover:bg-white/90"
          >
            {t("switchLanguage")}
          </button>
        </nav>
      </div>
    </div>
  );
}

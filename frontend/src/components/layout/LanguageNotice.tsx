"use client";

import { Languages } from "lucide-react";
import { usePreferences } from "@/lib/accessibility/preferences";

/** Shown in Hindi mode: only navigation/headings are translated in this POC. */
export function LanguageNotice() {
  const { locale, t } = usePreferences();
  if (locale !== "hi") return null;
  return (
    <div role="note" className="border-b border-line bg-warning-soft">
      <p className="mx-auto flex max-w-[1440px] items-center gap-2 px-4 py-2 text-sm text-warning sm:px-6 lg:px-8">
        <Languages aria-hidden="true" className="h-4 w-4 shrink-0" />
        <span lang="hi">{t("englishOnlyNote")}</span>
        <span className="text-ink-soft">(Detailed content is currently available in English only.)</span>
      </p>
    </div>
  );
}

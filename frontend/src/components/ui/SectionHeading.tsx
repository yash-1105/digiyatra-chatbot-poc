"use client";

import { useAltLabel, usePreferences } from "@/lib/accessibility/preferences";
import type { DictionaryKey } from "@/lib/i18n/dictionary";
import { cn } from "@/lib/cn";

interface SectionHeadingProps {
  id?: string;
  labelKey: DictionaryKey;
  description?: string;
  align?: "center" | "left";
  className?: string;
}

/**
 * Formal portal heading: large navy-blue title in the active language with
 * the other language as a small bilingual subtitle, plus a short orange rule.
 */
export function SectionHeading({ id, labelKey, description, align = "center", className }: SectionHeadingProps) {
  const { t } = usePreferences();
  const alt = useAltLabel();
  return (
    <div className={cn("mb-8", align === "center" ? "text-center" : "text-left", className)}>
      <h2 id={id} className="text-[1.75rem] font-medium leading-tight text-heading sm:text-[2rem]">
        {t(labelKey)}
      </h2>
      <p className="mt-1 text-sm font-medium tracking-wide text-ink-soft">{alt(labelKey)}</p>
      <span
        aria-hidden="true"
        className={cn("mt-3 block h-[3px] w-14 rounded bg-accent", align === "center" ? "mx-auto" : "")}
      />
      {description ? (
        <p className={cn("mt-4 max-w-3xl text-base leading-relaxed text-ink-muted", align === "center" ? "mx-auto" : "")}>
          {description}
        </p>
      ) : null}
    </div>
  );
}

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

export function SectionHeading({ id, labelKey, description, align = "left", className }: SectionHeadingProps) {
  const { t } = usePreferences();
  const alt = useAltLabel();
  return (
    <div className={cn("section-heading mb-10 sm:mb-14", align === "center" ? "text-center" : "text-left", className)}>
      <h2 id={id} className="section-title font-semibold leading-tight text-heading">
        {t(labelKey)}
      </h2>
      <p className="mt-1 text-sm font-medium tracking-wide text-ink-soft">{alt(labelKey)}</p>
      <span
        aria-hidden="true"
        className={cn("hidden", align === "center" ? "mx-auto" : "")}
      />
      {description ? (
        <p className={cn("mt-4 max-w-3xl text-base leading-relaxed text-ink-muted", align === "center" ? "mx-auto" : "")}>
          {description}
        </p>
      ) : null}
    </div>
  );
}

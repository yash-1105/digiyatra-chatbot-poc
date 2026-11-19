"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { dictionary, type DictionaryKey, type Locale } from "@/lib/i18n/dictionary";

export type Contrast = "normal" | "high";
export type TextSize = "sm" | "md" | "lg" | "xl";

const TEXT_SIZES: TextSize[] = ["sm", "md", "lg", "xl"];
const STORAGE_KEY = "dy-poc-preferences";

interface StoredPreferences {
  contrast: Contrast;
  textSize: TextSize;
  locale: Locale;
}

interface PreferencesContextValue extends StoredPreferences {
  setContrast: (value: Contrast) => void;
  increaseText: () => void;
  decreaseText: () => void;
  resetText: () => void;
  toggleLocale: () => void;
  t: (key: DictionaryKey) => string;
}

const DEFAULTS: StoredPreferences = { contrast: "normal", textSize: "md", locale: "en" };

const PreferencesContext = createContext<PreferencesContextValue | null>(null);

function readStored(): StoredPreferences {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<StoredPreferences>;
    return {
      contrast: parsed.contrast === "high" ? "high" : "normal",
      textSize: TEXT_SIZES.includes(parsed.textSize as TextSize) ? (parsed.textSize as TextSize) : "md",
      locale: parsed.locale === "hi" ? "hi" : "en",
    };
  } catch {
    return DEFAULTS;
  }
}

/**
 * Holds the accessibility preferences shown in the navy utility bar
 * (contrast, text size, language) and mirrors them onto <html> attributes
 * so plain CSS can react to them.
 */
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<StoredPreferences>(DEFAULTS);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setPrefs(readStored());
    setHydrated(true);
  }, []);

  useEffect(() => {
    // Before hydration the inline bootstrap script in layout.tsx owns <html>.
    if (!hydrated) return;
    const root = document.documentElement;
    root.dataset.contrast = prefs.contrast;
    root.dataset.textSize = prefs.textSize;
    root.lang = prefs.locale === "hi" ? "hi" : "en";
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      /* storage unavailable (private mode) — preferences simply won't persist */
    }
  }, [prefs, hydrated]);

  const stepText = useCallback((delta: number) => {
    setPrefs((p) => {
      const idx = TEXT_SIZES.indexOf(p.textSize);
      const next = TEXT_SIZES[Math.min(TEXT_SIZES.length - 1, Math.max(0, idx + delta))] ?? "md";
      return { ...p, textSize: next };
    });
  }, []);

  const value = useMemo<PreferencesContextValue>(
    () => ({
      ...prefs,
      setContrast: (contrast) => setPrefs((p) => ({ ...p, contrast })),
      increaseText: () => stepText(1),
      decreaseText: () => stepText(-1),
      resetText: () => setPrefs((p) => ({ ...p, textSize: "md" })),
      toggleLocale: () => setPrefs((p) => ({ ...p, locale: p.locale === "en" ? "hi" : "en" })),
      t: (key) => dictionary[prefs.locale][key],
    }),
    [prefs, stepText],
  );

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): PreferencesContextValue {
  const ctx = useContext(PreferencesContext);
  if (!ctx) throw new Error("usePreferences must be used inside <PreferencesProvider>");
  return ctx;
}

/** Bilingual helper: returns the label in the other language (for subtitles). */
export function useAltLabel() {
  const { locale } = usePreferences();
  return (key: DictionaryKey) => dictionary[locale === "en" ? "hi" : "en"][key];
}

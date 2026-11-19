import type { DictionaryKey } from "@/lib/i18n/dictionary";

export interface NavItem {
  /** Full label (footer, mobile menu). */
  key: DictionaryKey;
  /** Compact label for the single-line desktop navigation bar. */
  short?: DictionaryKey;
  href: string;
}

/** Main navigation — anchors to homepage sections. */
export const mainNav: NavItem[] = [
  { key: "about", short: "navAbout", href: "/#about" },
  { key: "howItWorks", href: "/#how-it-works" },
  { key: "registration", short: "navRegistration", href: "/#registration" },
  { key: "journey", href: "/#journey" },
  { key: "airports", short: "navAirports", href: "/#airports" },
  { key: "privacy", href: "/#privacy" },
  { key: "faq", href: "/#faq" },
  { key: "support", short: "navContact", href: "/#support" },
];

/** Secondary links shown in the header's top row (pipe separated). */
export const topLinks: NavItem[] = [
  { key: "about", href: "/#about" },
  { key: "faq", href: "/#faq" },
  { key: "support", href: "/#support" },
  { key: "accessibility", href: "/accessibility" },
];

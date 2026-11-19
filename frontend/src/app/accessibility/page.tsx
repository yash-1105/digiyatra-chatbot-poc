import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/ui/Container";
import { PublicShell } from "@/components/layout/PublicShell";

export const metadata: Metadata = { title: "Accessibility & Screen Reader Access" };

const features = [
  ["Skip to main content", "Available from the top utility bar and as the first keyboard stop on every page."],
  ["Contrast", "Use the sun (standard) and moon (high contrast) buttons in the top bar. Your choice is remembered on this device."],
  ["Text size", "Use +A, A and -A to increase, reset or decrease text size across the whole site."],
  ["Language", "Switch navigation and headings between English and Hindi (हिंदी). Detailed content is currently in English."],
  ["Keyboard navigation", "All menus, tabs, accordions, the carousel and the assistant are operable with a keyboard. Tabs support the arrow, Home and End keys. Press Esc to close the assistant or the mobile menu."],
  ["Reduced motion", "If your device requests reduced motion, the carousel does not auto-rotate and animations are minimised."],
  ["Screen readers", "Pages use semantic headings, landmarks and labelled controls. Chat replies are announced through a live region."],
] as const;

const readers = [
  ["NVDA", "Windows", "Free"],
  ["JAWS", "Windows", "Commercial"],
  ["Narrator", "Windows", "Built-in"],
  ["VoiceOver", "macOS / iOS", "Built-in"],
  ["TalkBack", "Android", "Built-in"],
] as const;

export default function AccessibilityPage() {
  return (
    <PublicShell>
      <div className="border-b border-line bg-band">
        <Container className="py-3 text-sm text-ink-muted">
          <Link href="/" className="text-brand hover:underline">Home</Link> <span aria-hidden="true">›</span> Accessibility
        </Container>
      </div>
      <Container className="py-12">
        <h1 className="text-[2rem] text-heading">Accessibility &amp; Screen Reader Access</h1>
        <span aria-hidden="true" className="mt-3 block h-[3px] w-14 rounded bg-accent" />
        <p className="mt-5 max-w-3xl leading-relaxed text-ink-muted">
          This proof-of-concept aims to follow WCAG 2.1 AA practices so that information about Digi Yatra is available to
          everyone. The following features are available on every page.
        </p>

        <dl className="mt-8 grid gap-4 md:grid-cols-2">
          {features.map(([term, desc]) => (
            <div key={term} className="rounded-md border border-line-soft bg-surface p-5 shadow-card">
              <dt className="font-semibold text-heading">{term}</dt>
              <dd className="mt-1 text-[0.95rem] leading-relaxed text-ink-muted">{desc}</dd>
            </div>
          ))}
        </dl>

        <h2 className="mt-12 text-2xl text-heading">Screen readers</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full max-w-2xl border-collapse text-left text-sm">
            <caption className="sr-only">Commonly used screen readers</caption>
            <thead>
              <tr className="bg-panel text-panel-ink">
                <th scope="col" className="px-4 py-2.5 font-semibold">Screen reader</th>
                <th scope="col" className="px-4 py-2.5 font-semibold">Platform</th>
                <th scope="col" className="px-4 py-2.5 font-semibold">Licence</th>
              </tr>
            </thead>
            <tbody>
              {readers.map(([name, platform, licence]) => (
                <tr key={name} className="border-b border-line odd:bg-surface even:bg-band">
                  <th scope="row" className="px-4 py-2.5 font-medium text-ink">{name}</th>
                  <td className="px-4 py-2.5 text-ink-muted">{platform}</td>
                  <td className="px-4 py-2.5 text-ink-muted">{licence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-8 text-sm text-ink-soft">
          Found an accessibility problem in this POC? Please report it to the project team.
        </p>
      </Container>
    </PublicShell>
  );
}

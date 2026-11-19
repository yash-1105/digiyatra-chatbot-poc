import { BadgeCheck, Clock, Database, EyeOff, Handshake, ShieldAlert, Smartphone, UserCog } from "lucide-react";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { privacyPrinciples, privacyRights, securityAlert } from "@/content/site";
import { officialLinks } from "@/lib/config";

const ICONS = [Database, Smartphone, Handshake, Clock, EyeOff, BadgeCheck];

export function PrivacySection() {
  return (
    <Section id="privacy" labelledBy="privacy-title">
      <SectionHeading
        id="privacy-title"
        labelKey="privacy"
        description="Digi Yatra is built on Self-Sovereign Identity: your credentials live on your device and are shared only with your consent."
      />
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <ul className="grid gap-4 sm:grid-cols-2">
          {privacyPrinciples.map((p, i) => {
            const Icon = ICONS[i] ?? Database;
            return (
              <li key={p.title} className="rounded-md border border-line-soft bg-surface p-5 shadow-card">
                <span className="flex h-10 w-10 items-center justify-center rounded bg-brand-soft text-brand">
                  <Icon aria-hidden="true" className="h-5 w-5" />
                </span>
                <h3 className="mt-3 font-semibold text-heading">{p.title}</h3>
                <p className="mt-1 text-[0.95rem] leading-relaxed text-ink-muted">{p.body}</p>
              </li>
            );
          })}
        </ul>

        <div className="flex flex-col gap-5">
          <div className="rounded-md bg-panel p-6 text-panel-ink shadow-card">
            <h3 className="flex items-center gap-2 text-lg font-semibold">
              <UserCog aria-hidden="true" className="h-5 w-5 text-accent" /> Your data rights
            </h3>
            <ul className="mt-3 space-y-2 text-sm leading-relaxed text-panel-ink/90">
              {privacyRights.map((r) => (
                <li key={r} className="flex gap-2">
                  <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  {r}
                </li>
              ))}
            </ul>
            <p className="mt-4 text-sm">
              <ExternalLink href={officialLinks.privacyPolicy} className="text-white underline-offset-2 hover:underline [html[data-contrast=high]_&]:text-[#ffff00]">
                Read the official Privacy Policy
              </ExternalLink>
            </p>
          </div>
          <div role="note" className="rounded-md border-l-4 border-danger bg-danger-soft p-5">
            <p className="flex items-center gap-2 font-semibold text-danger">
              <ShieldAlert aria-hidden="true" className="h-5 w-5" /> Security alert
            </p>
            <p className="mt-2 text-sm leading-relaxed text-ink">{securityAlert}</p>
          </div>
        </div>
      </div>
    </Section>
  );
}

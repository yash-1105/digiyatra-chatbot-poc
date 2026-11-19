import { BadgeCheck, Clock, Hand, Sparkles, Users } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { aboutFacts, benefits } from "@/content/site";

const BENEFIT_ICONS = [Clock, Users, Hand, Sparkles];

export function AboutSection() {
  return (
    <Section id="about" labelledBy="about-title" tone="grey">
      <SectionHeading
        id="about-title"
        labelKey="about"
        description="Digi Yatra enables paperless and contactless passenger processing at Indian airports, built on the principle that passengers stay in control of their own data."
      />
      <div className="grid gap-5 md:grid-cols-2">
        {aboutFacts.map((f) => (
          <Card key={f.title} className="border-l-4 border-l-brand">
            <h3 className="flex items-center gap-2 text-lg font-semibold text-heading">
              <BadgeCheck aria-hidden="true" className="h-5 w-5 text-accent" />
              {f.title}
            </h3>
            <p className="mt-2 leading-relaxed text-ink-muted">{f.body}</p>
          </Card>
        ))}
      </div>

      <h3 className="mb-4 mt-12 text-center text-xl font-medium text-heading">Benefits for passengers</h3>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {benefits.map((b, i) => {
          const Icon = BENEFIT_ICONS[i] ?? Sparkles;
          return (
            <li key={b.title} className="rounded-md bg-surface p-5 text-center shadow-card">
              <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-brand-soft text-brand">
                <Icon aria-hidden="true" className="h-6 w-6" />
              </span>
              <p className="mt-3 font-semibold text-heading">{b.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-ink-muted">{b.body}</p>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

import { Info, PlaneTakeoff, Smartphone, UploadCloud } from "lucide-react";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { howItWorks, howItWorksNotes } from "@/content/site";

const STEP_ICONS = [Smartphone, UploadCloud, PlaneTakeoff];

export function HowItWorksSection() {
  return (
    <Section id="how-it-works" labelledBy="how-title">
      <SectionHeading
        id="how-title"
        labelKey="howItWorks"
        description="Three stages take you from enrolment to the aircraft door."
      />
      <ol className="relative grid gap-6 lg:grid-cols-3">
        {/* connector line on desktop */}
        <span aria-hidden="true" className="absolute left-[16%] right-[16%] top-8 hidden h-0.5 bg-line lg:block" />
        {howItWorks.map((s, i) => {
          const Icon = STEP_ICONS[i] ?? Smartphone;
          return (
            <li key={s.step} className="relative rounded-md border border-line-soft bg-surface p-6 shadow-card">
              <div className="flex items-center gap-3">
                <span className="relative z-10 flex h-16 w-16 shrink-0 items-center justify-center rounded-full border-4 border-page bg-panel text-white">
                  <Icon aria-hidden="true" className="h-7 w-7" />
                </span>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-accent">Step {s.step}</p>
                  <h3 className="text-lg font-semibold text-heading">{s.title}</h3>
                </div>
              </div>
              <ul className="mt-4 space-y-2 text-[0.95rem] leading-relaxed text-ink-muted">
                {s.points.map((p) => (
                  <li key={p} className="flex gap-2">
                    <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
                    {p}
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ol>
      <div className="mt-8 rounded-md border border-brand/30 bg-brand-soft p-5">
        <p className="flex items-center gap-2 font-semibold text-heading">
          <Info aria-hidden="true" className="h-5 w-5 text-brand" /> Good to know
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-6 text-[0.95rem] text-ink-muted">
          {howItWorksNotes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </div>
    </Section>
  );
}

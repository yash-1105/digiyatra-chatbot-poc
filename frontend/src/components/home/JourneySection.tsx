import { ArrowRight, DoorOpen, Plane, ShieldCheck, TriangleAlert } from "lucide-react";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { journeySteps, journeyNotes } from "@/content/site";

const ICONS = [DoorOpen, ShieldCheck, Plane];

export function JourneySection() {
  return (
    <Section id="journey" labelledBy="journey-title">
      <SectionHeading
        id="journey-title"
        labelKey="journey"
        description="What to expect at each Digi Yatra touchpoint on the day you fly."
      />
      <ol className="grid items-stretch gap-4 lg:grid-cols-[1fr_auto_1fr_auto_1fr]">
        {journeySteps.map((s, i) => {
          const Icon = ICONS[i] ?? DoorOpen;
          return (
            <li key={s.title} className="contents">
              <div className="overflow-hidden rounded-md border border-line-soft bg-surface shadow-card">
                <div className="flex items-center gap-3 bg-panel px-5 py-3 text-panel-ink">
                  <Icon aria-hidden="true" className="h-6 w-6 text-accent" />
                  <h3 className="font-semibold">
                    <span className="sr-only">Checkpoint {i + 1}: </span>
                    {s.title}
                  </h3>
                </div>
                <ol className="space-y-3 p-5">
                  {s.points.map((p, j) => (
                    <li key={p} className="flex gap-3 text-[0.95rem] text-ink-muted">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-soft text-xs font-bold text-brand">
                        {j + 1}
                      </span>
                      {p}
                    </li>
                  ))}
                </ol>
              </div>
              {i < journeySteps.length - 1 ? (
                <span aria-hidden="true" className="hidden items-center text-accent lg:flex">
                  <ArrowRight className="h-7 w-7" />
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
      <div className="mt-8 rounded-md border border-warning/40 bg-warning-soft p-5">
        <p className="flex items-center gap-2 font-semibold text-warning">
          <TriangleAlert aria-hidden="true" className="h-5 w-5" /> Please note
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-6 text-[0.95rem] text-ink-muted">
          {journeyNotes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </div>
    </Section>
  );
}

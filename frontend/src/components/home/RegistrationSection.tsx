import { Baby, IdCard, Languages, PlayCircle, Smartphone, UserRound, Users } from "lucide-react";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { registrationSteps, registrationTips } from "@/content/site";
import { officialLinks } from "@/lib/config";

const TIP_ICONS = [IdCard, UserRound, Baby, Smartphone, IdCard, Languages];

export function RegistrationSection() {
  return (
    <Section id="registration" labelledBy="registration-title" tone="grey">
      <SectionHeading
        id="registration-title"
        labelKey="registration"
        description="Enrolment is a one-time process completed entirely in the official Digi Yatra app."
      />
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <ol className="rounded-md bg-surface p-6 shadow-card sm:p-8">
          {registrationSteps.map((s, i) => (
            <li key={s.title} className="relative flex gap-4 pb-7 last:pb-0">
              {i < registrationSteps.length - 1 ? (
                <span aria-hidden="true" className="absolute left-[19px] top-11 h-[calc(100%-2.75rem)] w-0.5 bg-line" />
              ) : null}
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent text-lg font-bold text-white">
                {i + 1}
              </span>
              <div>
                <h3 className="text-lg font-semibold text-heading">{s.title}</h3>
                <p className="mt-1 leading-relaxed text-ink-muted">{s.detail}</p>
              </div>
            </li>
          ))}
        </ol>

        <div className="flex flex-col gap-5">
          <div className="rounded-md bg-panel p-6 text-panel-ink shadow-card">
            <h3 className="text-lg font-semibold">Get the official app</h3>
            <p className="mt-1 text-sm text-panel-ink/85">Only download Digi Yatra from the official app stores.</p>
            <div className="mt-4 grid gap-3">
              <a
                href={officialLinks.playStore}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 rounded border border-white/40 px-4 py-2.5 hover:bg-white/10"
              >
                <PlayCircle aria-hidden="true" className="h-6 w-6 text-accent" />
                <span>
                  <span className="block text-xs text-panel-ink/75">Android</span>
                  <span className="block font-medium">Google Play Store</span>
                </span>
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
              <a
                href={officialLinks.appStore}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 rounded border border-white/40 px-4 py-2.5 hover:bg-white/10"
              >
                <Smartphone aria-hidden="true" className="h-6 w-6 text-accent" />
                <span>
                  <span className="block text-xs text-panel-ink/75">iPhone</span>
                  <span className="block font-medium">Apple App Store</span>
                </span>
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            </div>
          </div>
          <div className="rounded-md bg-surface p-6 shadow-card">
            <h3 className="flex items-center gap-2 text-lg font-semibold text-heading">
              <Users aria-hidden="true" className="h-5 w-5 text-accent" /> Enrolment videos
            </h3>
            <ul className="mt-3 space-y-2 text-[0.95rem]">
              {[
                ["Enrol using Aadhaar", "https://www.youtube.com/watch?v=y6xTGrpfAGs"],
                ["Enrol using DigiLocker", "https://www.youtube.com/watch?v=7z7iLNSkFg4"],
                ["Add a dependent / minor", "https://www.youtube.com/watch?v=j2lw7LljME0"],
              ].map(([label, href]) => (
                <li key={href}>
                  <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline">
                    {label}
                    <span className="sr-only"> (YouTube, opens in a new tab)</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {registrationTips.map((tip, i) => {
          const Icon = TIP_ICONS[i] ?? IdCard;
          return (
            <li key={tip.title} className="flex gap-3 rounded-md border border-line-soft bg-surface p-4">
              <Icon aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-brand" />
              <div>
                <p className="font-semibold text-heading">{tip.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-ink-muted">{tip.body}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

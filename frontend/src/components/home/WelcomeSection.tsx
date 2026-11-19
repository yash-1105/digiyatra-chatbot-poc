"use client";

import { Compass, HeartHandshake, Megaphone, Target } from "lucide-react";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { welcome } from "@/content/site";
import { usePreferences } from "@/lib/accessibility/preferences";
import { AnnouncementsList } from "./AnnouncementsList";

const PANEL_ICONS = { mission: Target, vision: Compass, commitment: HeartHandshake } as const;

/** Welcome text + navy mission/vision panels, with announcements alongside. */
export function WelcomeSection() {
  const { t } = usePreferences();
  return (
    <Section id="welcome" labelledBy="welcome-title">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div>
          <SectionHeading id="welcome-title" labelKey="welcome" align="left" className="mb-5" />
          <p className="text-[1.05rem] leading-relaxed text-ink">{welcome.intro}</p>
          <p className="mt-3 leading-relaxed text-ink-muted">{welcome.operator}</p>

          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            {welcome.panels.map((p) => {
              const Icon = PANEL_ICONS[p.key];
              return (
                <div key={p.key} className="rounded-md bg-panel p-5 text-panel-ink shadow-card">
                  <Icon aria-hidden="true" className="h-8 w-8 text-accent" />
                  <h3 className="mt-3 text-lg font-semibold">{t(p.key)}</h3>
                  <span aria-hidden="true" className="my-2 block h-0.5 w-10 bg-accent" />
                  <p className="text-sm leading-relaxed text-panel-ink/90">{p.body}</p>
                </div>
              );
            })}
          </div>
        </div>

        <aside aria-labelledby="welcome-news-title" className="flex flex-col overflow-hidden rounded-md border border-line bg-surface shadow-card">
          <h3 id="welcome-news-title" className="flex items-center gap-2 bg-panel px-5 py-3 text-lg font-semibold text-panel-ink">
            <Megaphone aria-hidden="true" className="h-5 w-5 text-accent" />
            {t("announcements")}
          </h3>
          <div className="flex flex-1 items-center px-5">
            <AnnouncementsList compact />
          </div>
        </aside>
      </div>
    </Section>
  );
}

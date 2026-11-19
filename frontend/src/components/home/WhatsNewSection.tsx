"use client";

import type { ReactNode } from "react";
import { Section } from "@/components/ui/Section";
import { Tabs } from "@/components/ui/Tabs";
import { appDownloads, guidelines, videoTutorials } from "@/content/site";
import { usePreferences } from "@/lib/accessibility/preferences";
import { AnnouncementsList } from "./AnnouncementsList";
import { ResourceList } from "./ResourceList";

/** "नया क्या है?" — large centred heading, four text tabs, white list card. */
export function WhatsNewSection() {
  const { t } = usePreferences();
  return (
    <Section id="whats-new" labelledBy="whats-new-title" tone="grey" className="pt-12">
      <h2 id="whats-new-title" className="mb-6 text-center text-[2rem] text-heading sm:text-[2.3rem]">
        {t("whatsNew")}
      </h2>
      <Tabs
        label={t("whatsNew")}
        defaultTab="videos"
        tabs={[
          {
            id: "guidelines",
            label: t("guidelines"),
            content: <Panel><ResourceList items={guidelines} icon="doc" /></Panel>,
          },
          {
            id: "videos",
            label: t("videos"),
            content: <Panel><ResourceList items={videoTutorials} icon="video" /></Panel>,
          },
          {
            id: "downloads",
            label: t("downloads"),
            content: <Panel><ResourceList items={appDownloads} icon="app" /></Panel>,
          },
          {
            id: "announcements",
            label: t("announcements"),
            content: <Panel><AnnouncementsList /></Panel>,
          },
        ]}
      />
    </Section>
  );
}

function Panel({ children }: { children: ReactNode }) {
  return <div className="rounded-lg bg-surface px-5 py-5 shadow-card sm:px-8 sm:py-7">{children}</div>;
}

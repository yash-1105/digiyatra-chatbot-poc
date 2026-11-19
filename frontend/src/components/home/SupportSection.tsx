"use client";

import { Building2, Mail, MessageCircleQuestion, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { contactChannels, supportGuidance } from "@/content/site";
import { openChat } from "@/lib/chat-events";
import { officialLinks } from "@/lib/config";

export function SupportSection() {
  return (
    <Section id="support" labelledBy="support-title">
      <SectionHeading
        id="support-title"
        labelKey="support"
        description="Contact details below are taken from Digi Yatra Foundation published material. Please verify on the official contact page."
      />
      <div className="grid gap-5 md:grid-cols-3">
        {contactChannels.map((c) => (
          <div key={c.value} className="flex flex-col rounded-md border border-line-soft border-t-4 border-t-accent bg-surface p-6 shadow-card">
            <Mail aria-hidden="true" className="h-6 w-6 text-brand" />
            <h3 className="mt-3 font-semibold text-heading">{c.label}</h3>
            <a href={`mailto:${c.value}`} className="mt-1 break-all text-brand hover:underline">
              {c.value}
            </a>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">{c.note}</p>
          </div>
        ))}
      </div>

      <div className="mt-8 grid gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="rounded-md bg-band p-6">
          <h3 className="flex items-center gap-2 text-lg font-semibold text-heading">
            <ShieldCheck aria-hidden="true" className="h-5 w-5 text-accent" /> Before you contact support
          </h3>
          <ul className="mt-3 list-disc space-y-2 pl-6 text-[0.95rem] leading-relaxed text-ink-muted">
            {supportGuidance.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </div>
        <div className="flex flex-col justify-between gap-4 rounded-md bg-panel p-6 text-panel-ink shadow-card">
          <div>
            <h3 className="flex items-center gap-2 text-lg font-semibold">
              <Building2 aria-hidden="true" className="h-5 w-5 text-accent" /> Need quick help?
            </h3>
            <p className="mt-2 text-sm text-panel-ink/90">
              Ask the Digi Yatra assistant, or visit the official contact page for the latest support options.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="light" onClick={() => openChat()}>
              <MessageCircleQuestion aria-hidden="true" className="h-4 w-4" /> Open assistant
            </Button>
            <ExternalLink href={officialLinks.contact} className="inline-flex items-center rounded border border-white/60 px-4 py-2 text-white hover:bg-white/10">
              Official contact page
            </ExternalLink>
          </div>
        </div>
      </div>
    </Section>
  );
}

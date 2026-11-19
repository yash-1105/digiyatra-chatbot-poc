"use client";

import { useMemo, useState } from "react";
import { MessageCircleQuestion, Search } from "lucide-react";
import { Accordion } from "@/components/ui/Accordion";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { Tabs } from "@/components/ui/Tabs";
import { faqCategories, type FaqItem } from "@/content/site";
import { openChat } from "@/lib/chat-events";

function toAccordion(items: FaqItem[], prefix: string) {
  return items.map((item, i) => ({ id: `${prefix}-${i}`, title: item.q, body: item.a }));
}

export function FaqSection() {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();

  const results = useMemo(() => {
    if (!q) return [];
    return faqCategories.flatMap((c) =>
      c.items.filter((i) => i.q.toLowerCase().includes(q) || i.a.toLowerCase().includes(q)),
    );
  }, [q]);

  return (
    <Section id="faq" labelledBy="faq-title" tone="grey">
      <SectionHeading id="faq-title" labelKey="faq" description="Answers to common questions, drawn from Digi Yatra support material." />

      <div className="rounded-lg bg-surface p-5 shadow-card sm:p-8">
        <label htmlFor="faq-search" className="mb-2 block text-sm font-medium text-heading">
          Search the FAQs
        </label>
        <div className="relative mb-6 max-w-xl">
          <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-soft" />
          <input
            id="faq-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. OTP, minor, delete"
            autoComplete="off"
            className="w-full rounded border border-line bg-page py-2.5 pl-9 pr-3 text-ink placeholder:text-ink-soft focus:border-brand"
          />
        </div>

        {q ? (
          <div aria-live="polite">
            <p className="mb-2 text-sm text-ink-soft">
              {results.length} result{results.length === 1 ? "" : "s"} for “{query.trim()}”
            </p>
            {results.length > 0 ? (
              <Accordion key={q} items={toAccordion(results, "search")} />
            ) : (
              <EmptyState
                title="No matching questions"
                description="Try different keywords, browse the categories, or ask the Digi Yatra assistant."
                action={
                  <Button variant="outline" onClick={() => openChat({ question: query.trim() })}>
                    <MessageCircleQuestion aria-hidden="true" className="h-4 w-4" /> Ask the assistant
                  </Button>
                }
              />
            )}
          </div>
        ) : (
          <Tabs
            variant="compact"
            label="FAQ categories"
            tabs={faqCategories.map((c) => ({
              id: c.id,
              label: c.label,
              content: <Accordion items={toAccordion(c.items, c.id)} className="pt-2" />,
            }))}
          />
        )}
      </div>

      <div className="mt-6 flex flex-col items-center gap-3 text-center sm:flex-row sm:justify-center">
        <p className="text-ink-muted">Didn&apos;t find what you were looking for?</p>
        <Button variant="primary" onClick={() => openChat()}>
          <MessageCircleQuestion aria-hidden="true" className="h-4 w-4" /> Ask the Digi Yatra Assistant
        </Button>
      </div>
    </Section>
  );
}

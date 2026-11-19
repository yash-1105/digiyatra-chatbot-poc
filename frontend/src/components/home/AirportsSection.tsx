"use client";

import { useMemo, useState } from "react";
import { MapPin, Search, TriangleAlert } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { Tabs } from "@/components/ui/Tabs";
import { airportsSnapshot, type Airport } from "@/content/site";
import { officialLinks } from "@/lib/config";

function filterAirports(list: Airport[], query: string): Airport[] {
  const q = query.trim().toLowerCase();
  if (!q) return list;
  return list.filter((a) => a.code.toLowerCase().includes(q) || a.name.toLowerCase().includes(q));
}

function AirportGrid({ airports, query, officialHref }: { airports: Airport[]; query: string; officialHref: string }) {
  const filtered = useMemo(() => filterAirports(airports, query), [airports, query]);

  if (airports.length === 0) {
    return (
      <EmptyState
        title="No approved airport information available"
        description={<>Please refer to the <ExternalLink href={officialHref}>official airport list</ExternalLink>.</>}
      />
    );
  }
  if (filtered.length === 0) {
    return <EmptyState title="No matching airports" description={`No airport in this list matches “${query}”. Try a city name or a three-letter code.`} />;
  }
  return (
    <>
      <p className="sr-only" aria-live="polite">
        {filtered.length} airports shown
      </p>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((a) => (
          <li key={a.code} className="flex items-center gap-3 rounded border border-line-soft bg-surface px-4 py-3">
            <span className="flex h-11 w-14 shrink-0 items-center justify-center rounded bg-panel font-mono text-sm font-bold tracking-wider text-panel-ink">
              {a.code}
            </span>
            <span className="text-[0.95rem] leading-snug text-ink">{a.name}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

export function AirportsSection() {
  const [query, setQuery] = useState("");
  return (
    <Section id="airports" labelledBy="airports-title" tone="grey">
      <SectionHeading id="airports-title" labelKey="airports" />

      <div role="note" className="mb-6 flex gap-3 rounded-md border border-warning/40 bg-warning-soft p-4 text-sm leading-relaxed text-ink">
        <TriangleAlert aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-warning" />
        <p>
          <strong>Knowledge-base snapshot — not verified as current.</strong> Airport availability changes over time and
          this list has not been confirmed against the official source. Before you travel, check the{" "}
          <ExternalLink href={officialLinks.currentAirports}>official list of current airports</ExternalLink> or the{" "}
          <ExternalLink href={officialLinks.upcomingAirports}>upcoming airports</ExternalLink>.
        </p>
      </div>

      <div className="rounded-lg bg-surface p-5 shadow-card sm:p-7">
        <label htmlFor="airport-search" className="mb-2 block text-sm font-medium text-heading">
          Search by city, airport name or code
        </label>
        <div className="relative mb-6 max-w-md">
          <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-soft" />
          <input
            id="airport-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. Delhi, BLR"
            autoComplete="off"
            className="w-full rounded border border-line bg-page py-2.5 pl-9 pr-3 text-ink placeholder:text-ink-soft focus:border-brand"
          />
        </div>
        <Tabs
          variant="compact"
          label="Airport lists"
          tabs={[
            {
              id: "listed",
              label: (
                <span className="inline-flex items-center gap-1.5">
                  <MapPin aria-hidden="true" className="h-4 w-4" /> Listed airports ({airportsSnapshot.listed.length})
                </span>
              ),
              content: (
                <div className="pt-5">
                  <AirportGrid airports={airportsSnapshot.listed} query={query} officialHref={officialLinks.currentAirports} />
                </div>
              ),
            },
            {
              id: "planned",
              label: `Planned (${airportsSnapshot.planned.length})`,
              content: (
                <div className="pt-5">
                  <AirportGrid airports={airportsSnapshot.planned} query={query} officialHref={officialLinks.upcomingAirports} />
                </div>
              ),
            },
          ]}
        />
      </div>
    </Section>
  );
}

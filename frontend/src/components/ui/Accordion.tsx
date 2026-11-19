"use client";

import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

export interface AccordionItem {
  id: string;
  title: string;
  body: string;
}

export function Accordion({ items, className }: { items: AccordionItem[]; className?: string }) {
  const baseId = useId();
  const [open, setOpen] = useState<string | null>(items[0]?.id ?? null);

  return (
    <div className={cn("divide-y divide-line-soft", className)}>
      {items.map((item) => {
        const expanded = open === item.id;
        const btnId = `${baseId}-btn-${item.id}`;
        const panelId = `${baseId}-panel-${item.id}`;
        return (
          <div key={item.id}>
            <h3>
              <button
                type="button"
                id={btnId}
                aria-expanded={expanded}
                aria-controls={panelId}
                onClick={() => setOpen(expanded ? null : item.id)}
                className="flex w-full items-start justify-between gap-4 py-4 text-left text-[1.05rem] text-brand hover:text-brand-strong"
              >
                <span>{item.title}</span>
                <ChevronDown
                  aria-hidden="true"
                  className={cn("mt-1 h-5 w-5 shrink-0 transition-transform", expanded && "rotate-180")}
                />
              </button>
            </h3>
            <div id={panelId} role="region" aria-labelledby={btnId} hidden={!expanded} className="pb-5 pr-8">
              <p className="leading-relaxed text-ink-muted">{item.body}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

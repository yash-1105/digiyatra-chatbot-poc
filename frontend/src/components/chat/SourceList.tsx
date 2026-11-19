"use client";

import { useId, useState } from "react";
import { BookOpen, ChevronDown, ExternalLink } from "lucide-react";
import type { ChatSource } from "@/lib/api";
import { cn } from "@/lib/cn";

export function SourceList({ sources }: { sources: ChatSource[] }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  if (sources.length === 0) return null;

  return (
    <div className="mt-2 border-t border-line-soft pt-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-xs font-semibold text-brand hover:underline"
      >
        <BookOpen aria-hidden="true" className="h-3.5 w-3.5" />
        Sources ({sources.length})
        <ChevronDown aria-hidden="true" className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
      </button>
      <ol id={panelId} hidden={!open} className="mt-2 space-y-1.5">
        {sources.map((s, i) => (
          <li key={`${s.title}-${i}`} className="flex gap-2 text-xs leading-snug">
            <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-brand-soft text-[0.65rem] font-bold text-brand">
              {i + 1}
            </span>
            <span className="min-w-0">
              {s.url ? (
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline">
                  {s.title}
                  <ExternalLink aria-hidden="true" className="ml-0.5 inline h-3 w-3 align-[-1px]" />
                  <span className="sr-only"> (opens in a new tab)</span>
                </a>
              ) : (
                <span className="text-ink">{s.title}</span>
              )}
              {s.file ? (
                <span className="mt-0.5 block font-mono text-[0.65rem] text-ink-soft">
                  <span className="sr-only">Source file: </span>
                  {s.file}
                </span>
              ) : null}
              {s.snippet ? <span className="mt-0.5 block italic text-ink-soft">“{s.snippet}”</span> : null}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

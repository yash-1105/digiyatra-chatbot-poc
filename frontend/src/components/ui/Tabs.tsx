"use client";

import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface TabDef {
  id: string;
  label: ReactNode;
  content: ReactNode;
}

interface TabsProps {
  tabs: TabDef[];
  /** Accessible name for the tab list. */
  label: string;
  defaultTab?: string;
  variant?: "portal" | "compact";
  className?: string;
}

/**
 * WAI-ARIA tabs with roving tabindex (Arrow/Home/End keys).
 * "portal" variant mirrors the DGCA "What's New" tabs: large grey labels,
 * the active one blue with an orange underline.
 */
export function Tabs({ tabs, label, defaultTab, variant = "portal", className }: TabsProps) {
  const baseId = useId();
  const [active, setActive] = useState(defaultTab ?? tabs[0]?.id ?? "");
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const focusTab = (index: number) => {
    const tab = tabs[(index + tabs.length) % tabs.length];
    if (!tab) return;
    setActive(tab.id);
    refs.current[(index + tabs.length) % tabs.length]?.focus();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (e.key === "ArrowRight") focusTab(index + 1);
    else if (e.key === "ArrowLeft") focusTab(index - 1);
    else if (e.key === "Home") focusTab(0);
    else if (e.key === "End") focusTab(tabs.length - 1);
    else return;
    e.preventDefault();
  };

  return (
    <div className={className}>
      <div
        role="tablist"
        aria-label={label}
        className={cn(
          "flex overflow-x-auto",
          variant === "portal" ? "justify-between gap-2 sm:justify-around" : "gap-1 border-b border-line",
        )}
      >
        {tabs.map((tab, i) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(tab.id)}
              onKeyDown={(e) => onKeyDown(e, i)}
              className={cn(
                "shrink-0 whitespace-nowrap border-b-[3px] transition-colors",
                variant === "portal"
                  ? "px-2.5 pb-2 pt-1 text-base sm:px-3 sm:text-lg lg:px-5 lg:text-[1.6rem]"
                  : "-mb-px px-4 py-2.5 text-sm font-medium",
                selected
                  ? "border-accent text-brand"
                  : "border-transparent text-ink-soft hover:text-brand",
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${baseId}-panel-${tab.id}`}
          aria-labelledby={`${baseId}-tab-${tab.id}`}
          hidden={tab.id !== active}
          tabIndex={0}
          className="animate-fade-in focus-visible:outline-offset-4"
        >
          {tab.id === active ? tab.content : null}
        </div>
      ))}
    </div>
  );
}

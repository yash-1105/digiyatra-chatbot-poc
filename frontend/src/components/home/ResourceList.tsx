import { FileText, PlayCircle, Smartphone } from "lucide-react";
import type { ResourceItem } from "@/content/site";

const ICONS = { doc: FileText, video: PlayCircle, app: Smartphone } as const;

/** DGCA "What's New" list style: blue title link, grey meta line, rules between. */
export function ResourceList({ items, icon }: { items: ResourceItem[]; icon: keyof typeof ICONS }) {
  const Icon = ICONS[icon];
  return (
    <ul className="divide-y divide-line">
      {items.map((item) => {
        const external = item.href?.startsWith("http");
        return (
          <li key={item.title} className="flex gap-4 py-5 first:pt-1 last:pb-1">
            <Icon aria-hidden="true" className="mt-1 h-5 w-5 shrink-0 text-accent" />
            <div>
              {item.href ? (
                <a
                  href={item.href}
                  {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                  className="text-[1.08rem] leading-snug text-brand hover:text-brand-strong hover:underline sm:text-[1.2rem]"
                >
                  {item.title}
                  {external ? <span className="sr-only"> (opens in a new tab)</span> : null}
                </a>
              ) : (
                <p className="text-[1.08rem] leading-snug text-heading sm:text-[1.2rem]">{item.title}</p>
              )}
              <p className="mt-1.5 text-sm text-ink-soft">{item.meta}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

import type { ReactNode } from "react";
import { ExternalLink as ExternalIcon } from "lucide-react";
import { cn } from "@/lib/cn";

export function ExternalLink({ href, children, className, icon = true }: { href: string; children: ReactNode; className?: string; icon?: boolean }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={cn("text-brand hover:underline", className)}>
      {children}
      {icon ? <ExternalIcon aria-hidden="true" className="ml-1 inline h-3.5 w-3.5 align-[-2px]" /> : null}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

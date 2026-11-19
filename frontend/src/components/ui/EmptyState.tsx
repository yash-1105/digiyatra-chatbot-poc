import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import { cn } from "@/lib/cn";

interface EmptyStateProps {
  title: string;
  description: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ title, description, action, className }: EmptyStateProps) {
  return (
    <div role="status" className={cn("flex flex-col items-center px-6 py-10 text-center", className)}>
      <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-brand-soft text-brand">
        <Inbox aria-hidden="true" className="h-6 w-6" />
      </span>
      <p className="text-lg font-medium text-heading">{title}</p>
      <div className="mt-2 max-w-md text-sm leading-relaxed text-ink-muted">{description}</div>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

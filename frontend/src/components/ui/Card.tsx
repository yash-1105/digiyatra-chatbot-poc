import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-md border border-line-soft bg-surface p-5 shadow-card sm:p-6", className)}>{children}</div>
  );
}

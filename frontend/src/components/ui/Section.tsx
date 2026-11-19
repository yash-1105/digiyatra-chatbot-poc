import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Container } from "./Container";

interface SectionProps {
  id: string;
  labelledBy: string;
  tone?: "white" | "grey";
  children: ReactNode;
  className?: string;
}

/** Shared spacing and surface treatment for the information sections. */
export function Section({ id, labelledBy, tone = "white", children, className }: SectionProps) {
  return (
    <section
      id={id}
      aria-labelledby={labelledBy}
      className={cn("portal-section py-16 sm:py-24 lg:py-28", tone === "grey" ? "bg-band" : "bg-page", className)}
    >
      <Container>{children}</Container>
    </section>
  );
}

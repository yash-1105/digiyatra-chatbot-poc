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

/** Full-width band alternating white / light-grey like the DGCA portal. */
export function Section({ id, labelledBy, tone = "white", children, className }: SectionProps) {
  return (
    <section
      id={id}
      aria-labelledby={labelledBy}
      className={cn("py-14 sm:py-16", tone === "grey" ? "bg-band" : "bg-page", className)}
    >
      <Container>{children}</Container>
    </section>
  );
}

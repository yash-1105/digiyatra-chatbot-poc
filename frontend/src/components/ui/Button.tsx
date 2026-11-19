import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "pill" | "outline" | "ghost" | "light";

const base =
  "inline-flex items-center justify-center gap-2 font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60";

const variants: Record<Variant, string> = {
  primary: "rounded bg-brand px-5 py-2.5 text-white hover:bg-brand-strong",
  // Gradient pill like the DGCA "अधिक" (More) button.
  pill: "btn-pill rounded-full px-10 py-3 shadow-card",
  outline: "rounded border border-brand px-4 py-2 text-brand hover:bg-brand-soft",
  ghost: "rounded px-3 py-2 text-brand hover:bg-brand-soft",
  light: "rounded bg-white px-5 py-2.5 text-[#1d3a6a] hover:bg-white/90",
};

export function Button({
  variant = "primary",
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; children: ReactNode }) {
  return (
    <button type="button" className={cn(base, variants[variant], className)} {...props}>
      {children}
    </button>
  );
}

export function LinkButton({
  variant = "primary",
  className,
  children,
  ...props
}: AnchorHTMLAttributes<HTMLAnchorElement> & { variant?: Variant; children: ReactNode }) {
  return (
    <a className={cn(base, variants[variant], className)} {...props}>
      {children}
    </a>
  );
}

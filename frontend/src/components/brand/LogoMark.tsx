import { cn } from "@/lib/cn";

/** Plain-text independent identity until the Foundation authorizes its logo. */
export function LogoMark({ className, title = "Digi Yatra Information Portal", wordmark = false }: { className?: string; title?: string; wordmark?: boolean }) {
  return (
    <span role={title ? "img" : undefined} aria-label={title || undefined} aria-hidden={!title || undefined} className={cn("portal-brand", wordmark ? "portal-brand-wordmark" : "portal-brand-compact", className)}>
      {wordmark ? "digi yatra" : "dy"}
    </span>
  );
}

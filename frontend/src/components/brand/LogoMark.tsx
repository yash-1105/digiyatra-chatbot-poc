import { cn } from "@/lib/cn";

/** Owner-supplied artwork; viewports omit padding without altering the PNGs. */
export function LogoMark({ className, title = "Digi Yatra Information Portal", wordmark = false }: { className?: string; title?: string; wordmark?: boolean }) {
  return (
    <svg role={title ? "img" : undefined} aria-label={title || undefined} aria-hidden={!title || undefined} focusable="false" viewBox={wordmark ? "48 177 351 94" : "64 132 380 248"} className={cn("portal-brand", wordmark ? "portal-brand-wordmark" : "portal-brand-compact", className)}>
      <image href={wordmark ? "/branding/digiyatra_logo.png" : "/branding/chatbot_logo.png"} width={wordmark ? 447 : 512} height={wordmark ? 447 : 512} />
    </svg>
  );
}

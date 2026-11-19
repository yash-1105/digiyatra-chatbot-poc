import { cn } from "@/lib/cn";

/**
 * Original POC mark (face-scan frame + flight arc). Deliberately NOT based on
 * any government emblem or the official Digi Yatra logo.
 */
export function LogoMark({ className, title = "Digi Yatra Information Portal" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 64 64" role="img" aria-label={title} className={cn("h-14 w-14", className)}>
      <circle cx="32" cy="32" r="31" fill="#1d3a6a" />
      <circle cx="32" cy="32" r="27" fill="none" stroke="#ee7d22" strokeWidth="2" strokeDasharray="120 50" transform="rotate(-30 32 32)" />
      {/* face-scan corner brackets */}
      <g fill="none" stroke="#ffffff" strokeWidth="3" strokeLinecap="round">
        <path d="M19 25v-6h6" />
        <path d="M39 19h6v6" />
        <path d="M45 39v6h-6" />
        <path d="M25 45h-6v-6" />
      </g>
      {/* simple face */}
      <circle cx="32" cy="29" r="6" fill="#ffffff" />
      <path d="M22.5 42c1.8-5 5.4-7.2 9.5-7.2s7.7 2.2 9.5 7.2" fill="#ffffff" />
      {/* tiny plane */}
      <path d="M48 12.5l3.2 1.2-5.6 3.3-1.6-.6 1.8-1.6-3.3-1.3 1-0.9 3.8.5 1.2-1z" fill="#ee7d22" />
    </svg>
  );
}

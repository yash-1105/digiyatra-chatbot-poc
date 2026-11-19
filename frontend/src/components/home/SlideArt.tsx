import { ScanFace, ShieldCheck, Smartphone } from "lucide-react";
import type { SlideArt as SlideArtKind } from "@/content/site";

const ICONS = { face: ScanFace, phone: Smartphone, shield: ShieldCheck } as const;

/**
 * Decorative illustration for hero slides (no photographs are used because
 * the POC has no licensed imagery). Terminal skyline + runway + large icon.
 */
export function SlideArt({ kind }: { kind: SlideArtKind }) {
  const Icon = ICONS[kind];
  return (
    <div aria-hidden="true" className="absolute inset-0 overflow-hidden bg-gradient-to-br from-[#0f2f5c] via-[#1a4f8f] to-[#2d7fc9]">
      <svg className="illustration absolute inset-0 h-full w-full" viewBox="0 0 800 360" preserveAspectRatio="xMidYMid slice">
        {/* sky grid */}
        <g stroke="#ffffff" strokeOpacity="0.06">
          {Array.from({ length: 16 }, (_, i) => (
            <line key={`v${i}`} x1={i * 52} y1="0" x2={i * 52} y2="360" />
          ))}
          {Array.from({ length: 8 }, (_, i) => (
            <line key={`h${i}`} x1="0" y1={i * 52} x2="800" y2={i * 52} />
          ))}
        </g>
        {/* flight path */}
        <path d="M-20 250 C 180 120, 420 90, 820 40" fill="none" stroke="#ee7d22" strokeWidth="3" strokeDasharray="10 10" opacity="0.85" />
        {/* terminal skyline */}
        <path
          d="M0 300 L0 262 L60 262 L60 240 L130 240 L130 255 L210 255 L235 228 L340 228 L365 255 L470 255 L470 236 L560 236 L560 250 L640 250 L640 226 L700 226 L700 258 L800 258 L800 300 Z"
          fill="#0b2546"
          opacity="0.75"
        />
        {/* control tower */}
        <path d="M600 226 L600 170 L590 160 L630 160 L620 170 L620 226 Z" fill="#0b2546" opacity="0.85" />
        <rect x="588" y="150" width="44" height="12" rx="3" fill="#7fb6ea" opacity="0.6" />
        {/* runway */}
        <path d="M0 300 L800 300 L800 360 L0 360 Z" fill="#081d38" />
        <g stroke="#ffffff" strokeOpacity="0.55" strokeWidth="4">
          {Array.from({ length: 10 }, (_, i) => (
            <line key={`r${i}`} x1={20 + i * 85} y1="330" x2={60 + i * 85} y2="330" />
          ))}
        </g>
      </svg>
      <div className="absolute right-[8%] top-1/2 hidden -translate-y-[60%] sm:block">
        <div className="flex h-36 w-36 items-center justify-center rounded-full border-4 border-white/30 bg-white/10 backdrop-blur-sm lg:h-44 lg:w-44">
          <Icon className="h-20 w-20 text-white lg:h-24 lg:w-24" strokeWidth={1.4} />
        </div>
      </div>
    </div>
  );
}

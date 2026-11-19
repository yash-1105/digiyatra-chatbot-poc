"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { heroSlides, highlights } from "@/content/site";
import { usePreferences } from "@/lib/accessibility/preferences";
import { cn } from "@/lib/cn";
import { SlideArt } from "./SlideArt";

const AUTOPLAY_MS = 7000;

/**
 * DGCA-style top band: wide carousel on the left, "Highlights" (मुख्य अंश)
 * list panel on the right with a gradient "More" pill button.
 */
export function HeroSection() {
  const { t } = usePreferences();
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [hovered, setHovered] = useState(false);

  const go = useCallback((delta: number) => {
    setIndex((i) => (i + delta + heroSlides.length) % heroSlides.length);
  }, []);

  useEffect(() => {
    // Respect reduced-motion users: no auto-rotation.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) setPlaying(false);
  }, []);

  useEffect(() => {
    if (!playing || hovered) return;
    const timer = window.setInterval(() => go(1), AUTOPLAY_MS);
    return () => window.clearInterval(timer);
  }, [playing, hovered, go]);

  const slide = heroSlides[index] ?? heroSlides[0]!;

  return (
    <section aria-label="Featured information" className="border-b border-line bg-band-alt">
      <div className="grid lg:grid-cols-[minmax(0,1.85fr)_minmax(0,1fr)]">
        {/* Carousel */}
        <div
          className="relative h-[300px] overflow-hidden border-line sm:h-[340px] lg:h-[360px] lg:border-r-4 lg:border-r-panel"
          role="region"
          aria-roledescription="carousel"
          aria-label="Digi Yatra at a glance"
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          onFocusCapture={() => setHovered(true)}
          onBlurCapture={() => setHovered(false)}
        >
          <SlideArt key={slide.id} kind={slide.art} />
          <div
            key={`${slide.id}-caption`}
            role="group"
            aria-roledescription="slide"
            aria-label={`${index + 1} of ${heroSlides.length}`}
            className="absolute inset-0 flex animate-fade-in flex-col justify-end bg-gradient-to-t from-black/60 via-black/15 to-transparent px-14 pb-12 text-white sm:pr-[44%]"
          >
            <h2 className="text-xl font-semibold leading-snug sm:text-2xl lg:text-[1.75rem]">{slide.title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-white/90 sm:text-base">{slide.caption}</p>
            <Link
              href={slide.href}
              className="mt-4 inline-flex w-fit items-center gap-1 rounded border border-white/80 px-4 py-1.5 text-sm font-medium hover:bg-white hover:text-[#13203a]"
            >
              {slide.cta} <ChevronRight aria-hidden="true" className="h-4 w-4" />
            </Link>
          </div>

          {/* Prev / next — round translucent buttons at the edges like DGCA */}
          <button
            type="button"
            onClick={() => go(-1)}
            aria-label="Previous slide"
            className="absolute left-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-white/60 text-[#13203a] hover:bg-white"
          >
            <ChevronLeft aria-hidden="true" className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={() => go(1)}
            aria-label="Next slide"
            className="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-white/60 text-[#13203a] hover:bg-white"
          >
            <ChevronRight aria-hidden="true" className="h-5 w-5" />
          </button>

          {/* Dots + pause */}
          <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-2 sm:left-14 sm:translate-x-0">
            {heroSlides.map((s, i) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setIndex(i)}
                aria-label={`Go to slide ${i + 1}: ${s.title}`}
                aria-current={i === index}
                className={cn("h-2.5 rounded-full transition-all", i === index ? "w-7 bg-accent" : "w-2.5 bg-white/70 hover:bg-white")}
              />
            ))}
            <button
              type="button"
              onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? "Pause automatic slide rotation" : "Start automatic slide rotation"}
              className="ml-2 flex h-6 w-6 items-center justify-center rounded-full bg-white/60 text-[#13203a] hover:bg-white"
            >
              {playing ? <Pause aria-hidden="true" className="h-3 w-3" /> : <Play aria-hidden="true" className="h-3 w-3" />}
            </button>
          </div>
          <p className="sr-only" aria-live={playing ? "off" : "polite"}>
            Slide {index + 1} of {heroSlides.length}: {slide.title}
          </p>
        </div>

        {/* Highlights panel */}
        <div className="flex flex-col px-5 py-5 lg:h-[360px]">
          <h2 className="text-center text-[1.9rem] font-semibold text-ink">{t("highlights")}</h2>
          <ul className="mt-2 flex-1 overflow-y-auto pr-2 [scrollbar-width:thin]">
            {highlights.map((h) => (
              <li key={h.text} className="border-b border-line">
                <Link href={h.href} className="block py-2.5 text-[1rem] leading-snug text-brand hover:text-brand-strong hover:underline">
                  {h.text}
                </Link>
              </li>
            ))}
          </ul>
          <div className="pt-4 text-center">
            <Link href="/#faq" className="btn-pill inline-flex rounded-full px-14 py-3 text-base font-medium shadow-card">
              {t("more")}
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

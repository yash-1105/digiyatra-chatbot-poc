"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUpRight, ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { heroSlides, highlights } from "@/content/site";
import { usePreferences } from "@/lib/accessibility/preferences";
import { cn } from "@/lib/cn";
import { openChat } from "@/lib/chat-events";

const AUTOPLAY_MS = 7000;

export function HeroSection() {
  const { t } = usePreferences();
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [hovered, setHovered] = useState(false);
  const go = useCallback((delta: number) => setIndex((i) => (i + delta + heroSlides.length) % heroSlides.length), []);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) setPlaying(false);
  }, []);
  useEffect(() => {
    if (!playing || hovered) return;
    const timer = window.setInterval(() => go(1), AUTOPLAY_MS);
    return () => window.clearInterval(timer);
  }, [playing, hovered, go]);
  const slide = heroSlides[index] ?? heroSlides[0]!;
  return (
    <>
      <section aria-label="Featured information" className="foundation-hero">
        <div aria-hidden="true" className="hero-light-trail"><i /><i /><i /></div>
        <div className="hero-content">
          <h1>Welcome to Digi Yatra.<br /><span>Your journey, made simpler.</span></h1>
          <p className="hero-intro">Explore paperless airport travel.<br className="hidden sm:block" /> Get the information you need, before you fly.</p>
          <div className="hero-actions">
            <Link href="/#registration" className="btn-pill inline-flex items-center gap-3 rounded-full px-7 py-3.5">Get started <ArrowUpRight aria-hidden="true" className="h-5 w-5" /></Link>
            <button type="button" onClick={() => openChat()} className="hero-assistant">Ask the assistant <ArrowUpRight aria-hidden="true" className="h-4 w-4" /></button>
          </div>
        </div>
        <div className="hero-feature" role="region" aria-roledescription="carousel" aria-label="Digi Yatra at a glance" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} onFocusCapture={() => setHovered(true)} onBlurCapture={() => setHovered(false)}>
          <div role="group" aria-roledescription="slide" aria-label={`${index + 1} of ${heroSlides.length}`} className="hero-feature-copy">
            <Link href={slide.href} className="font-medium text-white hover:underline">{slide.title} <ArrowUpRight aria-hidden="true" className="inline h-4 w-4" /><span className="sr-only"> — {slide.cta}</span></Link>
            <p>{slide.caption}</p>
          </div>
          <div className="hero-carousel-controls">
            <button type="button" onClick={() => go(-1)} aria-label="Previous slide"><ChevronLeft aria-hidden="true" className="h-4 w-4" /></button>
            {heroSlides.map((s, i) => <button key={s.id} type="button" onClick={() => setIndex(i)} aria-label={`Go to slide ${i + 1}: ${s.title}`} aria-current={i === index}><span className={cn("hero-dot", i === index && "hero-dot-active")} /></button>)}
            <button type="button" onClick={() => go(1)} aria-label="Next slide"><ChevronRight aria-hidden="true" className="h-4 w-4" /></button>
            <button type="button" onClick={() => setPlaying(p => !p)} aria-label={playing ? "Pause automatic slide rotation" : "Start automatic slide rotation"}>{playing ? <Pause aria-hidden="true" className="h-3.5 w-3.5" /> : <Play aria-hidden="true" className="h-3.5 w-3.5" />}</button>
          </div>
          <p className="sr-only" aria-live={playing ? "off" : "polite"}>Slide {index + 1} of {heroSlides.length}: {slide.title}</p>
        </div>
        <a href="#about" className="hero-scroll" aria-label="Explore Digi Yatra information"><ArrowDown aria-hidden="true" className="h-5 w-5" /></a>
      </section>
      <section aria-labelledby="highlights-title" className="highlights-strip">
        <div className="mx-auto max-w-[1440px] px-5 py-12 sm:px-8 lg:px-14">
          <h2 id="highlights-title" className="mb-6 text-xl font-semibold text-heading">{t("highlights")}</h2>
          <ul className="grid gap-x-10 gap-y-5 md:grid-cols-2 lg:grid-cols-3">{highlights.map(h => <li key={h.text}><Link href={h.href} className="flex items-start gap-3 text-sm leading-relaxed text-ink-muted hover:text-brand"><ArrowUpRight aria-hidden="true" className="mt-1 h-4 w-4 shrink-0 text-brand" />{h.text}</Link></li>)}</ul>
        </div>
      </section>
    </>
  );
}

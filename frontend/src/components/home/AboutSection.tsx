"use client";

import { ArrowUpRight, Fingerprint, ScanFace, ShieldCheck, Smartphone } from "lucide-react";
import { Section } from "@/components/ui/Section";
import { usePreferences } from "@/lib/accessibility/preferences";
import { aboutFacts, benefits } from "@/content/site";

const FEATURES = [
  { title: "A contactless airport journey", href: "#journey", Icon: ScanFace, style: "verification", detail: "From airport entry to the boarding gate." },
  { title: "Your journey, on your phone", href: "#registration", Icon: Smartphone, style: "mobile-wallet", detail: "One-time enrolment in the official Digi Yatra app." },
  { title: "Privacy stays with you", href: "#privacy", Icon: Fingerprint, style: "privacy-visual", detail: "Your credentials. Your device. Your consent." },
];

export function AboutSection() {
  const { locale } = usePreferences();
  return (
    <Section id="about" labelledBy="about-title">
      <div className="editorial-heading">
        <h2 id="about-title">{locale === "hi" ? <><span>हवाई अड्डों पर</span> सुगम यात्रा।</> : <><span>Driving efficiency</span> in airports.</>}</h2>
        <p>Digi Yatra enables paperless and contactless passenger processing at Indian airports, built on the principle that passengers stay in control of their own data.</p>
      </div>
      <div className="editorial-features">
        {FEATURES.map(({ title, href, Icon, style, detail }) => (
          <a key={title} href={href} className="editorial-feature group">
            <div className={`feature-art ${style}`} aria-hidden="true">
              <div className="feature-art-orbit" /><Icon strokeWidth={0.8} />
              {style === "verification" && <span className="scan-beam" />}
              {style === "mobile-wallet" && <span className="wallet-ticket"><ShieldCheck strokeWidth={1.2} /> Identity &amp; travel</span>}
            </div>
            <h3>{title}<ArrowUpRight aria-hidden="true" className="h-5 w-5 shrink-0 transition-transform group-hover:-translate-y-1 group-hover:translate-x-1" /></h3>
            <p>{detail}</p>
          </a>
        ))}
      </div>
      <div className="about-facts grid gap-8 border-y border-line py-9 md:grid-cols-2">
        {aboutFacts.map(f => <div key={f.title}><h3 className="text-lg font-semibold text-heading">{f.title}</h3><p className="mt-3 text-sm leading-relaxed text-ink-muted">{f.body}</p></div>)}
      </div>
      <h3 className="mb-6 mt-10 text-xl font-semibold text-heading">Benefits for passengers</h3>
      <ul className="grid gap-7 sm:grid-cols-2 lg:grid-cols-4">
        {benefits.map(b => <li key={b.title}><h4 className="font-medium text-heading">{b.title}</h4><p className="mt-2 text-sm leading-relaxed text-ink-muted">{b.body}</p></li>)}
      </ul>
    </Section>
  );
}

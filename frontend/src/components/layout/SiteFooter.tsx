"use client";

import Link from "next/link";
import { LockKeyhole } from "lucide-react";
import { LogoMark } from "@/components/brand/LogoMark";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { usePreferences } from "@/lib/accessibility/preferences";
import { officialLinks } from "@/lib/config";
import { mainNav } from "@/lib/navigation";

export function SiteFooter() {
  const { t } = usePreferences();
  const half = Math.ceil(mainNav.length / 2);

  return (
    <footer className="bg-navy-deep text-white/85">
      <div className="h-1 bg-accent" aria-hidden="true" />
      <div className="mx-auto grid max-w-[1440px] gap-10 px-4 py-12 sm:grid-cols-2 sm:px-6 lg:grid-cols-4 lg:px-8">
        <div>
          <div className="flex items-center gap-3">
            <LogoMark className="h-12 w-12" title="" />
            <div className="leading-tight text-white">
              <p className="font-devanagari font-semibold">डिजी यात्रा सूचना पोर्टल</p>
              <p className="text-sm font-semibold uppercase tracking-wide">Digi Yatra · POC</p>
            </div>
          </div>
          <p className="mt-4 text-sm leading-relaxed">
            An informational proof-of-concept about Digi Yatra — paperless, contactless air travel in India using facial
            verification.
          </p>
        </div>

        <nav aria-label="Footer — sections">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-white">Quick Links</h2>
          <ul className="grid grid-cols-1 gap-2 text-sm">
            {mainNav.slice(0, half).map((item) => (
              <li key={item.key}>
                <Link href={item.href} className="hover:text-white hover:underline">
                  {t(item.key)}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <nav aria-label="Footer — help">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-white">Help</h2>
          <ul className="grid gap-2 text-sm">
            {mainNav.slice(half).map((item) => (
              <li key={item.key}>
                <Link href={item.href} className="hover:text-white hover:underline">
                  {t(item.key)}
                </Link>
              </li>
            ))}
            <li>
              <Link href="/accessibility" className="hover:text-white hover:underline">
                {t("accessibility")}
              </Link>
            </li>
          </ul>
        </nav>

        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-white">Official Resources</h2>
          <ul className="grid gap-2 text-sm">
            <li>
              <ExternalLink href={officialLinks.website} className="text-white/85 hover:text-white">
                Digi Yatra Foundation website
              </ExternalLink>
            </li>
            <li>
              <ExternalLink href={officialLinks.privacyPolicy} className="text-white/85 hover:text-white">
                Privacy Policy
              </ExternalLink>
            </li>
            <li>
              <ExternalLink href={officialLinks.news} className="text-white/85 hover:text-white">
                Official news
              </ExternalLink>
            </li>
            <li>
              <ExternalLink href={officialLinks.contact} className="text-white/85 hover:text-white">
                Contact Digi Yatra Foundation
              </ExternalLink>
            </li>
          </ul>
        </div>
      </div>

      <div className="border-t border-white/15">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-3 px-4 py-5 text-xs leading-relaxed text-white/70 sm:px-6 md:flex-row md:items-center md:justify-between lg:px-8">
          <p className="max-w-3xl">
            <strong className="text-white">Disclaimer:</strong> This is a Proof of Concept (POC) demonstration built for
            evaluation purposes. It is not an official website of the Digi Yatra Foundation, the Ministry of Civil Aviation,
            the DGCA or the Government of India, and implies no endorsement. Always verify information on official channels.
          </p>
          <Link href="/admin/login" className="inline-flex shrink-0 items-center gap-1 text-white/60 hover:text-white">
            <LockKeyhole aria-hidden="true" className="h-3.5 w-3.5" />
            {t("adminLogin")}
          </Link>
        </div>
      </div>
    </footer>
  );
}

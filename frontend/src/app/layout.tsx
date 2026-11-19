import type { Metadata, Viewport } from "next";
import { Noto_Sans, Noto_Sans_Devanagari } from "next/font/google";
import { PreferencesProvider } from "@/lib/accessibility/preferences";
import "./globals.css";

const notoSans = Noto_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-noto-sans", display: "swap" });
const notoDevanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-noto-devanagari",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Digi Yatra Information Portal (POC)", template: "%s | Digi Yatra Portal (POC)" },
  description:
    "Proof-of-concept information portal about Digi Yatra — paperless, contactless air travel in India — with an AI assistant. Not an official website.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#1a2a48",
};

// Applies saved accessibility preferences before first paint (no flash).
const preferencesBootstrap = `try{var p=JSON.parse(localStorage.getItem("dy-poc-preferences")||"{}");var d=document.documentElement;if(p.contrast==="high")d.dataset.contrast="high";if(["sm","md","lg","xl"].indexOf(p.textSize)>-1)d.dataset.textSize=p.textSize;if(p.locale==="hi")d.lang="hi";}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-contrast="normal" data-text-size="md" className={`${notoSans.variable} ${notoDevanagari.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: preferencesBootstrap }} />
      </head>
      <body className="min-h-screen bg-page antialiased">
        <a
          href="#main-content"
          className="sr-only z-[100] rounded bg-surface px-4 py-2 font-medium text-brand shadow-float focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
        >
          Skip to main content
        </a>
        <PreferencesProvider>{children}</PreferencesProvider>
      </body>
    </html>
  );
}

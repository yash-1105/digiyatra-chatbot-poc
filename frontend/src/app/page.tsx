import { AboutSection } from "@/components/home/AboutSection";
import { AirportsSection } from "@/components/home/AirportsSection";
import { FaqSection } from "@/components/home/FaqSection";
import { HeroSection } from "@/components/home/HeroSection";
import { HowItWorksSection } from "@/components/home/HowItWorksSection";
import { JourneySection } from "@/components/home/JourneySection";
import { PrivacySection } from "@/components/home/PrivacySection";
import { RegistrationSection } from "@/components/home/RegistrationSection";
import { SupportSection } from "@/components/home/SupportSection";
import { WelcomeSection } from "@/components/home/WelcomeSection";
import { WhatsNewSection } from "@/components/home/WhatsNewSection";
import { PublicShell } from "@/components/layout/PublicShell";

export default function HomePage() {
  return (
    <PublicShell>
      <HeroSection />
      <WhatsNewSection />
      <WelcomeSection />
      <AboutSection />
      <HowItWorksSection />
      <RegistrationSection />
      <JourneySection />
      <AirportsSection />
      <PrivacySection />
      <FaqSection />
      <SupportSection />
    </PublicShell>
  );
}

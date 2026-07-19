import { Navigation } from "@/components/landing/navigation";
import { HeroSection } from "@/components/landing/hero-section";
import { ArchitectureSection } from "@/components/landing/architecture-section";
import { NoveltySection } from "@/components/landing/novelty-section";
import { FeaturesSection } from "@/components/landing/features-section";
import { HowItWorksSection } from "@/components/landing/how-it-works-section";
import { ComparisonSection } from "@/components/landing/comparison-section";
import { SmeBenefitsSection } from "@/components/landing/sme-benefits-section";
import { SecuritySection } from "@/components/landing/security-section";
import { DevelopersSection } from "@/components/landing/developers-section";
import { CtaSection } from "@/components/landing/cta-section";
import { FooterSection } from "@/components/landing/footer-section";

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-x-hidden">
      <Navigation />
      <HeroSection />
      <ArchitectureSection />
      <NoveltySection />
      <FeaturesSection />
      <HowItWorksSection />
      <ComparisonSection />
      <SmeBenefitsSection />
      <SecuritySection />
      <DevelopersSection />
      <CtaSection />
      <FooterSection />
    </main>
  );
}

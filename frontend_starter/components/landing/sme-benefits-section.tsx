"use client";

import { useEffect, useRef, useState } from "react";
import { Snowflake, Clock3, Landmark, Users } from "lucide-react";

const benefits = [
  {
    icon: Snowflake,
    stat: "Fewer freezes",
    title: "Faster, evidence-backed investigations mean fewer unnecessary account freezes",
    description:
      "Banks often freeze accounts first and investigate later. When an investigation that used to take hours takes minutes and comes with a defensible evidence trail, compliance teams can clear a false positive quickly instead of leaving an account frozen by default — so SMEs don't lose access to payroll, supplier payments, or working capital while a case sits in a queue.",
  },
  {
    icon: Clock3,
    stat: "8 in 10",
    title: "SMEs report onboarding or payment delays from manual compliance review",
    description:
      "The overwhelming majority of the delay is process, not risk — a human working through transaction history, entity relationships, and applicable regulation by hand. Automated evidence assembly and an AI-drafted first pass compress that review from hours to minutes, without lowering the evidentiary bar.",
  },
  {
    icon: Landmark,
    stat: "Hours → minutes",
    title: "Faster AML checks mean faster credit disbursement for SMEs that need it most",
    description:
      "Banks spend significant effort on AML checks before disbursing a loan. When that review compresses from hours to minutes — with a hard evidence gate still in place — SMEs get access to credit at the moment they actually need it, not after a compliance queue clears.",
  },
  {
    icon: Users,
    stat: "Lower cost, more coverage",
    title: "Cheaper compliance means banks serve more SMEs instead of avoiding them",
    description:
      "SMEs with limited financial history or cross-border transactions are often treated as high-risk simply because manual review of their accounts is expensive relative to the revenue they generate. Lowering the cost of a thorough review changes that calculus — encouraging banks to serve more SMEs rather than de-risking them out of the portfolio.",
  },
];

export function SmeBenefitsSection() {
  const [isVisible, setIsVisible] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setIsVisible(true); },
      { threshold: 0.1 }
    );
    if (sectionRef.current) observer.observe(sectionRef.current);
    return () => observer.disconnect();
  }, []);

  return (
    <section id="sme-benefits" ref={sectionRef} className="relative py-24 lg:py-32 overflow-hidden">
      <div className="max-w-[1400px] mx-auto px-6 lg:px-12">
        <div className="mb-16 lg:mb-20 grid lg:grid-cols-12 gap-8 items-end">
          <div className="lg:col-span-7">
            <span className="inline-flex items-center gap-3 text-sm font-mono text-muted-foreground mb-6">
              <span className="w-12 h-px bg-foreground/30" />
              Who this actually helps
            </span>
            <h2 className={`text-6xl md:text-7xl lg:text-[110px] font-display tracking-tight leading-[0.9] transition-all duration-1000 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
              Compliance,
              <br />
              <span className="text-muted-foreground">not collateral damage.</span>
            </h2>
          </div>
          <div className="lg:col-span-5 lg:pb-4">
            <p className={`text-xl text-muted-foreground leading-relaxed transition-all duration-1000 delay-200 ${isVisible ? "opacity-100" : "opacity-0"}`}>
              Slow, manual AML review doesn&apos;t just cost banks time — it costs SMEs
              working capital, credit access, and market access. Faster, evidence-backed
              investigation changes that on both sides of the relationship.
            </p>
          </div>
        </div>

        <div className="grid lg:grid-cols-2 gap-4 lg:gap-6">
          {benefits.map((b, i) => (
            <div
              key={b.title}
              className={`relative border border-foreground/10 bg-foreground/[0.02] p-8 lg:p-10 transition-all duration-700 hover:border-foreground/25 hover:bg-foreground/[0.04] ${
                isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-12"
              }`}
              style={{ transitionDelay: `${i * 80}ms` }}
            >
              <div className="flex items-center justify-between mb-6">
                <div className="w-10 h-10 rounded-lg bg-foreground/[0.06] flex items-center justify-center">
                  <b.icon className="w-5 h-5 text-foreground/70" />
                </div>
                <span className="font-mono text-sm text-muted-foreground">{b.stat}</span>
              </div>
              <h3 className="text-xl lg:text-2xl font-display leading-snug mb-4">{b.title}</h3>
              <p className="text-sm lg:text-base text-muted-foreground leading-relaxed">{b.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

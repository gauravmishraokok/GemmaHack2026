"use client";

import { useEffect, useRef, useState } from "react";

const steps = [
  {
    number: "01",
    title: "Assemble",
    subtitle: "the evidence",
    description: "Timeline, entity relationships (shared PAN, repeat beneficiary, circular flow), KYC flags, rule alerts, and regulation citations are built deterministically from the case — before any model runs.",
    code: `EV-041 linked_pan: PAN-TUOTE8885C
  30 accounts, 1 beneficial owner
EV-044 velocity: 14 txns / 48h
  totalling ₹48,79,976
EV-049 kyc_flag: 19 accounts
  FAILED KYC, Shell Company`,
  },
  {
    number: "02",
    title: "Gate",
    subtitle: "on sufficiency",
    description: "A hard, deterministic check: at least 3 transactions, at least 1 relationship, at least 1 regulation citation, every item source-traceable. Fail any one and the pipeline stops — no STR is ever drafted on thin evidence.",
    code: `validate(pack) -> (ok, missing)

if not ok:
  return INSUFFICIENT_EVIDENCE
  # str_draft stays null`,
  },
  {
    number: "03",
    title: "Reason",
    subtitle: "under constraint",
    description: "Gemma runs a single evidence-first pass, schema-constrained: evidence review, pattern, sufficiency, summary, questions, ground-of-suspicion tag, and narration must be produced in that structural order — and only within a closed vocabulary.",
    code: `response_format: {
  type: "json_schema",
  schema: INVESTIGATION_SCHEMA
}
# gos_tag: 1 of 8 closed values`,
  },
  {
    number: "04",
    title: "Verify",
    subtitle: "& score",
    description: "Every cited amount and EV-id is checked against the real ledger. Token logprobs are fused with that grounding check into a per-sentence confidence — a hallucinated figure is capped red no matter how fluent the sentence reads.",
    code: `confidence = lm_conf *
  (0.4 + 0.6 * grounding_score)

if amount not in ledger:
  band = "red"  # forced`,
  },
];

export function HowItWorksSection() {
  const [activeStep, setActiveStep] = useState(0);
  const [isVisible, setIsVisible] = useState(false);
  const sectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setIsVisible(true);
      },
      { threshold: 0.1 }
    );

    if (sectionRef.current) observer.observe(sectionRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveStep((prev) => (prev + 1) % steps.length);
    }, 6000);
    return () => clearInterval(interval);
  }, []);

  return (
    <section
      id="how-it-works"
      ref={sectionRef}
      className="relative py-24 lg:py-32 bg-[oklch(0.09_0.01_260)] text-white overflow-hidden"
    >
      <div className="absolute bottom-0 left-0 w-[400px] h-[400px] rounded-full bg-white/[0.02] blur-[100px] pointer-events-none" />

      <div className="relative z-10 max-w-[1400px] mx-auto px-6 lg:px-12">
        <div className="mb-16 lg:mb-20">
          <div className={`transition-all duration-1000 ${isVisible ? "translate-x-0 opacity-100" : "-translate-x-12 opacity-0"}`}>
            <span className="inline-flex items-center gap-3 text-sm font-mono text-white/40 mb-8">
              <span className="w-12 h-px bg-white/20" />
              Process
            </span>
          </div>

          <h2 className={`text-6xl md:text-7xl lg:text-[110px] font-display tracking-tight leading-[0.9] transition-all duration-1000 delay-100 ${
            isVisible ? "translate-y-0 opacity-100" : "translate-y-16 opacity-0"
          }`}>
            <span className="block">Assemble. Gate.</span>
            <span className="block text-white/30">Reason. Verify.</span>
          </h2>
        </div>

        {/* Horizontal Steps Layout */}
        <div className="grid lg:grid-cols-4 gap-4">
          {steps.map((step, index) => (
            <button
              key={step.number}
              type="button"
              onClick={() => setActiveStep(index)}
              className={`relative text-left p-6 lg:p-8 border transition-all duration-500 ${
                activeStep === index
                  ? "bg-[#000000] border-white/60"
                  : "bg-[#000000] border-white/25 hover:border-white/50"
              }`}
            >
              <div className="flex items-center gap-4 mb-6">
                <span className={`text-3xl font-display transition-colors duration-300 ${
                  activeStep === index ? "text-[#ec835a]" : "text-white/20"
                }`}>
                  {step.number}
                </span>
                <div className="flex-1 h-px bg-white/10 overflow-hidden">
                  {activeStep === index && (
                    <div className="h-full bg-[#ec835a]/50 animate-progress" />
                  )}
                </div>
              </div>

              <h3 className="text-2xl lg:text-3xl font-display mb-1">
                {step.title}
              </h3>
              <span className="text-lg text-white/40 font-display block mb-4">
                {step.subtitle}
              </span>

              <p className={`text-sm text-white/60 leading-relaxed transition-opacity duration-300 mb-4 ${
                activeStep === index ? "opacity-100" : "opacity-60"
              }`}>
                {step.description}
              </p>

              <pre className="font-mono text-[10px] leading-relaxed text-white/30 bg-white/[0.03] p-3 rounded overflow-x-auto whitespace-pre">
                {step.code}
              </pre>

              <div className={`absolute bottom-0 left-0 right-0 h-1 bg-[#ec835a] transition-transform duration-500 origin-left ${
                activeStep === index ? "scale-x-100" : "scale-x-0"
              }`} />
            </button>
          ))}
        </div>
      </div>

      <style jsx>{`
        @keyframes progress {
          from { width: 0%; }
          to { width: 100%; }
        }
        .animate-progress {
          animation: progress 6s linear forwards;
        }
      `}</style>
    </section>
  );
}

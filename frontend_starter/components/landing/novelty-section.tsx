"use client";

import { useEffect, useRef, useState } from "react";
import { Activity, Lock, Gauge } from "lucide-react";

const capabilities = [
  {
    icon: Activity,
    number: "01",
    title: "Activation probing, not prompting",
    subtitle: "risk scoring",
    color: "#3987e5",
    description:
      "A trained linear probe reads Gemma's own hidden-state representation of a case — output_hidden_states=True, mean-pooled at the middle transformer layer, reduced with PCA(64), classified with LogisticRegressionCV. The model isn't asked to self-report a risk score in text; its internal representation is read directly.",
    why: "Only possible with local weights. A cloud completion endpoint returns text — it never exposes hidden states.",
    metric: { value: "0.905", label: "probe AUROC vs. 0.879 XGBoost, 0.377 rule-count" },
  },
  {
    icon: Lock,
    number: "02",
    title: "Schema-constrained decoding",
    subtitle: "the STR draft",
    color: "#ec835a",
    description:
      "The ground-of-suspicion tag, the evidence-then-conclusion ordering, and the full JSON shape of the investigation are enforced at the decoding level. Ollama compiles the JSON schema into a token-level grammar — an invalid tag isn't filtered after generation, it's a byte sequence the sampler cannot produce.",
    why: "Structurally impossible to reproduce with a hosted API that only exposes a finished completion, no control over the sampler.",
    metric: { value: "8", label: "closed ground-of-suspicion tags — nothing else is reachable" },
  },
  {
    icon: Gauge,
    number: "03",
    title: "Token logprobs → confidence heat-map",
    subtitle: "trust layer",
    color: "#d03b3b",
    description:
      "Every STR sentence is scored by the mean of its own generation-time token logprobs, exponentiated into a 0–1 confidence, then discounted by an independent deterministic check: every cited amount and evidence reference is verified against the actual ledger. A fluent sentence citing an unverifiable figure is still forced red.",
    why: "Per-token probabilities are a local-inference primitive. A hosted chat API gives you the words, not the model's belief in each one.",
    metric: { value: "0", label: "amount violations after grounding — a hallucinated figure can't render green" },
  },
];

export function NoveltySection() {
  const [isVisible, setIsVisible] = useState(false);
  const [active, setActive] = useState(0);
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
    <section id="novelty" ref={sectionRef} className="relative py-24 lg:py-32 overflow-hidden">
      <div className="max-w-[1400px] mx-auto px-6 lg:px-12">
        <div className="grid lg:grid-cols-12 gap-8 items-end mb-16 lg:mb-20">
          <div className="lg:col-span-7">
            <span className="inline-flex items-center gap-3 text-sm font-mono text-muted-foreground mb-6">
              <span className="w-12 h-px bg-foreground/30" />
              Why local Gemma, specifically
            </span>
            <h2 className={`text-6xl md:text-7xl lg:text-[110px] font-display tracking-tight leading-[0.9] transition-all duration-1000 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
              Not a
              <br />
              <span className="text-muted-foreground">convenience.</span>
            </h2>
          </div>
          <div className="lg:col-span-5 lg:pb-4">
            <p className={`text-xl text-muted-foreground leading-relaxed transition-all duration-1000 delay-200 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`}>
              RBI data-localization and India&apos;s DPDP Act mean customer data legally
              cannot reach a third-party API. But even without that constraint, three
              things this system depends on only exist when the weights are on your
              own machine.
            </p>
          </div>
        </div>

        <div className="grid lg:grid-cols-12 gap-4 lg:gap-6">
          {/* Selector column */}
          <div className="lg:col-span-4 flex lg:flex-col gap-3 overflow-x-auto lg:overflow-visible pb-2 lg:pb-0">
            {capabilities.map((cap, i) => (
              <button
                key={cap.number}
                onClick={() => setActive(i)}
                className={`shrink-0 lg:shrink text-left p-5 border transition-all duration-300 w-[260px] lg:w-auto ${
                  active === i ? "border-foreground/40 bg-foreground/[0.04]" : "border-foreground/10 hover:border-foreground/20"
                }`}
              >
                <div className="flex items-center gap-3 mb-2">
                  <div
                    className="w-8 h-8 rounded-md flex items-center justify-center shrink-0"
                    style={{ background: active === i ? `${cap.color}22` : "transparent", color: active === i ? cap.color : undefined }}
                  >
                    <cap.icon className="w-4 h-4" />
                  </div>
                  <span className="font-mono text-xs text-muted-foreground">{cap.number}</span>
                </div>
                <h3 className="font-medium text-sm leading-tight">{cap.title}</h3>
                <span className="text-xs text-muted-foreground">{cap.subtitle}</span>
              </button>
            ))}
          </div>

          {/* Detail panel */}
          <div className="lg:col-span-8">
            <div
              key={active}
              className="border border-foreground/10 bg-foreground/[0.02] p-8 lg:p-12 min-h-[380px] flex flex-col justify-between animate-in fade-in duration-500"
            >
              <div>
                <span className="font-mono text-xs uppercase tracking-wider" style={{ color: capabilities[active].color }}>
                  {capabilities[active].subtitle}
                </span>
                <h3 className="text-3xl lg:text-4xl font-display mt-3 mb-6">{capabilities[active].title}</h3>
                <p className="text-lg text-muted-foreground leading-relaxed max-w-2xl mb-6">
                  {capabilities[active].description}
                </p>
                <div className="border-l-2 pl-4" style={{ borderColor: capabilities[active].color }}>
                  <p className="text-sm text-foreground/70 leading-relaxed max-w-xl">
                    <span className="font-medium">Why this needs local weights: </span>
                    {capabilities[active].why}
                  </p>
                </div>
              </div>
              <div className="mt-10 pt-6 border-t border-foreground/10">
                <span className="text-4xl lg:text-5xl font-display">{capabilities[active].metric.value}</span>
                <span className="block text-sm text-muted-foreground font-mono mt-2">{capabilities[active].metric.label}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

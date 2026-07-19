"use client";

import { useEffect, useRef, useState } from "react";
import { Database, GitBranch, ShieldCheck, FileCheck2 } from "lucide-react";

const planes = [
  {
    id: "batch",
    label: "Batch plane · :8001",
    title: "Data & Intelligence Engine",
    icon: Database,
    color: "#3987e5",
    stages: [
      { name: "Ingestion", detail: "IBM AML dataset + synthetic KYC/PAN, ring-preserving sampling" },
      { name: "Rule engine", detail: "velocity (5 txns/48h) · threshold (₹4.7L–25L windows) · structuring" },
      { name: "XGBoost refine", detail: "17-feature transaction classifier, AUROC 0.934 on 1M+ held-out rows" },
      { name: "Graph + Louvain", detail: "transaction-only graph clustered into cases — identity edges excluded" },
      { name: "Gemma activation probe", detail: "mean-pooled hidden states → PCA(64) → LogisticRegressionCV → risk p" },
    ],
  },
  {
    id: "interactive",
    label: "Interactive plane · :8002",
    title: "Reasoning & Evidence Product",
    icon: GitBranch,
    color: "#ec835a",
    stages: [
      { name: "Evidence pack", detail: "timeline, relationships, KYC flags, rule alerts, regulation citations" },
      { name: "Hard gate", detail: "≥3 txns, ≥1 relationship, ≥1 citation — else INSUFFICIENT_EVIDENCE, no draft" },
      { name: "Gemma reasoning", detail: "single pass, schema-constrained decoding — gos_tag physically unreachable if invalid" },
      { name: "Grounding check", detail: "every cited amount + EV-id verified against the real ledger" },
      { name: "Confidence fusion", detail: "token logprobs × grounding → per-sentence green/yellow/red heat-map" },
    ],
  },
];

function StageRow({
  stage,
  color,
  index,
  active,
  onHover,
}: {
  stage: { name: string; detail: string };
  color: string;
  index: number;
  active: boolean;
  onHover: () => void;
}) {
  return (
    <div
      onMouseEnter={onHover}
      className={`group relative pl-8 py-4 border-l transition-all duration-300 cursor-default ${
        active ? "border-l-[3px]" : "border-l"
      }`}
      style={{ borderColor: active ? color : "rgba(255,255,255,0.12)" }}
    >
      <span
        className="absolute -left-[7px] top-5 w-3 h-3 rounded-full transition-all duration-300"
        style={{
          background: active ? color : "rgba(255,255,255,0.25)",
          boxShadow: active ? `0 0 0 4px ${color}22` : "none",
        }}
      />
      <div className="flex items-baseline gap-3">
        <span className="font-mono text-xs text-white/30">{String(index + 1).padStart(2, "0")}</span>
        <h4 className={`font-medium transition-colors ${active ? "text-white" : "text-white/70"}`}>
          {stage.name}
        </h4>
      </div>
      <p className="text-sm text-white/40 mt-1 leading-relaxed">{stage.detail}</p>
    </div>
  );
}

export function ArchitectureSection() {
  const [isVisible, setIsVisible] = useState(false);
  const [activeStage, setActiveStage] = useState<Record<string, number>>({ batch: 0, interactive: 0 });
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
    <section id="architecture" ref={sectionRef} className="relative py-24 lg:py-32 bg-black text-white overflow-hidden">
      <div className="max-w-[1400px] mx-auto px-6 lg:px-12">
        <div className="mb-20">
          <span className={`inline-flex items-center gap-3 text-sm font-mono text-white/40 mb-6 transition-all duration-700 ${isVisible ? "opacity-100" : "opacity-0"}`}>
            <span className="w-12 h-px bg-white/20" />
            Architecture
          </span>
          <h2 className={`text-6xl md:text-7xl lg:text-[110px] font-display tracking-tight leading-[0.9] mb-8 transition-all duration-1000 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
            Two planes,
            <br />
            <span className="text-white/30">one contract.</span>
          </h2>
          <p className={`text-xl text-white/50 leading-relaxed max-w-2xl transition-all duration-1000 delay-100 ${isVisible ? "opacity-100" : "opacity-0"}`}>
            A batch plane turns raw transactions into risk-scored cases. An interactive
            plane turns a case into a defensible, filing-ready report. Both are built by
            different people against one frozen Pydantic contract — <code className="font-mono text-white/70">shared_contracts.py</code> —
            so they merge without breaking each other.
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-6 lg:gap-8">
          {planes.map((plane) => (
            <div
              key={plane.id}
              className={`relative border border-white/10 bg-white/[0.02] p-8 lg:p-10 transition-all duration-700 ${
                isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-12"
              }`}
            >
              <div className="flex items-center gap-3 mb-2">
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: `${plane.color}1a`, color: plane.color }}
                >
                  <plane.icon className="w-4 h-4" />
                </div>
                <span className="font-mono text-xs text-white/40">{plane.label}</span>
              </div>
              <h3 className="text-2xl lg:text-3xl font-display mb-6">{plane.title}</h3>

              <div className="flex flex-col">
                {plane.stages.map((stage, i) => (
                  <StageRow
                    key={stage.name}
                    stage={stage}
                    color={plane.color}
                    index={i}
                    active={activeStage[plane.id] === i}
                    onHover={() => setActiveStage((s) => ({ ...s, [plane.id]: i }))}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Trust layer strip beneath both planes */}
        <div className={`mt-6 lg:mt-8 grid sm:grid-cols-2 gap-4 transition-all duration-700 delay-300 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <div className="border border-white/10 bg-white/[0.02] p-6 flex items-start gap-4">
            <ShieldCheck className="w-5 h-5 text-[#0ca30c] shrink-0 mt-0.5" />
            <div>
              <h4 className="font-medium mb-1">Human review layer</h4>
              <p className="text-sm text-white/40">Model drafts, evidence gates, a human attests. Nothing is filed automatically.</p>
            </div>
          </div>
          <div className="border border-white/10 bg-white/[0.02] p-6 flex items-start gap-4">
            <FileCheck2 className="w-5 h-5 text-[#3987e5] shrink-0 mt-0.5" />
            <div>
              <h4 className="font-medium mb-1">Hash-chained audit log</h4>
              <p className="text-sm text-white/40">Every evidence build, investigation, and export is appended, tamper-evident, verifiable on demand.</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

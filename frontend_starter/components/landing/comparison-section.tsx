"use client";

import { useEffect, useRef, useState } from "react";
import { Check, X, Minus } from "lucide-react";

type Cell = { state: "yes" | "no" | "partial"; note?: string };

const rows: { label: string; cells: [Cell, Cell, Cell, Cell] }[] = [
  {
    label: "Data stays on-premise",
    cells: [
      { state: "yes", note: "air-gapped by design" },
      { state: "yes" },
      { state: "no", note: "customer data leaves the building" },
      { state: "yes" },
    ],
  },
  {
    label: "False-positive rate",
    cells: [
      { state: "yes", note: "learned boundary + evidence gate" },
      { state: "no", note: "90%+ on rigid thresholds" },
      { state: "partial", note: "vendor-dependent, still cloud-bound" },
      { state: "yes", note: "but doesn't scale" },
    ],
  },
  {
    label: "Explainable, evidence-linked output",
    cells: [
      { state: "yes", note: "every claim cites an EV-id" },
      { state: "partial", note: "rule name only, no narrative" },
      { state: "partial", note: "opaque model, no logprobs exposed" },
      { state: "yes", note: "human-written" },
    ],
  },
  {
    label: "Structurally invalid output impossible",
    cells: [
      { state: "yes", note: "schema-constrained decoding" },
      { state: "no" },
      { state: "no", note: "post-hoc filtering at best" },
      { state: "partial", note: "depends on the analyst" },
    ],
  },
  {
    label: "Per-claim confidence signal",
    cells: [
      { state: "yes", note: "token logprobs × grounding" },
      { state: "no" },
      { state: "no", note: "APIs don't expose logprobs this way" },
      { state: "no" },
    ],
  },
  {
    label: "Investigation time per case",
    cells: [
      { state: "yes", note: "minutes" },
      { state: "partial", note: "fast, but noisy" },
      { state: "partial", note: "minutes, cloud round-trip" },
      { state: "no", note: "hours" },
    ],
  },
  {
    label: "Affordable for a small NBFC / co-op bank",
    cells: [
      { state: "yes", note: "runs on hardware they own" },
      { state: "yes" },
      { state: "no", note: "per-seat/per-call enterprise pricing" },
      { state: "yes", note: "but doesn't scale with volume" },
    ],
  },
];

const columns = ["viGEMMAlya", "Rule engines", "Cloud AML SaaS", "Manual review"];

function StateIcon({ state }: { state: Cell["state"] }) {
  if (state === "yes") return <Check className="w-4 h-4 text-[#0ca30c]" />;
  if (state === "no") return <X className="w-4 h-4 text-[#d03b3b]" />;
  return <Minus className="w-4 h-4 text-[#fab219]" />;
}

export function ComparisonSection() {
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
    // "dark" class pins dark tokens: this band is deliberately dark in both themes
    <section id="comparison" ref={sectionRef} className="dark relative py-24 lg:py-32 bg-[oklch(0.09_0.01_260)] overflow-hidden">
      <div className="max-w-[1400px] mx-auto px-6 lg:px-12">
        <div className="mb-16">
          <span className={`inline-flex items-center gap-3 text-sm font-mono text-muted-foreground mb-6 transition-all duration-700 ${isVisible ? "opacity-100" : "opacity-0"}`}>
            <span className="w-12 h-px bg-foreground/30" />
            Competitive analysis
          </span>
          <h2 className={`text-6xl md:text-7xl lg:text-[110px] font-display tracking-tight leading-[0.9] mb-8 transition-all duration-1000 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
            The gap
            <br />
            <span className="text-muted-foreground">nobody filled.</span>
          </h2>
          <p className={`text-xl text-muted-foreground leading-relaxed max-w-2xl transition-all duration-1000 delay-100 ${isVisible ? "opacity-100" : "opacity-0"}`}>
            Rule engines are cheap but noisy. Cloud AML SaaS is capable but legally
            off-limits for on-prem-only data. Manual review is defensible but doesn&apos;t
            scale. Small NBFCs and co-op banks have been stuck choosing between the three.
          </p>
        </div>

        <div className={`overflow-x-auto transition-all duration-1000 delay-200 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <table className="w-full min-w-[720px] border-collapse">
            <thead>
              <tr>
                <th className="text-left py-4 pr-6 text-sm text-muted-foreground font-normal align-bottom w-[240px]">
                  &nbsp;
                </th>
                {columns.map((col, i) => (
                  <th
                    key={col}
                    className={`text-left py-4 px-4 align-bottom ${i === 0 ? "bg-foreground/[0.04] rounded-t-lg" : ""}`}
                  >
                    <span className={`font-display text-xl ${i === 0 ? "text-foreground" : "text-muted-foreground"}`}>
                      {col}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={row.label} className="border-t border-foreground/10">
                  <td className="py-4 pr-6 text-sm text-foreground/80">{row.label}</td>
                  {row.cells.map((cell, ci) => (
                    <td
                      key={ci}
                      className={`py-4 px-4 ${ci === 0 ? "bg-foreground/[0.04]" : ""} ${ri === rows.length - 1 && ci === 0 ? "rounded-b-lg" : ""}`}
                    >
                      <div className="flex items-center gap-2">
                        <StateIcon state={cell.state} />
                        {cell.note && <span className="text-xs text-muted-foreground">{cell.note}</span>}
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className={`mt-8 text-sm text-muted-foreground max-w-2xl transition-all duration-700 delay-300 ${isVisible ? "opacity-100" : "opacity-0"}`}>
          Measured, not asserted: XGBoost baseline AUROC 0.934 on 1M+ held-out IBM AML
          transactions; the Gemma-derived risk probe beats both the XGBoost aggregate
          (0.879 AUROC) and a naive rule-count baseline (0.377 AUROC) on the same
          held-out split — reported honestly either way, per the model comparison chart
          this system ships with.
        </p>
      </div>
    </section>
  );
}

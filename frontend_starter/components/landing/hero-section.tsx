"use client";

import { useEffect, useState, useRef } from "react";

const words = ["investigate", "reason", "verify", "file"];

function BlurWord({ word, trigger }: { word: string; trigger: number }) {
  const letters = word.split("");
  const STAGGER = 45;
  const DURATION = 500;
  const GRADIENT_HOLD = STAGGER * letters.length + DURATION + 200;

  const [letterStates, setLetterStates] = useState<{ opacity: number; blur: number }[]>(
    letters.map(() => ({ opacity: 0, blur: 20 }))
  );
  const [showGradient, setShowGradient] = useState(true);
  const framesRef = useRef<number[]>([]);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    framesRef.current.forEach(cancelAnimationFrame);
    timersRef.current.forEach(clearTimeout);
    framesRef.current = [];
    timersRef.current = [];

    setLetterStates(letters.map(() => ({ opacity: 0, blur: 20 })));
    setShowGradient(true);

    letters.forEach((_, i) => {
      const t = setTimeout(() => {
        const start = performance.now();
        const tick = (now: number) => {
          const progress = Math.min((now - start) / DURATION, 1);
          const eased = 1 - Math.pow(1 - progress, 3);
          setLetterStates(prev => {
            const next = [...prev];
            next[i] = { opacity: eased, blur: 20 * (1 - eased) };
            return next;
          });
          if (progress < 1) {
            const id = requestAnimationFrame(tick);
            framesRef.current.push(id);
          }
        };
        const id = requestAnimationFrame(tick);
        framesRef.current.push(id);
      }, i * STAGGER);
      timersRef.current.push(t);
    });

    const gt = setTimeout(() => setShowGradient(false), GRADIENT_HOLD);
    timersRef.current.push(gt);

    return () => {
      framesRef.current.forEach(cancelAnimationFrame);
      timersRef.current.forEach(clearTimeout);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trigger]);

  // amber/red gradient — reads as "risk", not decorative rainbow
  const gradientColors = ["#fab219", "#ec835a", "#d03b3b", "#ec835a", "#fab219"];

  return (
    <>
      {letters.map((char, i) => {
        const colorIndex = (i / Math.max(letters.length - 1, 1)) * (gradientColors.length - 1);
        const lower = Math.floor(colorIndex);
        const upper = Math.min(lower + 1, gradientColors.length - 1);
        const t = colorIndex - lower;

        const hex2rgb = (hex: string) => {
          const r = parseInt(hex.slice(1, 3), 16);
          const g = parseInt(hex.slice(3, 5), 16);
          const b = parseInt(hex.slice(5, 7), 16);
          return [r, g, b];
        };
        const [r1, g1, b1] = hex2rgb(gradientColors[lower]);
        const [r2, g2, b2] = hex2rgb(gradientColors[upper]);
        const r = Math.round(r1 + (r2 - r1) * t);
        const g = Math.round(g1 + (g2 - g1) * t);
        const b = Math.round(b1 + (b2 - b1) * t);

        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              opacity: letterStates[i]?.opacity ?? 0,
              filter: `blur(${letterStates[i]?.blur ?? 20}px)`,
              color: showGradient ? `rgb(${r},${g},${b})` : "white",
              transition: "color 0.4s ease",
            }}
          >
            {char}
          </span>
        );
      })}
    </>
  );
}

/* Case graph visualization: nodes (accounts) linked by SENT/LINKED_PAN edges,
   drifting gently, with a slow pulse on the highest-risk node — the same
   visual grammar as the product's own relationship graph, not stock footage. */
function CaseGraphCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    type Node = { x: number; y: number; bx: number; by: number; risk: number; phase: number };
    const NODE_COUNT = 22;
    const nodes: Node[] = Array.from({ length: NODE_COUNT }, (_, i) => {
      const seed = i * 2.399;
      return {
        bx: (seed * 127.1) % 1,
        by: (seed * 311.7) % 1,
        x: 0,
        y: 0,
        risk: i % 7 === 0 ? 0.9 : i % 3 === 0 ? 0.5 : 0.15,
        phase: seed * Math.PI * 2,
      };
    });
    // ring + cross edges — mirrors real structuring/funnel topology
    const edges: [number, number][] = [];
    for (let i = 0; i < NODE_COUNT; i++) edges.push([i, (i + 1) % NODE_COUNT]);
    for (let i = 0; i < NODE_COUNT; i += 4) edges.push([i, (i + 7) % NODE_COUNT]);
    for (let i = 0; i < NODE_COUNT; i += 5) edges.push([i, (i + 11) % NODE_COUNT]);

    let time = 0;
    const render = () => {
      const rect = canvas.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;
      ctx.clearRect(0, 0, w, h);

      nodes.forEach((n) => {
        n.x = n.bx * w + Math.sin(time * 0.15 + n.phase) * 14;
        n.y = n.by * h + Math.cos(time * 0.12 + n.phase * 0.8) * 14;
      });

      edges.forEach(([a, b]) => {
        const na = nodes[a], nb = nodes[b];
        ctx.beginPath();
        ctx.moveTo(na.x, na.y);
        ctx.lineTo(nb.x, nb.y);
        ctx.strokeStyle = "rgba(255,255,255,0.06)";
        ctx.lineWidth = 1;
        ctx.stroke();
      });

      nodes.forEach((n) => {
        const pulse = Math.sin(time * 1.4 + n.phase) * 0.5 + 0.5;
        const color =
          n.risk > 0.8 ? `rgba(211,59,59,${0.55 + pulse * 0.35})` :
          n.risk > 0.35 ? `rgba(250,178,25,${0.4 + pulse * 0.2})` :
          `rgba(255,255,255,${0.25 + pulse * 0.1})`;
        const r = n.risk > 0.8 ? 4.5 : n.risk > 0.35 ? 3.2 : 2.2;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        if (n.risk > 0.8) {
          ctx.beginPath();
          ctx.arc(n.x, n.y, r + 6 + pulse * 4, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(211,59,59,${0.25 * (1 - pulse)})`;
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      });

      time += 0.016;
      frameRef.current = requestAnimationFrame(render);
    };
    render();

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(frameRef.current);
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" aria-hidden="true" />;
}

export function HeroSection() {
  const [isVisible, setIsVisible] = useState(false);
  const [wordIndex, setWordIndex] = useState(0);

  useEffect(() => {
    setIsVisible(true);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setWordIndex((prev) => (prev + 1) % words.length);
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  return (
    <section className="relative min-h-screen flex flex-col justify-center items-start overflow-hidden bg-black">
      {/* Live case-graph visualization instead of stock video */}
      <div className="absolute inset-0 z-0">
        <CaseGraphCanvas />
        <div className="absolute inset-0 bg-gradient-to-r from-black/85 via-black/50 to-black/20" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/30 via-transparent to-black/70" />
      </div>

      {/* Subtle grid lines */}
      <div className="absolute inset-0 z-[2] overflow-hidden pointer-events-none opacity-20">
        {[...Array(8)].map((_, i) => (
          <div
            key={`h-${i}`}
            className="absolute h-px bg-white/10"
            style={{ top: `${12.5 * (i + 1)}%`, left: 0, right: 0 }}
          />
        ))}
        {[...Array(12)].map((_, i) => (
          <div
            key={`v-${i}`}
            className="absolute w-px bg-white/10"
            style={{ left: `${8.33 * (i + 1)}%`, top: 0, bottom: 0 }}
          />
        ))}
      </div>

      <div className="relative z-10 w-full max-w-[1400px] mx-auto px-6 lg:px-12 py-32 lg:py-40">
        <div className="lg:max-w-[62%]">
          <div
            className={`mb-8 transition-all duration-700 ${
              isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
            }`}
          >
            <span className="inline-flex items-center gap-3 text-sm font-mono text-white/60">
              <span className="w-8 h-px bg-white/30" />
              Air-gapped AML co-investigator · Track 2, Build with Gemma
            </span>
          </div>

          <div className="mb-10">
            <h1
              className={`text-left text-[clamp(2rem,5.6vw,6.5rem)] font-display leading-[0.95] tracking-tight text-white transition-all duration-1000 ${
                isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
              }`}
            >
              <span className="block">Hundreds of alerts,</span>
              <span className="block">
                a local Gemma helps you{" "}
                <span className="relative inline-block">
                  <BlurWord word={words[wordIndex]} trigger={wordIndex} />
                </span>
              </span>
            </h1>
          </div>

          <p
            className={`text-lg text-white/60 leading-relaxed max-w-xl mb-4 transition-all duration-1000 delay-200 ${
              isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
            }`}
          >
            viGEMMAlya clusters raw transactions into investigable cases, reconstructs
            each case&apos;s evidence, and reasons over it with a locally-run Gemma model
            under schema-constrained decoding — drafting a filing-ready STR whose every
            sentence is scored by the model&apos;s own confidence. No customer data ever
            leaves the building.
          </p>
        </div>
      </div>

      {/* Real, measured stats — not filler counters */}
      <div
        className={`absolute bottom-12 left-0 right-0 px-6 lg:px-12 transition-all duration-700 delay-500 ${
          isVisible ? "opacity-100" : "opacity-0"
        }`}
      >
        <div className="max-w-[1400px] mx-auto flex flex-wrap items-start gap-10 lg:gap-20">
          {[
            { value: "1,217", label: "cases from 100k raw transactions (Louvain clustering)" },
            { value: "0.934", label: "XGBoost AUROC on 1M+ held-out transactions" },
            { value: "100%", label: "customer data stays on-premise" },
          ].map((stat) => (
            <div key={stat.label} className="flex flex-col gap-2 max-w-[220px]">
              <span className="text-3xl lg:text-4xl font-display text-white">{stat.value}</span>
              <span className="text-xs text-white/50 leading-tight">{stat.label}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

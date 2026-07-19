"use client";

import { ArrowUpRight } from "lucide-react";
import { useEffect, useRef } from "react";

const footerLinks = {
  Product: [
    { name: "Architecture", href: "#architecture" },
    { name: "Novelty", href: "#novelty" },
    { name: "How it works", href: "#how-it-works" },
    { name: "Comparison", href: "#comparison" },
  ],
  Product2: [
    { name: "SME benefits", href: "#sme-benefits" },
    { name: "Live pipeline", href: "/pipeline" },
    { name: "API surface", href: "#developers" },
    { name: "Security", href: "#security" },
  ],
  Compliance: [
    { name: "PMLA 2002", href: "#" },
    { name: "RBI KYC Master Direction", href: "#" },
    { name: "FIU-IND STR Guidance", href: "#" },
  ],
  Track: [
    { name: "Build with Gemma", href: "#" },
    { name: "Track 2 — Compliance & Risk", href: "#" },
  ],
};

function AnimatedGraphCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationId: number;
    let time = 0;

    const resize = () => {
      canvas.width = canvas.offsetWidth * window.devicePixelRatio;
      canvas.height = canvas.offsetHeight * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };
    resize();
    window.addEventListener("resize", resize);

    const animate = () => {
      const width = canvas.offsetWidth;
      const height = canvas.offsetHeight;
      ctx.clearRect(0, 0, width, height);

      ctx.strokeStyle = "rgba(150, 160, 200, 0.15)";
      ctx.lineWidth = 1;

      for (let wave = 0; wave < 3; wave++) {
        ctx.beginPath();
        for (let x = 0; x <= width; x += 6) {
          const y =
            height * 0.5 +
            Math.sin(x * 0.008 + time + wave * 0.6) * 26 +
            Math.sin(x * 0.018 + time * 1.3 + wave) * 16;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      time += 0.015;
      animationId = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animationId);
    };
  }, []);

  return <canvas ref={canvasRef} className="w-full h-full" />;
}

export function FooterSection() {
  return (
    <footer className="relative bg-black">
      <div className="relative w-full h-[220px] md:h-[280px] overflow-hidden border-b border-white/5">
        <AnimatedGraphCanvas />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-black" />
      </div>

      <div className="relative z-10 max-w-[1400px] mx-auto px-6 lg:px-12">
        <div className="py-16 lg:py-20">
          <div className="grid grid-cols-2 md:grid-cols-6 gap-12 lg:gap-8">
            <div className="col-span-2">
              <a href="#" className="inline-flex items-center gap-2 mb-6">
                <span className="inline-block w-2 h-2 rounded-full bg-[#e34948]" aria-hidden="true" />
                <span className="text-2xl font-display text-white">viGEMMAlya</span>
                <span className="text-xs text-white/40 font-mono">AML</span>
              </a>

              <p className="text-white/50 leading-relaxed mb-8 max-w-xs text-sm">
                An air-gapped AML co-investigator for small NBFCs and co-operative
                banks. Built for Track 2 of the Build with Gemma: Bengaluru AI Sprint.
              </p>

              <div className="flex gap-6">
                <a
                  href="/pipeline"
                  className="text-sm text-white/40 hover:text-white transition-colors flex items-center gap-1 group"
                >
                  Live pipeline
                  <ArrowUpRight className="w-3 h-3 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
                </a>
              </div>
            </div>

            {Object.entries(footerLinks).map(([title, links]) => (
              <div key={title}>
                <h3 className="text-sm font-medium text-white mb-6">
                  {title === "Product2" ? "" : title}
                </h3>
                <ul className="space-y-4">
                  {links.map((link) => (
                    <li key={link.name}>
                      <a
                        href={link.href}
                        className="text-sm text-white/40 hover:text-white transition-colors inline-flex items-center gap-2"
                      >
                        {link.name}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="py-8 border-t border-white/10 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-sm text-white/30">
            &copy; 2026 viGEMMAlya. Built for a hackathon; ships with honest limitations disclosed.
          </p>

          <div className="flex items-center gap-4 text-sm text-white/30">
            <span className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[#0ca30c]" />
              Air-gapped, on-premise by design
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}

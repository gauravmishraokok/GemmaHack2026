"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

const endpoints = [
  { method: "POST", path: "/evidence/{case_id}", desc: "Assemble the deterministic evidence pack" },
  { method: "POST", path: "/investigate/{case_id}", desc: "Run the constrained Gemma investigation" },
  { method: "GET", path: "/events/stream", desc: "Live SSE feed of pipeline stage transitions" },
  { method: "POST", path: "/grammar/validate", desc: "Probe the decoding grammar's rejection boundary" },
  { method: "POST", path: "/export/{case_id}", desc: "Attest and export the FIU-IND XML" },
  { method: "GET", path: "/audit/verify", desc: "Verify the hash-chain integrity" },
];

const features = [
  {
    title: "Two-plane REST API",
    description: "engine:8001 for case data, reasoning:8002 for evidence, investigation, and export."
  },
  {
    title: "Server-Sent Events",
    description: "Watch a real investigation move through its pipeline stages, live."
  },
  {
    title: "One frozen contract",
    description: "shared_contracts.py — both services validate against it exactly, byte for byte."
  },
  {
    title: "Local-first serving",
    description: "Ollama for Gemma, SQLite/Postgres for storage, no cloud dependency required."
  },
];

export function DevelopersSection() {
  const [isVisible, setIsVisible] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);

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

  return (
    <section id="developers" ref={sectionRef} className="relative py-24 lg:py-32 overflow-hidden">
      <div className="relative z-10 max-w-[1400px] mx-auto px-6 lg:px-12">
        <div
          className={`mb-16 transition-all duration-700 ${
            isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
        >
          <span className="inline-flex items-center gap-3 text-sm font-mono text-muted-foreground mb-6">
            <span className="w-8 h-px bg-foreground/30" />
            API surface
          </span>
          <h2 className="text-6xl md:text-7xl lg:text-[110px] font-display tracking-tight leading-[0.9]">
            Built on
            <br />
            <span className="text-muted-foreground">a real backend.</span>
          </h2>
        </div>

        <div className="grid lg:grid-cols-12 gap-8 lg:gap-12">
          <div
            className={`lg:col-span-5 transition-all duration-700 delay-100 ${
              isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
            }`}
          >
            <p className="text-xl text-muted-foreground mb-10 leading-relaxed">
              Every panel in this product calls a real endpoint against a real,
              running pipeline. Watch the whole thing move stage by stage on the
              live pipeline page.
            </p>
            <div className="grid grid-cols-2 gap-6 mb-10">
              {features.map((feature, index) => (
                <div
                  key={feature.title}
                  className={`transition-all duration-500 ${
                    isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
                  }`}
                  style={{ transitionDelay: `${index * 50 + 200}ms` }}
                >
                  <h3 className="font-medium mb-1">{feature.title}</h3>
                  <p className="text-sm text-muted-foreground">{feature.description}</p>
                </div>
              ))}
            </div>
            <Link
              href="/pipeline"
              className="inline-flex items-center gap-2 text-sm font-medium border-b border-foreground/30 pb-1 hover:border-foreground transition-colors group"
            >
              Watch the live pipeline
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </Link>
          </div>

          <div
            className={`lg:col-span-7 transition-all duration-700 delay-200 ${
              isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
            }`}
          >
            <div className="border border-foreground/10 bg-foreground/[0.02] font-mono text-sm overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-foreground/10">
                <span className="w-2.5 h-2.5 rounded-full bg-[#d03b3b]" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#fab219]" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#0ca30c]" />
                <span className="ml-3 text-xs text-muted-foreground">reasoning · :8002</span>
              </div>
              <div className="divide-y divide-foreground/5">
                {endpoints.map((ep) => (
                  <div key={ep.path} className="flex items-center gap-4 px-4 py-3 hover:bg-foreground/[0.03] transition-colors">
                    <span
                      className={`shrink-0 w-14 text-xs font-semibold ${
                        ep.method === "GET" ? "text-[#3987e5]" : "text-[#ec835a]"
                      }`}
                    >
                      {ep.method}
                    </span>
                    <span className="shrink-0 text-foreground/80">{ep.path}</span>
                    <span className="text-xs text-muted-foreground truncate">{ep.desc}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

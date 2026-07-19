"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Wifi, WifiOff } from "lucide-react";
import { reasoningApi, BAND_STYLE, type CaseSummary, type HealthResponse } from "@/lib/reasoning-client";
import { InlineSpinner, InlineError } from "@/components/case/primitives";
import { GrammarDemo } from "@/components/case/grammar-demo";
import { ThemeToggle } from "@/components/theme-toggle";

function BandTile({ band, count }: { band: "RED" | "YELLOW" | "GREEN"; count: number }) {
  const s = BAND_STYLE[band];
  const sub = band === "RED" ? "investigate first" : band === "YELLOW" ? "review queue" : "low priority";
  return (
    <div className="flex-1 rounded-xl border border-border bg-card px-5 py-4">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em]" style={{ color: s.color }}>
        <span aria-hidden="true">{s.icon}</span>
        {s.label} band
      </div>
      <div className="mt-1 font-mono text-4xl font-semibold tabular-nums">{count}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{sub}</div>
    </div>
  );
}

export default function CasesDashboard() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [threshold, setThreshold] = useState(0.7);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    reasoningApi.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    reasoningApi
      .listCases(threshold)
      .then(setCases)
      .catch((e) => setError(e.message));
  }, [threshold]);

  const counts = useMemo(() => {
    const c = { RED: 0, YELLOW: 0, GREEN: 0 };
    (cases ?? []).forEach((x) => (c[x.risk_band] += 1));
    return c;
  }, [cases]);

  const totalAlerts = (cases ?? []).reduce((n, c) => n + c.member_count, 0);
  const llmUp = health?.llm?.ollama === "up" || health?.llm?.ollama === "mock";

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <Link href="/" className="flex items-center gap-3 text-left">
            <span className="inline-block h-2 w-2 rounded-full bg-[#e34948]" aria-hidden="true" />
            <div>
              <div className="font-display text-sm font-semibold tracking-wide">viGEMMAlya</div>
              <div className="text-[11px] text-muted-foreground">Air-gapped AML co-investigator · reasoning plane</div>
            </div>
          </Link>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {health && (
              <>
                <span className="hidden sm:inline">
                  {health.case_source === "engine" ? "engine :8001" : "mock fixtures"}
                </span>
                <span
                  className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1"
                  style={{
                    borderColor: llmUp ? "var(--status-good)" : "var(--status-critical)",
                    color: llmUp ? "var(--status-good)" : "var(--status-critical)",
                  }}
                >
                  {llmUp ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
                  {llmUp ? `${health.llm.model} · local` : "Ollama offline"}
                </span>
              </>
            )}
            <Link href="/" className="hidden items-center gap-1 text-muted-foreground hover:text-foreground sm:flex">
              <ArrowLeft className="h-3.5 w-3.5" /> home
            </Link>
            <ThemeToggle className="border-border text-muted-foreground hover:text-foreground hover:border-foreground/40" />
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-6xl space-y-8 px-6 py-8">
        {error && <InlineError error={`Cannot reach reasoning service: ${error}`} />}
        {!cases && !error && <InlineSpinner label="Loading cases…" />}

        {cases && (
          <>
            <div>
              <div className="mb-4 flex items-end justify-between">
                <div>
                  <h1 className="font-display text-2xl font-semibold tracking-tight">Case triage</h1>
                  <p className="text-sm text-muted-foreground">
                    {totalAlerts} raw alerts collapsed into {cases.length} investigable cases by graph
                    community detection (engine plane).
                  </p>
                </div>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row">
                <BandTile band="RED" count={counts.RED} />
                <BandTile band="YELLOW" count={counts.YELLOW} />
                <BandTile band="GREEN" count={counts.GREEN} />
              </div>

              <div className="mt-3 flex items-center gap-4 rounded-xl border border-border bg-card px-5 py-3">
                <label htmlFor="threshold" className="whitespace-nowrap text-xs text-muted-foreground">
                  RED threshold (activation-probe p)
                </label>
                <input
                  id="threshold"
                  type="range"
                  min="0.3"
                  max="0.95"
                  step="0.05"
                  value={threshold}
                  onChange={(e) => setThreshold(parseFloat(e.target.value))}
                  className="w-full accent-[var(--status-critical)]"
                />
                <span className="w-12 text-right font-mono text-sm font-semibold tabular-nums">
                  {threshold.toFixed(2)}
                </span>
              </div>
            </div>

            <div>
              <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                Cases
              </h3>
              <div className="grid gap-3 sm:grid-cols-2">
                {cases
                  .slice()
                  .sort((a, b) => b.p - a.p)
                  .map((c) => {
                    const s = BAND_STYLE[c.risk_band];
                    return (
                      <Link
                        key={c.case_id}
                        href={`/cases/${c.case_id}`}
                        className="group rounded-xl border border-border bg-card px-5 py-4 text-left transition hover:border-muted-foreground"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-sm font-semibold">{c.case_id}</span>
                          <span
                            className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium"
                            style={{ borderColor: s.color, color: s.color }}
                          >
                            <span aria-hidden="true" className="text-[9px]">
                              {s.icon}
                            </span>
                            {s.label}
                          </span>
                        </div>
                        <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                          <span>{c.member_count} member alerts</span>
                          <span className="tabular-nums">risk p = {c.p.toFixed(2)}</span>
                        </div>
                        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{ width: `${c.p * 100}%`, background: s.color }}
                          />
                        </div>
                        <div className="mt-3 flex items-center gap-1 text-[11px] text-muted-foreground opacity-0 transition group-hover:opacity-100">
                          Open investigation <ArrowUpRight className="h-3 w-3" />
                        </div>
                      </Link>
                    );
                  })}
              </div>
            </div>

            <GrammarDemo />
          </>
        )}
      </div>
    </main>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Play, Wifi, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  reasoningApi,
  subscribePipelineEvents,
  type CaseSummary,
  type PipelineEvent,
} from "@/lib/reasoning-client";
import { StageTracker, deriveStageStates } from "@/components/pipeline/stage-tracker";
import { LiveLog } from "@/components/pipeline/live-log";

const RISK_COLOR: Record<string, string> = {
  RED: "#d03b3b",
  YELLOW: "#fab219",
  GREEN: "#0ca30c",
};

export default function PipelinePage() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [selectedCase, setSelectedCase] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backendUp, setBackendUp] = useState<boolean | null>(null);
  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    reasoningApi
      .health()
      .then(() => setBackendUp(true))
      .catch(() => setBackendUp(false));
    reasoningApi
      .listCases()
      .then((c) => {
        setCases(c);
        if (c.length > 0) setSelectedCase(c.slice().sort((a, b) => b.p - a.p)[0].case_id);
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  // subscribe to the live SSE feed, filtered to the selected case, the moment
  // one is chosen — reconnects automatically if the case changes.
  useEffect(() => {
    unsubRef.current?.();
    setEvents([]);
    setConnected(false);
    if (!selectedCase) return;

    // pull recent history first so switching to a case with a prior run
    // shows its last events immediately, before the stream catches up.
    reasoningApi
      .recentEvents(selectedCase, 100)
      .then(setEvents)
      .catch(() => {});

    const unsub = subscribePipelineEvents(
      (e) => setEvents((prev) => [...prev, e]),
      () => setConnected(true),
      () => setConnected(false),
      selectedCase
    );
    unsubRef.current = unsub;
    return () => unsub();
  }, [selectedCase]);

  const runInvestigation = useCallback(async () => {
    if (!selectedCase) return;
    setRunning(true);
    setError(null);
    try {
      await reasoningApi.investigate(selectedCase);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }, [selectedCase]);

  const stageStates = deriveStageStates(events.filter((e) => e.case_id === selectedCase));
  const overallDone = stageStates.complete.state === "ok" || stageStates.complete.state === "fail";

  return (
    // "dark" pins dark tokens: this page is a deliberately dark terminal view in both themes
    <main className="dark min-h-screen bg-black text-white">
      <header className="border-b border-white/10 sticky top-0 z-20 bg-black/90 backdrop-blur">
        <div className="max-w-[1400px] mx-auto px-6 lg:px-12 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3 text-white/70 hover:text-white transition-colors">
            <ArrowLeft className="w-4 h-4" />
            <span className="text-sm">Back</span>
          </Link>
          <div className="flex items-center gap-2">
            <span className="font-display text-lg">viGEMMAlya</span>
            <span className="font-mono text-xs text-white/40">/ live pipeline</span>
          </div>
          <div className="flex items-center gap-4 text-xs font-mono">
            {backendUp === null ? (
              <span className="text-white/30">checking backend…</span>
            ) : backendUp ? (
              <span className="flex items-center gap-1.5 text-[#0ca30c]">
                <Wifi className="w-3.5 h-3.5" /> reasoning :8002
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-[#d03b3b]">
                <WifiOff className="w-3.5 h-3.5" /> backend unreachable
              </span>
            )}
          </div>
        </div>
      </header>

      <div className="max-w-[1400px] mx-auto px-6 lg:px-12 py-12 lg:py-16">
        <div className="mb-10">
          <h1 className="text-4xl lg:text-5xl font-display tracking-tight mb-3">
            Watch the pipeline think.
          </h1>
          <p className="text-white/50 max-w-2xl leading-relaxed">
            This page is wired to the reasoning service&apos;s real Server-Sent Events
            feed — every stage below lights up as the actual backend investigation
            runs, not a timed animation. Pick a case, run it, and watch evidence
            assembly, the hard gate, Gemma reasoning, grounding, and confidence
            scoring happen live.
          </p>
        </div>

        {backendUp === false && (
          <div className="mb-8 border border-[#d03b3b]/40 bg-[#d03b3b]/5 p-4 text-sm text-[#ec835a]">
            Can&apos;t reach the reasoning service at{" "}
            <code className="font-mono">{reasoningApi.base}</code>. Start it with{" "}
            <code className="font-mono">uvicorn api.main:app --port 8002</code> from{" "}
            <code className="font-mono">reasoning/</code>, then refresh this page.
          </div>
        )}

        <div className="grid lg:grid-cols-12 gap-6">
          {/* Case selector + controls */}
          <div className="lg:col-span-4">
            <div className="border border-white/10 bg-white/[0.02] p-5 mb-4">
              <span className="text-xs font-mono text-white/40 uppercase tracking-wider block mb-3">
                Select a case
              </span>
              {!cases ? (
                <p className="text-sm text-white/30">Loading cases…</p>
              ) : (
                <div className="space-y-1.5 max-h-[280px] overflow-y-auto pr-1">
                  {cases
                    .slice()
                    .sort((a, b) => b.p - a.p)
                    .map((c) => (
                      <button
                        key={c.case_id}
                        onClick={() => setSelectedCase(c.case_id)}
                        className={`w-full text-left px-3 py-2.5 border transition-all flex items-center justify-between gap-3 ${
                          selectedCase === c.case_id
                            ? "border-white/40 bg-white/[0.06]"
                            : "border-white/5 hover:border-white/20"
                        }`}
                      >
                        <span className="font-mono text-xs">{c.case_id}</span>
                        <span
                          className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                          style={{
                            color: RISK_COLOR[c.risk_band],
                            background: `${RISK_COLOR[c.risk_band]}1a`,
                          }}
                        >
                          {c.risk_band} · {c.p.toFixed(2)}
                        </span>
                      </button>
                    ))}
                </div>
              )}
            </div>

            <Button
              onClick={runInvestigation}
              disabled={!selectedCase || running}
              className="w-full h-12 bg-white text-black hover:bg-white/90 rounded-none disabled:opacity-40"
            >
              <Play className="w-4 h-4 mr-2" />
              {running ? "Investigation running…" : `Run investigation on ${selectedCase ?? "—"}`}
            </Button>

            {error && (
              <p className="mt-3 text-xs text-[#ec835a] font-mono leading-relaxed">{error}</p>
            )}

            <div className="mt-4 flex items-center gap-2 text-xs font-mono text-white/30">
              <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-[#0ca30c]" : "bg-white/20"}`} />
              {connected ? "live event stream connected" : "connecting…"}
            </div>
          </div>

          {/* Stage tracker */}
          <div className="lg:col-span-4">
            <div className="border border-white/10 bg-white/[0.02] p-6 lg:p-8 h-full">
              <span className="text-xs font-mono text-white/40 uppercase tracking-wider block mb-6">
                Pipeline stages
              </span>
              {selectedCase ? (
                <StageTracker states={stageStates} />
              ) : (
                <p className="text-sm text-white/30">Select a case to begin.</p>
              )}
              {overallDone && (
                <div
                  className={`mt-4 pt-4 border-t border-white/10 text-sm font-medium ${
                    stageStates.complete.state === "ok" ? "text-[#0ca30c]" : "text-[#ec835a]"
                  }`}
                >
                  {stageStates.complete.state === "ok"
                    ? "STR draft ready — see the case view for the confidence heat-map."
                    : "Halted — no STR drafted for this run."}
                </div>
              )}
            </div>
          </div>

          {/* Live log */}
          <div className="lg:col-span-4">
            <LiveLog events={events.filter((e) => e.case_id === selectedCase)} />
          </div>
        </div>
      </div>
    </main>
  );
}

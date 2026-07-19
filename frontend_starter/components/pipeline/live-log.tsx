"use client";

import { useEffect, useRef } from "react";
import { STAGE_LABELS, type PipelineEvent } from "@/lib/reasoning-client";

function statusColor(status: PipelineEvent["status"]) {
  if (status === "ok") return "#0ca30c";
  if (status === "fail") return "#d03b3b";
  if (status === "start") return "#3987e5";
  return "#898781";
}

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString("en-IN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function LiveLog({ events }: { events: PipelineEvent[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="border border-white/10 bg-black">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/10">
        <span className="w-2 h-2 rounded-full bg-[#0ca30c] animate-pulse" />
        <span className="font-mono text-xs text-white/50">live backend log</span>
        <span className="ml-auto font-mono text-[10px] text-white/25">{events.length} events</span>
      </div>
      <div ref={scrollRef} className="max-h-[420px] overflow-y-auto font-mono text-xs px-4 py-3 space-y-1.5">
        {events.length === 0 && (
          <p className="text-white/25 py-8 text-center">
            No events yet — run an investigation to see the pipeline move.
          </p>
        )}
        {events.map((e, i) => (
          <div key={i} className="flex gap-3 leading-relaxed">
            <span className="text-white/25 shrink-0">{formatTime(e.ts)}</span>
            <span className="shrink-0 w-2 h-2 rounded-full mt-1" style={{ background: statusColor(e.status) }} />
            <span className="shrink-0 text-white/60">{STAGE_LABELS[e.stage] ?? e.stage}</span>
            <span className="text-white/35 truncate">{e.detail}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

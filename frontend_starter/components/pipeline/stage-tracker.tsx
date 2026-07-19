"use client";

import { CheckCircle2, XCircle, Loader2, Circle } from "lucide-react";
import { STAGES, STAGE_LABELS, type PipelineEvent } from "@/lib/reasoning-client";

export type StageState = "idle" | "active" | "ok" | "fail";

export function deriveStageStates(events: PipelineEvent[]): Record<string, { state: StageState; detail?: string }> {
  const out: Record<string, { state: StageState; detail?: string }> = {};
  for (const stage of STAGES) out[stage] = { state: "idle" };

  for (const e of events) {
    if (e.stage === "error") continue;
    if (!STAGES.includes(e.stage as (typeof STAGES)[number])) continue;
    if (e.status === "start") {
      out[e.stage] = { state: "active", detail: e.detail };
    } else if (e.status === "ok") {
      out[e.stage] = { state: "ok", detail: e.detail };
    } else if (e.status === "fail") {
      out[e.stage] = { state: "fail", detail: e.detail };
    }
  }
  return out;
}

function StageIcon({ state }: { state: StageState }) {
  if (state === "ok") return <CheckCircle2 className="w-5 h-5 text-[#0ca30c]" />;
  if (state === "fail") return <XCircle className="w-5 h-5 text-[#d03b3b]" />;
  if (state === "active") return <Loader2 className="w-5 h-5 text-[#3987e5] animate-spin" />;
  return <Circle className="w-5 h-5 text-white/15" />;
}

export function StageTracker({
  states,
  surfaceClassName = "bg-black",
}: {
  states: Record<string, { state: StageState; detail?: string }>;
  /** Background the connector-line icon sits on top of — must match the
   * container this tracker is rendered inside, or the icon shows a visible
   * square. Defaults to the dedicated /pipeline page's black background;
   * pass "bg-card" when embedding inside a themed card. */
  surfaceClassName?: string;
}) {
  const visibleStages = STAGES.filter((s) => s !== "export" || states.export.state !== "idle");

  return (
    <div className="relative">
      {visibleStages.map((stage, i) => {
        const { state, detail } = states[stage];
        const isLast = i === visibleStages.length - 1;
        return (
          <div key={stage} className="relative flex gap-4 pb-8 last:pb-0">
            {!isLast && (
              <div
                className={`absolute left-[10px] top-6 bottom-0 w-px transition-colors duration-500 ${
                  state === "ok" ? "bg-[#0ca30c]/40" : state === "fail" ? "bg-[#d03b3b]/40" : "bg-foreground/10"
                }`}
              />
            )}
            <div className={`shrink-0 mt-0.5 z-10 ${surfaceClassName}`}>
              <StageIcon state={state} />
            </div>
            <div className="flex-1 min-w-0 pb-1">
              <div className="flex items-center gap-3">
                <h4
                  className={`text-sm font-medium transition-colors duration-300 ${
                    state === "idle" ? "text-muted-foreground/50" : "text-foreground"
                  }`}
                >
                  {STAGE_LABELS[stage] ?? stage}
                </h4>
                {state === "active" && (
                  <span className="text-[10px] font-mono uppercase tracking-wider text-[#3987e5] animate-pulse">
                    running
                  </span>
                )}
              </div>
              {detail && (
                <p
                  className={`text-xs mt-1 leading-relaxed font-mono ${
                    state === "fail" ? "text-[#d03b3b]/80" : "text-muted-foreground"
                  }`}
                >
                  {detail}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

import type { EvidencePack, FullInvestigation } from "@/lib/reasoning-client";
import { SectionLabel, AIBadge, InlineSpinner } from "../primitives";

export function InvestigationTab({
  full,
  pack,
  onRun,
  busy,
}: {
  full: FullInvestigation | null;
  pack: EvidencePack;
  onRun: () => void;
  busy: boolean;
}) {
  if (busy) {
    return (
      <div className="rounded-xl border border-border bg-card px-5 py-8">
        <InlineSpinner label="Gemma is reasoning over the evidence pack…" />
      </div>
    );
  }

  if (!full) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-border bg-card px-5 py-8">
        <p className="text-sm text-muted-foreground">
          No investigation has been run for this case yet. The evidence pack on the left tabs
          is assembled deterministically; the investigation is a single constrained Gemma pass
          over exactly those items.
        </p>
        <button
          onClick={onRun}
          className="rounded-lg border px-4 py-2 text-sm font-semibold"
          style={{ borderColor: "var(--cat-company)", color: "var(--cat-company)" }}
        >
          ✦ Run Gemma investigation
        </button>
      </div>
    );
  }

  const { result, diagnostics } = full;
  const insufficient = result.status === "INSUFFICIENT_EVIDENCE";

  return (
    <div className="space-y-4">
      {insufficient && (
        <div className="rounded-xl border px-5 py-4" style={{ borderColor: "var(--status-serious)" }}>
          <div className="text-sm font-semibold" style={{ color: "var(--status-serious)" }}>
            <span aria-hidden="true">▲</span> INSUFFICIENT_EVIDENCE — hard gate engaged
            {diagnostics?.gate === "model_self_assessment" && " (by the model's own sufficiency judgement)"}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            No STR draft was generated and none can be exported. The gate is enforced in the
            pipeline, not the UI.
          </p>
        </div>
      )}

      <div className="rounded-xl border border-border bg-card px-5 py-4">
        <div className="mb-1 flex items-center justify-between">
          <SectionLabel>Investigation summary</SectionLabel>
          <AIBadge />
        </div>
        <p className="text-sm leading-relaxed text-foreground">{result.investigation_summary}</p>
        <div className="mt-3 rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground">
          <span className="text-muted-foreground">behaviour pattern · </span>
          {result.behaviour_pattern}
        </div>
      </div>

      {diagnostics?.evidence_assessment?.length > 0 && (
        <div className="rounded-xl border border-border bg-card px-5 py-4">
          <div className="mb-1 flex items-center justify-between">
            <SectionLabel>Evidence walk-through (step 1 of the constrained pass)</SectionLabel>
            <AIBadge />
          </div>
          <ul className="space-y-2 text-xs">
            {diagnostics.evidence_assessment.map((ea, i) => (
              <li key={i} className="flex gap-3">
                <code className="h-fit shrink-0 rounded border border-border bg-background px-1.5 py-0.5 text-[10px]">
                  {ea.ev_id}
                </code>
                <span className="leading-relaxed text-foreground">{ea.observation}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-border bg-card px-5 py-4">
          <div className="mb-1 flex items-center justify-between">
            <SectionLabel>Suggested next questions</SectionLabel>
            <AIBadge />
          </div>
          <ol className="list-inside list-decimal space-y-2 text-xs leading-relaxed text-foreground">
            {result.suggested_questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ol>
        </div>

        <div className="rounded-xl border border-border bg-card px-5 py-4">
          <SectionLabel>Regulatory references (local retrieval)</SectionLabel>
          <div className="space-y-3">
            {pack.regulations.map((r, i) => (
              <div key={i} className="rounded-lg border border-border bg-background px-3 py-2">
                <div className="text-xs font-semibold text-foreground">{r.section}</div>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{r.text_snippet}</p>
                <div className="mt-1 text-[10px] text-muted-foreground">{r.relevance}</div>
              </div>
            ))}
            {pack.regulations.length === 0 && (
              <p className="text-xs text-muted-foreground">No citations retrieved.</p>
            )}
          </div>
        </div>
      </div>

      {diagnostics && (
        <div className="rounded-xl border border-border bg-card px-5 py-3 text-[11px] text-muted-foreground">
          <span className="uppercase tracking-wider">run diagnostics · </span>
          model {diagnostics.model} · {diagnostics.elapsed_s}s · {diagnostics.total_tokens} tokens
          generated ({diagnostics.answer_tokens} in the constrained answer) · logprobs{" "}
          {diagnostics.logprobs_available ? "captured" : "unavailable"}
          {diagnostics.overall_confidence != null &&
            ` · overall confidence ${(diagnostics.overall_confidence * 100).toFixed(0)}%`}
          {diagnostics.amount_violations?.length > 0 && (
            <span style={{ color: "var(--status-critical)" }}>
              {" "}
              · ▲ {diagnostics.amount_violations.length} amount violation(s)
            </span>
          )}
        </div>
      )}
    </div>
  );
}

import { SectionTitle, AIBadge, Spinner } from "../ui.jsx";

export default function Investigation({ full, pack, onRun, busy }) {
  if (busy) {
    return (
      <div className="card px-5 py-8">
        <Spinner label="Gemma is reasoning over the evidence pack…" />
      </div>
    );
  }
  if (!full) {
    return (
      <div className="card flex flex-col items-start gap-3 px-5 py-8">
        <p className="text-sm text-[var(--ink-2)]">
          No investigation has been run for this case yet. The evidence pack on the
          left tabs is assembled deterministically; the investigation is a single
          constrained Gemma pass over exactly those items.
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
        <div
          className="rounded-xl border px-5 py-4"
          style={{ borderColor: "var(--status-serious)" }}
        >
          <div className="text-sm font-semibold" style={{ color: "var(--status-serious)" }}>
            <span aria-hidden="true">▲</span> INSUFFICIENT_EVIDENCE — hard gate engaged
            {diagnostics?.gate === "model_self_assessment" && " (by the model's own sufficiency judgement)"}
          </div>
          <p className="mt-1 text-xs text-[var(--ink-2)]">
            No STR draft was generated and none can be exported. The gate is
            enforced in the pipeline, not the UI.
          </p>
        </div>
      )}

      <div className="card px-5 py-4">
        <div className="mb-1 flex items-center justify-between">
          <SectionTitle>Investigation summary</SectionTitle>
          <AIBadge />
        </div>
        <p className="text-sm leading-relaxed text-[var(--ink-2)]">
          {result.investigation_summary}
        </p>
        <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--page)] px-3 py-2 text-xs text-[var(--ink-2)]">
          <span className="text-[var(--ink-muted)]">behaviour pattern · </span>
          {result.behaviour_pattern}
        </div>
      </div>

      {diagnostics?.evidence_assessment?.length > 0 && (
        <div className="card px-5 py-4">
          <div className="mb-1 flex items-center justify-between">
            <SectionTitle>Evidence walk-through (step 1 of the constrained pass)</SectionTitle>
            <AIBadge />
          </div>
          <ul className="space-y-2 text-xs">
            {diagnostics.evidence_assessment.map((ea, i) => (
              <li key={i} className="flex gap-3">
                <code className="h-fit shrink-0 rounded border border-[var(--border)] bg-[var(--page)] px-1.5 py-0.5 text-[10px]">
                  {ea.ev_id}
                </code>
                <span className="leading-relaxed text-[var(--ink-2)]">{ea.observation}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card px-5 py-4">
          <div className="mb-1 flex items-center justify-between">
            <SectionTitle>Suggested next questions</SectionTitle>
            <AIBadge />
          </div>
          <ol className="list-inside list-decimal space-y-2 text-xs leading-relaxed text-[var(--ink-2)]">
            {result.suggested_questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ol>
        </div>

        <div className="card px-5 py-4">
          <SectionTitle>Regulatory references (local retrieval)</SectionTitle>
          <div className="space-y-3">
            {pack.regulations.map((r, i) => (
              <div key={i} className="rounded-lg border border-[var(--border)] bg-[var(--page)] px-3 py-2">
                <div className="text-xs font-semibold text-[var(--ink)]">{r.section}</div>
                <p className="mt-1 text-[11px] leading-relaxed text-[var(--ink-2)]">
                  {r.text_snippet}
                </p>
                <div className="mt-1 text-[10px] text-[var(--ink-muted)]">{r.relevance}</div>
              </div>
            ))}
            {pack.regulations.length === 0 && (
              <p className="text-xs text-[var(--ink-muted)]">No citations retrieved.</p>
            )}
          </div>
        </div>
      </div>

      {diagnostics && (
        <div className="card px-5 py-3 text-[11px] text-[var(--ink-muted)]">
          <span className="uppercase tracking-wider">run diagnostics · </span>
          model {diagnostics.model} · {diagnostics.elapsed_s}s ·{" "}
          {diagnostics.total_tokens} tokens generated ({diagnostics.answer_tokens} in the
          constrained answer) · logprobs {diagnostics.logprobs_available ? "captured" : "unavailable"}
          {diagnostics.overall_confidence != null &&
            ` · overall confidence ${(diagnostics.overall_confidence * 100).toFixed(0)}%`}
          {diagnostics.amount_violations?.length > 0 && (
            <span style={{ color: "var(--status-critical)" }}>
              {" "}· ▲ {diagnostics.amount_violations.length} amount violation(s)
            </span>
          )}
        </div>
      )}
    </div>
  );
}

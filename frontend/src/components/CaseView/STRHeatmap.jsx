import { useState } from "react";
import { api, formatAmount, CONF_STYLE } from "../../api/client.js";
import { SectionTitle, AIBadge, Chip, Spinner, ErrorBox } from "../ui.jsx";

function ConfidenceMeter({ value }) {
  const band = value > 0.75 ? "green" : value >= 0.5 ? "yellow" : "red";
  const s = CONF_STYLE[band];
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 w-40 overflow-hidden rounded-full bg-[var(--grid)]">
        <div
          className="h-full rounded-full"
          style={{ width: `${value * 100}%`, background: s.color }}
        />
      </div>
      <span className="tabular text-sm font-semibold" style={{ color: s.color }}>
        {(value * 100).toFixed(0)}%
      </span>
    </div>
  );
}

export default function STRHeatmap({ full, caseId, onRun, busy }) {
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState(null);
  const [error, setError] = useState(null);

  if (busy) {
    return (
      <div className="card px-5 py-8">
        <Spinner label="Drafting STR under the decoding grammar…" />
      </div>
    );
  }

  const draft = full?.result?.str_draft;

  if (!draft) {
    const insufficient = full?.result?.status === "INSUFFICIENT_EVIDENCE";
    return (
      <div className="card flex flex-col items-start gap-3 px-5 py-8">
        {insufficient ? (
          <>
            <div className="text-sm font-semibold" style={{ color: "var(--status-serious)" }}>
              <span aria-hidden="true">▲</span> No STR exists for this case.
            </div>
            <p className="text-sm text-[var(--ink-2)]">
              The evidence gate returned INSUFFICIENT_EVIDENCE, so the drafting stage
              was never reached. This is the system working as designed — a filing
              without evidence is a liability, not a deliverable.
            </p>
          </>
        ) : (
          <>
            <p className="text-sm text-[var(--ink-2)]">
              Run the investigation to draft an STR under grammar constraints.
            </p>
            <button
              onClick={onRun}
              className="rounded-lg border px-4 py-2 text-sm font-semibold"
              style={{ borderColor: "var(--cat-company)", color: "var(--cat-company)" }}
            >
              ✦ Run Gemma investigation
            </button>
          </>
        )}
      </div>
    );
  }

  const overall =
    draft.narration.reduce((s, n) => s + n.confidence, 0) / draft.narration.length;

  async function attestAndExport() {
    setExporting(true);
    setError(null);
    try {
      const res = await api.exportStr(caseId, draft);
      setExported(res);
      const blob = new Blob([res.xml], { type: "application/xml" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `STR_${caseId}.xml`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.message);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="card px-5 py-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <SectionTitle>STR draft — confidence heat-map</SectionTitle>
            <AIBadge />
          </div>
          <div className="flex items-center gap-4">
            <span className="text-[11px] uppercase tracking-wider text-[var(--ink-muted)]">
              overall
            </span>
            <ConfidenceMeter value={overall} />
          </div>
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-wider text-[var(--ink-muted)]">
            ground of suspicion
          </span>
          <code className="rounded border border-[var(--border)] bg-[var(--page)] px-2 py-1 text-xs font-semibold">
            {draft.gos_tag}
          </code>
          <span className="ml-2 text-[11px] uppercase tracking-wider text-[var(--ink-muted)]">
            action
          </span>
          <code className="rounded border border-[var(--border)] bg-[var(--page)] px-2 py-1 text-xs">
            {draft.recommended_action}
          </code>
        </div>

        <div className="space-y-2">
          {draft.narration.map((n, i) => {
            const s = CONF_STYLE[n.band];
            return (
              <div
                key={i}
                className="flex items-start gap-3 rounded-lg px-3 py-2.5"
                style={{
                  borderLeft: `3px solid ${s.color}`,
                  background: `color-mix(in srgb, ${s.color} 7%, transparent)`,
                }}
                title={`Fused confidence: model token logprobs × deterministic grounding = ${(n.confidence * 100).toFixed(1)}%`}
              >
                <span className="mt-0.5 shrink-0 text-[10px]" style={{ color: s.color }} aria-hidden="true">
                  {s.icon}
                </span>
                <p className="flex-1 text-sm leading-relaxed text-[var(--ink-2)]">
                  {n.sentence}
                </p>
                <span
                  className="tabular shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold"
                  style={{ borderColor: s.color, color: s.color }}
                >
                  {(n.confidence * 100).toFixed(0)}% · {s.label}
                </span>
              </div>
            );
          })}
        </div>

        <div className="mt-3 flex flex-wrap gap-4 text-[11px] text-[var(--ink-muted)]">
          {Object.entries(CONF_STYLE).map(([band, s]) => (
            <span key={band} className="inline-flex items-center gap-1.5">
              <span aria-hidden="true" style={{ color: s.color }}>{s.icon}</span>
              {band === "green" && ">75% — model + grounding agree"}
              {band === "yellow" && "50–75% — review before attesting"}
              {band === "red" && "<50% — verify: low model confidence or a failed grounding check"}
            </span>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card px-5 py-4">
          <SectionTitle>Amounts cited (verified against ledger)</SectionTitle>
          <div className="flex flex-wrap gap-2">
            {draft.amounts_cited.map((a, i) => (
              <code key={i} className="tabular rounded border border-[var(--border)] bg-[var(--page)] px-2 py-1 text-xs">
                {formatAmount(a)}
              </code>
            ))}
          </div>
          <SectionTitle>
            <span className="mt-4 block">Evidence referenced</span>
          </SectionTitle>
          <div className="flex flex-wrap gap-1.5">
            {draft.evidence_refs.map((r) => (
              <code key={r} className="rounded border border-[var(--border)] bg-[var(--page)] px-1.5 py-0.5 text-[10px]">
                {r}
              </code>
            ))}
          </div>
        </div>

        <div className="card flex flex-col justify-between px-5 py-4">
          <div>
            <SectionTitle>Human attestation</SectionTitle>
            <p className="text-xs leading-relaxed text-[var(--ink-2)]">
              The model drafts; a human attests. Attesting writes an entry to the
              hash-chained audit log and exports FIU-IND XML. Sentences banded{" "}
              <span style={{ color: "var(--status-critical)" }}>▲ red</span> should be
              verified against the evidence tab before signing off.
            </p>
          </div>
          <div className="mt-4">
            {error && <ErrorBox error={error} />}
            {exported ? (
              <div
                className="rounded-lg border px-4 py-3 text-xs"
                style={{ borderColor: "var(--status-good)", color: "var(--status-good)" }}
              >
                <div className="font-semibold">● Attested & exported — STR_{caseId}.xml downloaded</div>
                <div className="mt-1 break-all font-mono text-[10px] opacity-80">
                  audit seq #{exported.audit_entry.seq} · chain hash{" "}
                  {exported.audit_entry.hash.slice(0, 24)}…
                </div>
              </div>
            ) : (
              <button
                onClick={attestAndExport}
                disabled={exporting}
                className="w-full rounded-lg border px-4 py-2.5 text-sm font-semibold transition disabled:opacity-50"
                style={{ borderColor: "var(--status-good)", color: "var(--status-good)" }}
              >
                {exporting ? "Exporting…" : "✓ Attest & export FIU-IND XML"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

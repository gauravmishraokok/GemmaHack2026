"use client";

import { useState } from "react";
import { reasoningApi, formatAmount, CONF_STYLE, type FullInvestigation } from "@/lib/reasoning-client";
import { SectionLabel, AIBadge, InlineSpinner, InlineError } from "../primitives";

function ConfidenceMeter({ value }: { value: number }) {
  const band = value > 0.75 ? "green" : value >= 0.5 ? "yellow" : "red";
  const s = CONF_STYLE[band];
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 w-40 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full" style={{ width: `${value * 100}%`, background: s.color }} />
      </div>
      <span className="font-mono text-sm font-semibold tabular-nums" style={{ color: s.color }}>
        {(value * 100).toFixed(0)}%
      </span>
    </div>
  );
}

export function StrHeatmapTab({
  full,
  caseId,
  onRun,
  busy,
}: {
  full: FullInvestigation | null;
  caseId: string;
  onRun: () => void;
  busy: boolean;
}) {
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState<Awaited<ReturnType<typeof reasoningApi.exportStr>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (busy) {
    return (
      <div className="rounded-xl border border-border bg-card px-5 py-8">
        <InlineSpinner label="Drafting STR under the decoding grammar…" />
      </div>
    );
  }

  const draft = full?.result?.str_draft;

  if (!draft) {
    const insufficient = full?.result?.status === "INSUFFICIENT_EVIDENCE";
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-border bg-card px-5 py-8">
        {insufficient ? (
          <>
            <div className="text-sm font-semibold" style={{ color: "var(--status-serious)" }}>
              <span aria-hidden="true">▲</span> No STR exists for this case.
            </div>
            <p className="text-sm text-muted-foreground">
              The evidence gate returned INSUFFICIENT_EVIDENCE, so the drafting stage was never
              reached. This is the system working as designed — a filing without evidence is a
              liability, not a deliverable.
            </p>
          </>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
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

  const overall = draft.narration.reduce((s, n) => s + n.confidence, 0) / draft.narration.length;

  async function attestAndExport() {
    setExporting(true);
    setError(null);
    try {
      const res = await reasoningApi.exportStr(caseId, draft!);
      setExported(res);
      const blob = new Blob([res.xml], { type: "application/xml" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `STR_${caseId}.xml`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-card px-5 py-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <SectionLabel>STR draft — confidence heat-map</SectionLabel>
            <AIBadge />
          </div>
          <div className="flex items-center gap-4">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground">overall</span>
            <ConfidenceMeter value={overall} />
          </div>
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-wider text-muted-foreground">ground of suspicion</span>
          <code className="rounded border border-border bg-background px-2 py-1 text-xs font-semibold">
            {draft.gos_tag}
          </code>
          <span className="ml-2 text-[11px] uppercase tracking-wider text-muted-foreground">action</span>
          <code className="rounded border border-border bg-background px-2 py-1 text-xs">
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
                <p className="flex-1 text-sm leading-relaxed text-foreground">{n.sentence}</p>
                <span
                  className="shrink-0 rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold tabular-nums"
                  style={{ borderColor: s.color, color: s.color }}
                >
                  {(n.confidence * 100).toFixed(0)}% · {s.label}
                </span>
              </div>
            );
          })}
        </div>

        <div className="mt-3 flex flex-wrap gap-4 text-[11px] text-muted-foreground">
          {Object.entries(CONF_STYLE).map(([band, s]) => (
            <span key={band} className="inline-flex items-center gap-1.5">
              <span aria-hidden="true" style={{ color: s.color }}>
                {s.icon}
              </span>
              {band === "green" && ">75% — model + grounding agree"}
              {band === "yellow" && "50–75% — review before attesting"}
              {band === "red" && "<50% — verify: low model confidence or a failed grounding check"}
            </span>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-border bg-card px-5 py-4">
          <SectionLabel>Amounts cited (verified against ledger)</SectionLabel>
          <div className="flex flex-wrap gap-2">
            {draft.amounts_cited.map((a, i) => (
              <code key={i} className="rounded border border-border bg-background px-2 py-1 font-mono text-xs tabular-nums">
                {formatAmount(a)}
              </code>
            ))}
          </div>
          <SectionLabel>
            <span className="mt-4 block">Evidence referenced</span>
          </SectionLabel>
          <div className="flex flex-wrap gap-1.5">
            {draft.evidence_refs.map((r) => (
              <code key={r} className="rounded border border-border bg-background px-1.5 py-0.5 text-[10px]">
                {r}
              </code>
            ))}
          </div>
        </div>

        <div className="flex flex-col justify-between rounded-xl border border-border bg-card px-5 py-4">
          <div>
            <SectionLabel>Human attestation</SectionLabel>
            <p className="text-xs leading-relaxed text-muted-foreground">
              The model drafts; a human attests. Attesting writes an entry to the hash-chained
              audit log and exports FIU-IND XML. Sentences banded{" "}
              <span style={{ color: "var(--status-critical)" }}>▲ red</span> should be verified
              against the evidence tab before signing off.
            </p>
          </div>
          <div className="mt-4">
            {error && <InlineError error={error} />}
            {exported ? (
              <div
                className="rounded-lg border px-4 py-3 text-xs"
                style={{ borderColor: "var(--status-good)", color: "var(--status-good)" }}
              >
                <div className="font-semibold">
                  ● Attested &amp; exported — STR_{caseId}.xml downloaded
                </div>
                <div className="mt-1 break-all font-mono text-[10px] opacity-80">
                  audit seq #{exported.audit_entry.seq} · chain hash{" "}
                  {exported.audit_entry.hash.slice(0, 24)}…
                </div>
                {exported.notifications && (
                  <div className="mt-2 space-y-0.5 text-[10px]">
                    <div style={{ color: exported.notifications.email?.status === "sent" ? "var(--status-good)" : "var(--status-warning)" }}>
                      ✉ email {exported.notifications.email?.status}
                      {exported.notifications.email?.to && ` → ${exported.notifications.email.to}`}
                      {exported.notifications.email?.reason && ` (${exported.notifications.email.reason})`}
                    </div>
                    <div style={{ color: exported.notifications.sms?.status === "sent" ? "var(--status-good)" : "var(--status-warning)" }}>
                      ☏ sms {exported.notifications.sms?.status}
                      {exported.notifications.sms?.to && ` → ${exported.notifications.sms.to}`}
                      {exported.notifications.sms?.reason && ` (${exported.notifications.sms.reason})`}
                    </div>
                  </div>
                )}
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

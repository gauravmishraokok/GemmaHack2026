import type { EvidencePack } from "@/lib/reasoning-client";
import { SectionLabel, SourceBadge } from "../primitives";

const KIND_META: Record<string, { icon: string; label: string }> = {
  transaction: { icon: "⇄", label: "Transactions" },
  relationship: { icon: "◈", label: "Relationships" },
  rule_alert: { icon: "!", label: "Rule alerts (engine)" },
  kyc_flag: { icon: "⚑", label: "KYC risk indicators" },
  document: { icon: "▤", label: "Documents (vision extraction — stubbed)" },
  regulation: { icon: "§", label: "Regulation citations" },
  risk_score: { icon: "◉", label: "Risk score (activation probe)" },
};

export function EvidenceTab({ pack }: { pack: EvidencePack }) {
  const groups: Record<string, typeof pack.evidence> = {};
  pack.evidence.forEach((ev) => {
    (groups[ev.kind] = groups[ev.kind] || []).push(ev);
  });

  return (
    <div className="space-y-4">
      {pack.missing_evidence.length > 0 && (
        <div
          className="rounded-xl border px-5 py-4 text-sm"
          style={{ borderColor: "var(--status-serious)", color: "var(--status-serious)" }}
        >
          <div className="font-semibold">
            <span aria-hidden="true">▲</span> Evidence validator: critical slots unbacked
          </div>
          <ul className="mt-2 list-inside list-disc space-y-1 text-xs">
            {pack.missing_evidence.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs opacity-80">
            The hard gate will return INSUFFICIENT_EVIDENCE — no STR can be drafted for this case
            until these are resolved.
          </p>
        </div>
      )}

      {Object.entries(KIND_META).map(([kind, meta]) => {
        const items = groups[kind];
        if (!items) return null;
        return (
          <div key={kind} className="rounded-xl border border-border bg-card px-5 py-4">
            <div className="mb-1 flex items-center justify-between">
              <SectionLabel>
                <span aria-hidden="true">{meta.icon}</span> {meta.label} ({items.length})
              </SectionLabel>
              <SourceBadge />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    <th className="py-1.5 pr-4 font-medium">ev_id</th>
                    <th className="py-1.5 pr-4 font-medium">source_ref</th>
                    <th className="py-1.5 font-medium">value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {items.map((ev) => (
                    <tr key={ev.ev_id}>
                      <td className="py-2 pr-4 align-top">
                        <code className="rounded border border-border bg-background px-1.5 py-0.5 text-[10px]">
                          {ev.ev_id}
                        </code>
                      </td>
                      <td className="py-2 pr-4 align-top font-mono text-[10px] text-muted-foreground">
                        {ev.source_ref}
                      </td>
                      <td className="py-2 align-top leading-relaxed text-foreground">{ev.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}

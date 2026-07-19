"use client";

import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from "recharts";
import { formatAmount, type Case, type EvidencePack } from "@/lib/reasoning-client";
import { SectionLabel, SourceBadge } from "../primitives";

export function TimelineTab({ caseObj, pack }: { caseObj: Case; pack: EvidencePack }) {
  const data = caseObj.transactions
    .slice()
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    .map((t) => ({
      ...t,
      label: new Date(t.timestamp).toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }),
    }));

  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="rounded-xl border border-border bg-card px-5 py-4 lg:col-span-3">
        <div className="mb-1 flex items-center justify-between">
          <SectionLabel>Transaction amounts over time</SectionLabel>
          <SourceBadge />
        </div>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 4 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) =>
                Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(v)
              }
              width={44}
            />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.04)" }}
              contentStyle={{
                background: "var(--card)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: "var(--foreground)" }}
              formatter={(v: number, _n, entry) => [
                `${formatAmount(v, entry.payload.currency)} — ${entry.payload.from_account} → ${entry.payload.to_account}`,
                entry.payload.txn_id,
              ]}
            />
            <Bar dataKey="amount" radius={[4, 4, 0, 0]} maxBarSize={26}>
              {data.map((t) => (
                <Cell key={t.txn_id} fill={t.typology_flag ? "var(--status-serious)" : "var(--cat-account)"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <div className="mt-2 flex gap-4 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm" style={{ background: "var(--status-serious)" }} />
            rule-flagged transaction
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm" style={{ background: "var(--cat-account)" }} />
            unflagged
          </span>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card px-5 py-4 lg:col-span-2">
        <div className="mb-1 flex items-center justify-between">
          <SectionLabel>Event timeline</SectionLabel>
          <SourceBadge />
        </div>
        <ol className="relative ml-2 max-h-[320px] space-y-4 overflow-y-auto border-l border-border pl-4 pr-1">
          {pack.timeline.map((e, i) => {
            const velocity = e.event.startsWith("VELOCITY");
            return (
              <li key={i} className="relative">
                <span
                  aria-hidden="true"
                  className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full"
                  style={{ background: velocity ? "var(--status-warning)" : "var(--muted-foreground)" }}
                />
                <div className="font-mono text-[11px] tabular-nums text-muted-foreground">
                  {new Date(e.ts).toLocaleString("en-IN")}
                </div>
                <div
                  className="text-xs leading-relaxed"
                  style={{ color: velocity ? "var(--status-warning)" : "var(--foreground)" }}
                >
                  {velocity && <span aria-hidden="true">◆ </span>}
                  {e.event}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}

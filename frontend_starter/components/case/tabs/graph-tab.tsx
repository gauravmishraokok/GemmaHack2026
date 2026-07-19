"use client";

import { useMemo, useState } from "react";
import type { Case, Entity, GraphEdge } from "@/lib/reasoning-client";
import { SectionLabel, SourceBadge } from "../primitives";

type Pos = { x: number; y: number; vx: number; vy: number };

/* Hand-rolled force layout: zero dependencies, deterministic, cannot break on
   stage. Runs to convergence synchronously in useMemo. */
function layout(nodes: Entity[], edges: GraphEdge[], width: number, height: number) {
  const pos: Record<string, Pos> = {};
  const N = nodes.length || 1;
  nodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / N;
    pos[n.id] = {
      x: width / 2 + Math.cos(angle) * width * 0.32,
      y: height / 2 + Math.sin(angle) * height * 0.32,
      vx: 0,
      vy: 0,
    };
  });
  const K = 0.02;
  const REP = 9500;
  for (let iter = 0; iter < 420; iter++) {
    for (const a of nodes) {
      for (const b of nodes) {
        if (a.id === b.id) continue;
        const pa = pos[a.id], pb = pos[b.id];
        const dx = pa.x - pb.x, dy = pa.y - pb.y;
        const d2 = Math.max(dx * dx + dy * dy, 100);
        const f = REP / d2;
        const d = Math.sqrt(d2);
        pa.vx += (dx / d) * f;
        pa.vy += (dy / d) * f;
      }
    }
    for (const e of edges) {
      const pa = pos[e.source], pb = pos[e.target];
      if (!pa || !pb) continue;
      const dx = pb.x - pa.x, dy = pb.y - pa.y;
      pa.vx += dx * K; pa.vy += dy * K;
      pb.vx -= dx * K; pb.vy -= dy * K;
    }
    for (const n of nodes) {
      const p = pos[n.id];
      p.vx += (width / 2 - p.x) * 0.005;
      p.vy += (height / 2 - p.y) * 0.005;
      p.x += Math.max(-8, Math.min(8, p.vx));
      p.y += Math.max(-8, Math.min(8, p.vy));
      p.vx *= 0.5; p.vy *= 0.5;
      p.x = Math.max(50, Math.min(width - 50, p.x));
      p.y = Math.max(34, Math.min(height - 34, p.y));
    }
  }
  return pos;
}

const TYPE_STYLE: Record<string, { color: string; shape: "circle" | "square" | "diamond" | "hex"; label: string }> = {
  Account: { color: "var(--cat-account)", shape: "circle", label: "Account" },
  Person: { color: "var(--cat-person)", shape: "square", label: "Person" },
  Company: { color: "var(--cat-company)", shape: "diamond", label: "Company" },
  PAN: { color: "var(--cat-pan)", shape: "hex", label: "PAN" },
};

const EDGE_STYLE: Record<string, { dash?: string; width: number }> = {
  SENT: { width: 2 },
  LINKED_PAN: { dash: "5 4", width: 1.5 },
  OWNED_BY: { dash: "2 3", width: 1 },
  DIRECTOR_OF: { dash: "8 3", width: 1.5 },
};

function NodeMark({ x, y, type, selected }: { x: number; y: number; type: string; selected: boolean }) {
  const s = TYPE_STYLE[type] || TYPE_STYLE.Account;
  const r = selected ? 11 : 9;
  const common = { fill: s.color, stroke: "var(--card)", strokeWidth: 2 };
  if (s.shape === "square") return <rect x={x - r} y={y - r} width={2 * r} height={2 * r} rx={3} {...common} />;
  if (s.shape === "diamond")
    return (
      <rect
        x={x - r}
        y={y - r}
        width={2 * r}
        height={2 * r}
        rx={3}
        transform={`rotate(45 ${x} ${y})`}
        {...common}
      />
    );
  if (s.shape === "hex") {
    const pts = Array.from({ length: 6 }, (_, i) => {
      const a = (Math.PI / 3) * i - Math.PI / 6;
      return `${x + r * Math.cos(a)},${y + r * Math.sin(a)}`;
    }).join(" ");
    return <polygon points={pts} {...common} />;
  }
  return <circle cx={x} cy={y} r={r} {...common} />;
}

export function GraphTab({ caseObj }: { caseObj: Case }) {
  const [selected, setSelected] = useState<string | null>(null);
  const width = 860;
  const height = 440;

  const pos = useMemo(() => layout(caseObj.entities, caseObj.graph_edges, width, height), [caseObj]);

  const selEdges = selected
    ? caseObj.graph_edges.filter((e) => e.source === selected || e.target === selected)
    : [];
  const selEntity = caseObj.entities.find((e) => e.id === selected);

  return (
    <div className="rounded-xl border border-border bg-card px-5 py-4">
      <div className="mb-1 flex items-center justify-between">
        <SectionLabel>Entity relationship graph</SectionLabel>
        <SourceBadge />
      </div>
      <div className="grid gap-4 lg:grid-cols-4">
        <div className="overflow-x-auto lg:col-span-3">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full rounded-lg border border-border bg-background"
            role="img"
            aria-label="Force-directed graph of case entities and relationships"
          >
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--muted-foreground)" />
              </marker>
            </defs>
            {caseObj.graph_edges.map((e, i) => {
              const a = pos[e.source], b = pos[e.target];
              if (!a || !b) return null;
              const st = EDGE_STYLE[e.relation] || EDGE_STYLE.SENT;
              const dim = !!selected && e.source !== selected && e.target !== selected;
              return (
                <line
                  key={i}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke="var(--muted-foreground)"
                  strokeOpacity={dim ? 0.12 : 0.5}
                  strokeWidth={st.width}
                  strokeDasharray={st.dash}
                  markerEnd={e.relation === "SENT" ? "url(#arrow)" : undefined}
                />
              );
            })}
            {caseObj.entities.map((n) => {
              const p = pos[n.id];
              const dim =
                !!selected &&
                n.id !== selected &&
                !selEdges.some((e) => e.source === n.id || e.target === n.id);
              return (
                <g
                  key={n.id}
                  opacity={dim ? 0.25 : 1}
                  onClick={() => setSelected(selected === n.id ? null : n.id)}
                  style={{ cursor: "pointer" }}
                >
                  <NodeMark x={p.x} y={p.y} type={n.type} selected={selected === n.id} />
                  <text x={p.x} y={p.y + 22} textAnchor="middle" fill="var(--foreground)" fontSize="10" fontFamily="ui-monospace, monospace" opacity={0.7}>
                    {n.id}
                  </text>
                </g>
              );
            })}
          </svg>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            {Object.entries(TYPE_STYLE).map(([k, v]) => (
              <span key={k} className="inline-flex items-center gap-1.5">
                <span
                  className="inline-block h-2.5 w-2.5"
                  style={{
                    background: v.color,
                    borderRadius: v.shape === "circle" ? "50%" : 2,
                    transform: v.shape === "diamond" ? "rotate(45deg)" : "none",
                  }}
                />
                {v.label}
              </span>
            ))}
            <span className="ml-auto">solid → SENT · dashed = LINKED_PAN · dotted = OWNED_BY · long-dash = DIRECTOR_OF</span>
          </div>
        </div>

        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            {selected ? "Selected entity" : "Click a node"}
          </div>
          {selEntity ? (
            <div className="mt-2 space-y-2 text-xs text-foreground">
              <div className="font-mono text-sm">{selEntity.id}</div>
              <div className="text-muted-foreground">{selEntity.name}</div>
              <div className="text-muted-foreground">type: {selEntity.type}</div>
              {selEntity.owner_pan && <div className="text-muted-foreground">PAN: {selEntity.owner_pan}</div>}
              {selEntity.director_of && selEntity.director_of.length > 0 && (
                <div className="text-muted-foreground">director of: {selEntity.director_of.join(", ")}</div>
              )}
              <div className="pt-2 text-[11px] uppercase tracking-wider text-muted-foreground">
                {selEdges.length} connections
              </div>
              {selEdges.map((e, i) => (
                <div key={i} className="rounded border border-border px-2 py-1 font-mono text-[10px]">
                  {e.source} —{e.relation}→ {e.target}
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              Nodes are the accounts, people, companies and PANs the engine clustered into this case.
              Click any node to isolate its connections.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

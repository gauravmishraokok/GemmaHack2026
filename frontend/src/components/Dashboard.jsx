import { useEffect, useState } from "react";
import { api, BAND_STYLE } from "../api/client.js";
import { SectionTitle, Spinner, ErrorBox, Chip } from "./ui.jsx";
import GrammarDemo from "./GrammarDemo.jsx";

/* Band counts are a headline, not a distribution — stat tiles, not a chart. */
function BandTile({ band, count }) {
  const s = BAND_STYLE[band];
  return (
    <div className="card flex-1 px-5 py-4">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em]" style={{ color: s.color }}>
        <span aria-hidden="true">{s.icon}</span>
        {s.label} band
      </div>
      <div className="mt-1 text-4xl font-semibold tabular">{count}</div>
      <div className="mt-1 text-[11px] text-[var(--ink-muted)]">
        {band === "RED" ? "investigate first" : band === "YELLOW" ? "review queue" : "low priority"}
      </div>
    </div>
  );
}

export default function Dashboard({ onOpenCase }) {
  const [cases, setCases] = useState(null);
  const [error, setError] = useState(null);
  const [threshold, setThreshold] = useState(0.7);

  useEffect(() => {
    api
      .listCases(threshold)
      .then(setCases)
      .catch((e) => setError(e.message));
  }, [threshold]);

  if (error) return <ErrorBox error={`Cannot reach reasoning service: ${error}`} />;
  if (!cases) return <Spinner label="Loading cases…" />;

  const counts = { RED: 0, YELLOW: 0, GREEN: 0 };
  cases.forEach((c) => (counts[c.risk_band] += 1));
  const totalAlerts = cases.reduce((n, c) => n + c.member_count, 0);

  return (
    <div className="space-y-8">
      <div>
        <div className="mb-4 flex items-end justify-between">
          <div>
            <h2 className="text-lg font-semibold">Case triage</h2>
            <p className="text-sm text-[var(--ink-2)]">
              {totalAlerts} raw alerts collapsed into {cases.length} investigable cases
              by graph community detection (engine plane).
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row">
          <BandTile band="RED" count={counts.RED} />
          <BandTile band="YELLOW" count={counts.YELLOW} />
          <BandTile band="GREEN" count={counts.GREEN} />
        </div>

        <div className="card mt-3 flex items-center gap-4 px-5 py-3">
          <label htmlFor="threshold" className="text-xs text-[var(--ink-2)] whitespace-nowrap">
            RED threshold (activation-probe p)
          </label>
          <input
            id="threshold"
            type="range"
            min="0.3"
            max="0.95"
            step="0.05"
            value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
            className="w-full accent-[var(--status-critical)]"
          />
          <span className="tabular text-sm font-semibold w-12 text-right">
            {threshold.toFixed(2)}
          </span>
        </div>
      </div>

      <div>
        <SectionTitle>Cases</SectionTitle>
        <div className="grid gap-3 sm:grid-cols-2">
          {cases
            .slice()
            .sort((a, b) => b.p - a.p)
            .map((c) => {
              const s = BAND_STYLE[c.risk_band];
              return (
                <button
                  key={c.case_id}
                  onClick={() => onOpenCase(c.case_id)}
                  className="card group px-5 py-4 text-left transition hover:border-[var(--ink-muted)]"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm font-semibold">{c.case_id}</span>
                    <Chip color={s.color} icon={s.icon}>{s.label}</Chip>
                  </div>
                  <div className="mt-3 flex items-center justify-between text-xs text-[var(--ink-2)]">
                    <span>{c.member_count} member alerts</span>
                    <span className="tabular">risk p = {c.p.toFixed(2)}</span>
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--grid)]">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${c.p * 100}%`, background: s.color }}
                    />
                  </div>
                  <div className="mt-3 text-[11px] text-[var(--ink-muted)] opacity-0 transition group-hover:opacity-100">
                    Open investigation →
                  </div>
                </button>
              );
            })}
        </div>
      </div>

      <GrammarDemo />
    </div>
  );
}

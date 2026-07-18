import { useEffect, useState } from "react";
import { api, BAND_STYLE } from "../../api/client.js";
import { Spinner, ErrorBox, Chip } from "../ui.jsx";
import Timeline from "./Timeline.jsx";
import GraphView from "./GraphView.jsx";
import Evidence from "./Evidence.jsx";
import Investigation from "./Investigation.jsx";
import STRHeatmap from "./STRHeatmap.jsx";

const TABS = ["Timeline", "Graph", "Evidence", "Investigation", "STR + Heatmap"];

export default function CaseView({ caseId, onBack }) {
  const [caseObj, setCaseObj] = useState(null);
  const [pack, setPack] = useState(null);
  const [full, setFull] = useState(null); // {result, evidence, diagnostics}
  const [tab, setTab] = useState("Timeline");
  const [error, setError] = useState(null);
  const [investigating, setInvestigating] = useState(false);

  useEffect(() => {
    setError(null);
    Promise.all([api.getCase(caseId), api.evidence(caseId)])
      .then(([c, p]) => {
        setCaseObj(c);
        setPack(p);
      })
      .catch((e) => setError(e.message));
    // reuse a previous run if one exists
    api.fullInvestigation(caseId).then(setFull).catch(() => {});
  }, [caseId]);

  async function runInvestigation() {
    setInvestigating(true);
    setError(null);
    try {
      await api.investigate(caseId);
      const f = await api.fullInvestigation(caseId);
      setFull(f);
      setTab(f.result.status === "OK" ? "STR + Heatmap" : "Investigation");
    } catch (e) {
      setError(e.message);
    } finally {
      setInvestigating(false);
    }
  }

  if (error && !caseObj) return <ErrorBox error={error} />;
  if (!caseObj || !pack) return <Spinner label={`Assembling evidence for ${caseId}…`} />;

  const s = BAND_STYLE[caseObj.risk_band];
  const result = full?.result;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--ink-2)] transition hover:border-[var(--ink-muted)]"
          >
            ← Cases
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h2 className="font-mono text-lg font-semibold">{caseObj.case_id}</h2>
              <Chip color={s.color} icon={s.icon}>{s.label}</Chip>
              {result && (
                <Chip
                  color={result.status === "OK" ? "var(--status-good)" : "var(--status-serious)"}
                  icon={result.status === "OK" ? "●" : "▲"}
                >
                  {result.status === "OK" ? "investigated" : "insufficient evidence"}
                </Chip>
              )}
            </div>
            <div className="mt-0.5 text-xs text-[var(--ink-2)] tabular">
              probe p = {caseObj.risk.p.toFixed(2)} · margin {caseObj.risk.margin.toFixed(2)} ·
              OOD {caseObj.risk.ood.toFixed(1)} · {caseObj.transactions.length} txns ·{" "}
              {caseObj.accounts.length} accounts · {caseObj.member_alert_ids.length} alerts
            </div>
          </div>
        </div>

        <button
          onClick={runInvestigation}
          disabled={investigating}
          className="rounded-lg border px-4 py-2 text-sm font-semibold transition disabled:opacity-60"
          style={{ borderColor: "var(--cat-company)", color: "var(--cat-company)" }}
        >
          {investigating
            ? "Gemma investigating… (local 12B pass)"
            : result
              ? "↻ Re-run Gemma investigation"
              : "✦ Run Gemma investigation"}
        </button>
      </div>

      {error && <ErrorBox error={error} />}
      {investigating && (
        <div className="card px-5 py-4">
          <Spinner label="Single constrained pass: evidence → pattern → sufficiency → GoS tag → narration. Logprobs recorded per token for the confidence heat-map." />
        </div>
      )}

      <nav className="flex gap-1 overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--surface)] p-1">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`whitespace-nowrap rounded-lg px-4 py-2 text-sm transition ${
              tab === t
                ? "bg-[var(--surface-2)] font-semibold text-[var(--ink)]"
                : "text-[var(--ink-muted)] hover:text-[var(--ink-2)]"
            }`}
          >
            {t}
          </button>
        ))}
      </nav>

      {tab === "Timeline" && <Timeline caseObj={caseObj} pack={pack} />}
      {tab === "Graph" && <GraphView caseObj={caseObj} />}
      {tab === "Evidence" && <Evidence pack={pack} />}
      {tab === "Investigation" && (
        <Investigation full={full} pack={pack} onRun={runInvestigation} busy={investigating} />
      )}
      {tab === "STR + Heatmap" && (
        <STRHeatmap full={full} caseId={caseId} onRun={runInvestigation} busy={investigating} />
      )}
    </div>
  );
}

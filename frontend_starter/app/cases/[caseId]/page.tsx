"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import {
  reasoningApi,
  subscribePipelineEvents,
  BAND_STYLE,
  type Case,
  type EvidencePack,
  type FullInvestigation,
  type PipelineEvent,
} from "@/lib/reasoning-client";
import { InlineSpinner, InlineError, Chip } from "@/components/case/primitives";
import { ThemeToggle } from "@/components/theme-toggle";
import { StageTracker, deriveStageStates } from "@/components/pipeline/stage-tracker";
import { TimelineTab } from "@/components/case/tabs/timeline-tab";
import { GraphTab } from "@/components/case/tabs/graph-tab";
import { EvidenceTab } from "@/components/case/tabs/evidence-tab";
import { InvestigationTab } from "@/components/case/tabs/investigation-tab";
import { StrHeatmapTab } from "@/components/case/tabs/str-heatmap-tab";

const TABS = ["Timeline", "Graph", "Evidence", "Investigation", "STR + Heatmap"] as const;
type Tab = (typeof TABS)[number];

export default function CaseDetailPage() {
  const params = useParams<{ caseId: string }>();
  const router = useRouter();
  const caseId = params.caseId;

  const [caseObj, setCaseObj] = useState<Case | null>(null);
  const [pack, setPack] = useState<EvidencePack | null>(null);
  const [full, setFull] = useState<FullInvestigation | null>(null);
  const [tab, setTab] = useState<Tab>("Timeline");
  const [error, setError] = useState<string | null>(null);
  const [investigating, setInvestigating] = useState(false);
  const [pipelineEvents, setPipelineEvents] = useState<PipelineEvent[]>([]);

  useEffect(() => {
    setError(null);
    setCaseObj(null);
    setPack(null);
    setFull(null);
    Promise.all([reasoningApi.getCase(caseId), reasoningApi.evidence(caseId)])
      .then(([c, p]) => {
        setCaseObj(c);
        setPack(p);
      })
      .catch((e) => setError(e.message));
    reasoningApi
      .fullInvestigation(caseId)
      .then(setFull)
      .catch(() => {});
  }, [caseId]);

  // Live pipeline events for this case power the inline stage tracker shown
  // while an investigation runs — real backend stages, not a fake timer.
  useEffect(() => {
    setPipelineEvents([]);
    const unsub = subscribePipelineEvents(
      (e) => setPipelineEvents((prev) => [...prev, e]),
      undefined,
      undefined,
      caseId
    );
    return unsub;
  }, [caseId]);

  const runInvestigation = useCallback(async () => {
    setInvestigating(true);
    setError(null);
    setPipelineEvents([]);
    try {
      await reasoningApi.investigate(caseId);
      const f = await reasoningApi.fullInvestigation(caseId);
      setFull(f);
      setTab(f.result.status === "OK" ? "STR + Heatmap" : "Investigation");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setInvestigating(false);
    }
  }, [caseId]);

  if (error && !caseObj) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-8">
        <InlineError error={error} />
      </main>
    );
  }
  if (!caseObj || !pack) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-8">
        <InlineSpinner label={`Assembling evidence for ${caseId}…`} />
      </main>
    );
  }

  const s = BAND_STYLE[caseObj.risk_band];
  const result = full?.result;
  const stageStates = deriveStageStates(pipelineEvents);

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <button
            onClick={() => router.push("/cases")}
            className="flex items-center gap-2 text-sm text-muted-foreground transition hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" /> Cases
          </button>
          <div className="flex items-center gap-3">
            <Link href="/" className="font-display text-sm font-semibold tracking-wide">
              viGEMMAlya
            </Link>
            <ThemeToggle className="border-border text-muted-foreground hover:text-foreground hover:border-foreground/40" />
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-6xl space-y-4 px-6 py-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-4">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="font-mono text-lg font-semibold">{caseObj.case_id}</h1>
                <Chip color={s.color} icon={s.icon}>
                  {s.label}
                </Chip>
                {result && (
                  <Chip
                    color={result.status === "OK" ? "var(--status-good)" : "var(--status-serious)"}
                    icon={result.status === "OK" ? "●" : "▲"}
                  >
                    {result.status === "OK" ? "investigated" : "insufficient evidence"}
                  </Chip>
                )}
              </div>
              <div className="mt-0.5 font-mono text-xs tabular-nums text-muted-foreground">
                probe p = {caseObj.risk.p.toFixed(2)} · margin {caseObj.risk.margin.toFixed(2)} · OOD{" "}
                {caseObj.risk.ood.toFixed(1)} · {caseObj.transactions.length} txns ·{" "}
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
            {investigating ? "Gemma investigating…" : result ? "↻ Re-run Gemma investigation" : "✦ Run Gemma investigation"}
          </button>
        </div>

        {error && <InlineError error={error} />}

        {investigating && (
          <div className="rounded-xl border border-border bg-card px-5 py-5">
            <p className="mb-4 text-xs text-muted-foreground">
              Single constrained pass: evidence → gate → Gemma reasoning → grounding → confidence.
              Stages below light up live from the real backend, via Server-Sent Events.
            </p>
            <StageTracker states={stageStates} surfaceClassName="bg-card" />
          </div>
        )}

        <nav className="flex gap-1 overflow-x-auto rounded-xl border border-border bg-card p-1">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`whitespace-nowrap rounded-lg px-4 py-2 text-sm transition ${
                tab === t
                  ? "bg-secondary font-semibold text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {t}
            </button>
          ))}
        </nav>

        {tab === "Timeline" && <TimelineTab caseObj={caseObj} pack={pack} />}
        {tab === "Graph" && <GraphTab caseObj={caseObj} />}
        {tab === "Evidence" && <EvidenceTab pack={pack} />}
        {tab === "Investigation" && (
          <InvestigationTab full={full} pack={pack} onRun={runInvestigation} busy={investigating} />
        )}
        {tab === "STR + Heatmap" && (
          <StrHeatmapTab full={full} caseId={caseId} onRun={runInvestigation} busy={investigating} />
        )}
      </div>
    </main>
  );
}

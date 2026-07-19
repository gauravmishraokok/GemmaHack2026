import { useEffect, useState } from "react";
import { api } from "./api/client.js";
import Dashboard from "./components/Dashboard.jsx";
import CaseView from "./components/CaseView/index.jsx";

export default function App() {
  const [view, setView] = useState({ name: "dashboard" });
  const [health, setHealth] = useState(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: "down" }));
  }, []);

  const llmUp = health?.llm?.ollama === "up" || health?.llm?.ollama === "mock";

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-[var(--page)]/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <button
            className="flex items-center gap-3 text-left"
            onClick={() => setView({ name: "dashboard" })}
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm">
              ◉
            </div>
            <div>
              <div className="text-sm font-semibold tracking-wide">viGEMMAlya</div>
              <div className="text-[11px] text-[var(--ink-muted)]">
                Air-gapped AML co-investigator · reasoning plane
              </div>
            </div>
          </button>
          <div className="flex items-center gap-3 text-xs text-[var(--ink-2)]">
            {health && (
              <>
                <span className="hidden sm:inline text-[var(--ink-muted)]">
                  {health.case_source === "engine" ? "engine :8001" : "mock fixtures"}
                </span>
                <span
                  className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1"
                  style={{
                    borderColor: llmUp ? "var(--status-good)" : "var(--status-critical)",
                    color: llmUp ? "var(--status-good)" : "var(--status-critical)",
                  }}
                >
                  <span aria-hidden="true" className="text-[8px]">●</span>
                  {llmUp ? `${health.llm.model} · local` : "Ollama offline"}
                </span>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-6">
        {view.name === "dashboard" ? (
          <Dashboard onOpenCase={(caseId) => setView({ name: "case", caseId })} />
        ) : (
          <CaseView caseId={view.caseId} onBack={() => setView({ name: "dashboard" })} />
        )}
      </main>
    </div>
  );
}

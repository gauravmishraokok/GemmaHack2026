import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { SectionTitle } from "./ui.jsx";

const INVALID_EXAMPLE = JSON.stringify(
  { gos_tag: "LOOKS_KINDA_SUSPICIOUS", narration: ["The customer seemed shifty."] },
  null,
  2
);

export default function GrammarDemo() {
  const [raw, setRaw] = useState(INVALID_EXAMPLE);
  const [result, setResult] = useState(null);
  const [tags, setTags] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.strSchema().then((s) => setTags(s.gos_tags)).catch(() => {});
  }, []);

  async function validate() {
    setBusy(true);
    try {
      setResult(await api.validateGrammar(raw));
    } catch (e) {
      setResult({ valid: false, error: e.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <SectionTitle>Constrained decoding — live rejection demo</SectionTitle>
      <div className="card px-5 py-4">
        <p className="mb-3 text-sm text-[var(--ink-2)]">
          The STR is generated under a decoding grammar compiled from a closed JSON
          schema: tokens outside it are <em>masked before sampling</em>, so an invalid
          ground-of-suspicion tag is unreachable — not filtered afterwards. Paste any
          output below to probe the boundary the model physically cannot cross.
        </p>
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <textarea
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              spellCheck={false}
              rows={8}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--page)] p-3 font-mono text-xs text-[var(--ink-2)] outline-none focus:border-[var(--ink-muted)]"
            />
            <button
              onClick={validate}
              disabled={busy}
              className="mt-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-4 py-2 text-sm font-medium transition hover:border-[var(--ink-muted)] disabled:opacity-50"
            >
              {busy ? "Checking…" : "Check against grammar"}
            </button>
            {result && (
              <div
                className="mt-3 rounded-lg border px-4 py-3 text-sm"
                style={{
                  borderColor: result.valid ? "var(--status-good)" : "var(--status-critical)",
                  color: result.valid ? "var(--status-good)" : "var(--status-critical)",
                }}
              >
                <span aria-hidden="true">{result.valid ? "● " : "▲ "}</span>
                {result.valid
                  ? "Structurally valid — this output is reachable under the grammar."
                  : `REJECTED — ${result.error}`}
              </div>
            )}
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
              Closed ground-of-suspicion dictionary
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {tags.map((t) => (
                <code
                  key={t}
                  className="rounded border border-[var(--border)] bg-[var(--page)] px-2 py-1 text-[10px] text-[var(--ink-2)]"
                >
                  {t}
                </code>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-[var(--ink-muted)]">
              During generation these are the <em>only</em> byte sequences the sampler
              can emit for gos_tag. This endpoint replays the same schema checks on
              pasted text so you can see the boundary; in the live pass there is
              nothing to reject — the invalid tokens never get sampled at all.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
